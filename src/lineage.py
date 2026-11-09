"""Lineage trees over near-duplicate components. Method code: never receives t.

File structure:
    build_nodes            collapse exact duplicates (normalised text) into nodes
    lsh_bucket_components  join all nodes that share any LSH band bucket (no pair listing)
    pairwise_overlap       intersections and set sizes for all pairs of a node set
    lineage_components     sample, verify edges (Jaccard window), split into connected pieces
    lineage_components_scoped  as above, with edges split by pair scope (all / within / cross group)
    build_tree            MST on 1 - Jaccard, containment root, hop depth, inferred rank
    length_rank            baseline: shorter text earlier
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from datasketch.lsh import _optimal_param
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import breadth_first_order, connected_components, minimum_spanning_tree
from tqdm import tqdm

from src.copydir import norm_text_hash


def build_nodes(public: pd.DataFrame) -> dict[str, Any]:
    """Collapse posts with the same normalised text into one node.

    Args:
        public: Public table (doc_id, text, group_id, author_id).

    Returns:
        Dict with node_hash, rep_text (one representative per node), count (posts per
        node), node_docs (list of doc-id arrays per node), dropped_empty.
    """
    h = np.array([norm_text_hash(t) for t in tqdm(public["text"], desc="node keys", unit="doc")], dtype=object)
    keep = h != ""
    df = pd.DataFrame({"h": h[keep], "doc": public["doc_id"].to_numpy()[keep], "text": public["text"].to_numpy()[keep]})
    g = df.groupby("h", sort=False)
    first = g.head(1)
    return {"node_hash": first["h"].to_numpy(), "rep_text": first["text"].tolist(),
            "count": g.size().reindex(first["h"]).to_numpy(),
            "node_docs": [v.to_numpy() for _, v in g["doc"]],
            "dropped_empty": int((~keep).sum())}


def lsh_bucket_components(sig: np.ndarray, use: np.ndarray, threshold: float = 0.5) -> np.ndarray:
    """Component id per node, joining all nodes that share any band bucket.

    Args:
        sig: MinHash signature matrix (n_nodes, num_perm).
        use: Nodes to include (non-empty shingle sets); others get their own id.
        threshold: LSH threshold (selects bands and rows as datasketch does).

    Returns:
        Component root per node.
    """
    bands, rows = _optimal_param(threshold, sig.shape[1], 0.5, 0.5)
    n = sig.shape[0]
    parent = np.arange(n)

    def find(x: int) -> int:
        root = x
        while parent[root] != root:
            root = parent[root]
        while parent[x] != root:
            parent[x], x = root, parent[x]
        return root

    docs = np.flatnonzero(use)
    for bnd in tqdm(range(bands), desc="LSH bucket union", unit="band"):
        block = np.ascontiguousarray(sig[docs, bnd * rows:(bnd + 1) * rows])
        keys = block.view(np.dtype((np.void, block.dtype.itemsize * rows))).ravel()
        _, inv = np.unique(keys, return_inverse=True)
        order = np.argsort(inv, kind="stable")
        inv_s = inv[order]
        starts = np.flatnonzero(np.r_[True, inv_s[1:] != inv_s[:-1]])
        ends = np.r_[starts[1:], len(inv_s)]
        for s, e in zip(starts, ends):
            if e - s < 2:
                continue
            members = docs[order[s:e]]
            r0 = find(int(members[0]))
            for m in members[1:]:
                rm = find(int(m))
                if rm != r0:
                    parent[rm] = r0
    return np.array([find(x) for x in range(n)])


def pairwise_overlap(nodes: np.ndarray, flat: np.ndarray, offsets: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Intersection matrix and set sizes for a set of nodes (CSR shingle hashes).

    Args:
        nodes: Node indices.
        flat: CSR shingle hashes.
        offsets: CSR offsets.

    Returns:
        (inter matrix n x n, sizes n)
    """
    sets = [flat[offsets[v]:offsets[v + 1]] for v in nodes]
    n = len(nodes)
    inter = np.zeros((n, n), dtype=np.int64)
    for i in range(n):
        for j in range(i + 1, n):
            inter[i, j] = inter[j, i] = np.intersect1d(sets[i], sets[j], assume_unique=True).size
    sizes = np.array([len(s) for s in sets], dtype=np.int64)
    return inter, sizes


def lineage_components(cand: np.ndarray, flat: np.ndarray, offsets: np.ndarray, cfg: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Sample candidate components, verify edges and split into connected lineage components.

    Args:
        cand: Candidate component id per node.
        flat: CSR shingle hashes.
        offsets: CSR offsets.
        cfg: Frozen config.

    Returns:
        (list of components with nodes, inter, sizes, jaccard; counts)
    """
    lo, hi = cfg["jaccard_window"]
    rng = np.random.default_rng(cfg["seed"])
    s = pd.Series(np.arange(len(cand))).groupby(cand)
    groups = [g.to_numpy() for _, g in s if len(g) >= cfg["min_nodes"]]
    counts = {"candidate_components_ge_min": len(groups), "candidate_components_capped": 0,
              "nodes_in_candidates_ge_min": int(sum(len(g) for g in groups))}
    out: list[dict[str, Any]] = []
    for g in tqdm(groups, desc="verify components", unit="comp"):
        if len(g) > cfg["max_nodes"]:
            g = np.sort(rng.choice(g, cfg["max_nodes"], replace=False))
            counts["candidate_components_capped"] += 1
        inter, sizes = pairwise_overlap(g, flat, offsets)
        union = sizes[:, None] + sizes[None, :] - inter
        jac = np.where(union > 0, inter / np.maximum(union, 1), 0.0)
        np.fill_diagonal(jac, 0.0)
        adj = (jac >= lo) & (jac <= hi)
        ncomp, lab = connected_components(coo_matrix(adj), directed=False)
        for c in range(ncomp):
            idx = np.flatnonzero(lab == c)
            if len(idx) >= cfg["min_nodes"]:
                out.append({"nodes": g[idx], "inter": inter[np.ix_(idx, idx)], "sizes": sizes[idx],
                            "jaccard": jac[np.ix_(idx, idx)], "edges": adj[np.ix_(idx, idx)]})
    counts["lineage_components"] = len(out)
    counts["nodes_in_lineage_components"] = int(sum(len(c["nodes"]) for c in out))
    return out, counts


def lineage_components_scoped(cand: np.ndarray, flat: np.ndarray, offsets: np.ndarray, cfg: dict[str, Any],
                              node_groups: list[frozenset]) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    """lineage_components with edges split by pair scope; the all scope equals lineage_components.

    Sampling, the Jaccard matrix and the random generator sequence are identical to
    lineage_components; only the edge set differs per scope.

    Args:
        cand: Candidate component id per node.
        flat: CSR shingle hashes.
        offsets: CSR offsets.
        cfg: Frozen config (jaccard_window, min_nodes, max_nodes, seed, pair_scopes).
        node_groups: Set of group ids per node.

    Returns:
        (scope -> list of components, counts)
    """
    lo, hi = cfg["jaccard_window"]
    rng = np.random.default_rng(cfg["seed"])
    s = pd.Series(np.arange(len(cand))).groupby(cand)
    groups = [g.to_numpy() for _, g in s if len(g) >= cfg["min_nodes"]]
    scopes = cfg["pair_scopes"]
    counts: dict[str, Any] = {"candidate_components_ge_min": len(groups), "candidate_components_capped": 0,
                              "nodes_in_candidates_ge_min": int(sum(len(g) for g in groups))}
    out: dict[str, list[dict[str, Any]]] = {sc: [] for sc in scopes}
    edge_counts = {sc: 0 for sc in scopes}
    for g in tqdm(groups, desc="verify components (scoped)", unit="comp"):
        if len(g) > cfg["max_nodes"]:
            g = np.sort(rng.choice(g, cfg["max_nodes"], replace=False))
            counts["candidate_components_capped"] += 1
        inter, sizes = pairwise_overlap(g, flat, offsets)
        union = sizes[:, None] + sizes[None, :] - inter
        jac = np.where(union > 0, inter / np.maximum(union, 1), 0.0)
        np.fill_diagonal(jac, 0.0)
        window = (jac >= lo) & (jac <= hi)
        sets = [node_groups[v] for v in g]
        n = len(g)
        share = np.zeros((n, n), dtype=bool)
        for i in range(n):
            for j in range(i + 1, n):
                if not sets[i].isdisjoint(sets[j]):
                    share[i, j] = share[j, i] = True
        adj_by = {"all": window, "within_group": window & share, "cross_group": window & ~share}
        for sc in scopes:
            adj = adj_by[sc]
            edge_counts[sc] += int(np.triu(adj, 1).sum())
            ncomp, lab = connected_components(coo_matrix(adj), directed=False)
            for c in range(ncomp):
                idx = np.flatnonzero(lab == c)
                if len(idx) >= cfg["min_nodes"]:
                    out[sc].append({"nodes": g[idx], "inter": inter[np.ix_(idx, idx)], "sizes": sizes[idx],
                                    "jaccard": jac[np.ix_(idx, idx)], "edges": adj[np.ix_(idx, idx)]})
    for sc in scopes:
        counts[f"{sc}_verified_edges"] = edge_counts[sc]
        counts[f"{sc}_lineage_components"] = len(out[sc])
        counts[f"{sc}_nodes_in_lineage_components"] = int(sum(len(c["nodes"]) for c in out[sc]))
    return out, counts


def build_tree(comp: dict[str, Any], rng: np.random.Generator) -> dict[str, Any]:
    """MST on 1 - Jaccard over verified edges, containment root, hop depth and inferred rank.

    Args:
        comp: One lineage component from lineage_components.
        rng: Seeded generator (shared across components, in order).

    Returns:
        Dict with root (local index), parent (local), depth, rank (0 = earliest inferred).
    """
    n = len(comp["nodes"])
    w = np.where(comp["edges"], 1.0 - comp["jaccard"], 0.0)
    mst = minimum_spanning_tree(coo_matrix(np.triu(w)).tocsr())
    sym = mst + mst.T
    cont = comp["inter"] / np.maximum(comp["sizes"][:, None], 1)
    np.fill_diagonal(cont, 0.0)
    mean_c = cont.sum(axis=1) / (n - 1)
    best = np.flatnonzero(mean_c == mean_c.max())
    root = int(best[rng.integers(0, len(best))]) if len(best) > 1 else int(best[0])
    order, pred = breadth_first_order(sym, root, directed=False, return_predecessors=True)
    depth = np.zeros(n, dtype=np.int64)
    for v in order[1:]:
        depth[v] = depth[pred[v]] + 1
    key = rng.random(n)
    rank = np.empty(n, dtype=np.int64)
    rank[np.lexsort((key, depth))] = np.arange(n)
    return {"root": root, "parent": np.where(pred < 0, -1, pred), "depth": depth, "rank": rank,
            "mean_containment_root": float(mean_c[root])}


def length_rank(lengths: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Baseline order: shorter text earlier, ties broken by a seeded random key.

    Args:
        lengths: Character length per node.
        rng: Seeded generator.

    Returns:
        Rank per node (0 = earliest inferred).
    """
    key = rng.random(len(lengths))
    rank = np.empty(len(lengths), dtype=np.int64)
    rank[np.lexsort((key, lengths))] = np.arange(len(lengths))
    return rank
