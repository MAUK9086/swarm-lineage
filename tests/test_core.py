"""Unit tests for the properties the report relies on.

Run with:  python -m unittest discover -s tests -v

Covers:
    cue equivalences    containment = shingle-count rule; insertion/deletion = token-count rule
    time isolation      split_truth removes t; assert_public refuses tables that carry it
    row-order           node keys and LSH candidate partitions do not depend on row order
    tau summary         lineage_tau_summary equals lineage_evaluation on tie-free ranks
    parent edges        parent_edge_evaluation on a hand-made example
"""

from __future__ import annotations

import random
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.copydir import (  # noqa: E402
    assert_public,
    minhash_signatures,
    predict_containment,
    predict_insdel,
    shingle_hashes_csr,
    shingles,
    tokens,
)
from src.evaluate import lineage_evaluation, lineage_tau_summary, parent_edge_evaluation, split_truth  # noqa: E402
from src.lineage import build_nodes, lsh_bucket_components  # noqa: E402

WORDS = "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi omicron pi rho sigma".split()


def _text(rng: random.Random, n: int) -> str:
    return " ".join(rng.choice(WORDS) for _ in range(n))


def _edit(rng: random.Random, t: str) -> str:
    w = t.split()
    for _ in range(rng.randint(1, 4)):
        op = rng.random()
        if op < 0.4 and w:
            del w[rng.randrange(len(w))]
        else:
            w.insert(rng.randrange(len(w) + 1), rng.choice(WORDS))
    return " ".join(w)


def _table(seed: int = 0, n_base: int = 30) -> pd.DataFrame:
    rng = random.Random(seed)
    rows = []
    for b in range(n_base):
        base = _text(rng, rng.randint(15, 40))
        for k in range(rng.randint(1, 5)):
            rows.append({"doc_id": f"d{b}_{k}", "text": base if k == 0 else _edit(rng, base),
                         "group_id": f"g{b % 4}", "author_id": f"a{rng.randint(0, 9)}",
                         "t": pd.Timestamp("2026-01-01", tz="UTC") + pd.Timedelta(minutes=rng.randint(0, 10_000))})
    df = pd.DataFrame(rows)
    df["t"] = df["t"].dt.as_unit("ns")
    return df


class CueEquivalence(unittest.TestCase):
    def test_containment_equals_shingle_count(self) -> None:
        rng = random.Random(1)
        for _ in range(300):
            a = _text(rng, rng.randint(8, 30))
            b = _edit(rng, a)
            sa, sb = shingles(a), shingles(b)
            inter = len(sa & sb)
            if not sa or not sb or inter == 0 or len(sa) == len(sb):
                continue
            pred, _ = predict_containment(np.array([inter]), np.array([len(sa)]), np.array([len(sb)]))
            self.assertEqual(bool(pred[0]), len(sa) < len(sb))

    def test_insdel_equals_token_count(self) -> None:
        rng = random.Random(2)
        ta, tb = [], []
        for _ in range(300):
            a = _text(rng, rng.randint(8, 30))
            ta.append(tokens(a))
            tb.append(tokens(_edit(rng, a)))
        pred, _ = predict_insdel(ta, tb)
        for p, x, y in zip(pred, ta, tb):
            if len(x) != len(y):
                self.assertEqual(bool(p), len(x) < len(y))


class TimeIsolation(unittest.TestCase):
    def test_split_truth_and_guard(self) -> None:
        df = _table()
        public, truth = split_truth(df)
        self.assertNotIn("t", public.columns)
        self.assertEqual(len(truth), len(df))
        assert_public(public)
        with self.assertRaises(Exception):
            assert_public(df)


class RowOrder(unittest.TestCase):
    def _partition(self, df: pd.DataFrame) -> dict:
        public, _ = split_truth(df)
        nodes = build_nodes(public)
        flat, off = shingle_hashes_csr(nodes["rep_text"], len(nodes["rep_text"]))
        sig = minhash_signatures(flat, off, seed=42)
        cand = lsh_bucket_components(sig, np.diff(off) > 0, threshold=0.5)
        h = nodes["node_hash"]
        part = pd.Series(h).groupby(cand).transform("min")
        return dict(zip(h, part))

    def test_partition_invariant_to_row_order(self) -> None:
        df = _table(3, 40)
        ref = self._partition(df)
        for s in (1, 2, 3):
            self.assertEqual(ref, self._partition(df.sample(frac=1.0, random_state=s).reset_index(drop=True)))


class TauSummary(unittest.TestCase):
    def test_matches_lineage_evaluation_without_ties(self) -> None:
        rng = np.random.default_rng(0)
        docs = [np.array([f"x{i}"]) for i in range(40)]
        truth = pd.Series(pd.to_datetime(rng.integers(0, 10**12, 40), utc=True), index=[f"x{i}" for i in range(40)])
        comps = [np.arange(0, 12), np.arange(12, 25), np.arange(25, 40)]
        ranks = {"m": [rng.permutation(len(c)) for c in comps]}
        a = lineage_tau_summary(truth, docs, comps, ranks, n_boot=200, seed=5)
        b = lineage_evaluation(truth, docs, comps, ranks, n_boot=200, n_null=2, seed=5)
        self.assertAlmostEqual(a["m"]["macro_tau"], b["m"]["macro_tau"], places=12)
        self.assertEqual(a["m"]["macro_ci"], b["m"]["macro_ci"])


class ParentEdges(unittest.TestCase):
    def test_hand_made_example(self) -> None:
        docs = [np.array(["r1"]), np.array(["r2"]), np.array(["r3"]), np.array(["r4"])]
        parent_of = {"r2": "r1", "r3": "r2", "r4": "r2"}
        comps = [np.array([0, 1, 2, 3])]
        perfect = {"p": [np.array([-1, 0, 1, 1])]}
        ev = parent_edge_evaluation(parent_of, docs, comps, perfect, np.array([10, 20, 30, 30]), n_boot=50)
        self.assertEqual(ev["coverage"]["eligible_node_edges"], 3)
        self.assertAlmostEqual(ev["p"]["f1"]["macro"], 1.0)
        self.assertAlmostEqual(ev["p"]["orientation_by_method"]["macro"], 1.0)
        self.assertAlmostEqual(ev["p"]["root_has_no_true_parent"]["macro"], 1.0)
        flipped = {"p": [np.array([1, 2, -1, 1])]}
        ev2 = parent_edge_evaluation(parent_of, docs, comps, flipped, np.array([10, 20, 30, 30]), n_boot=50)
        self.assertAlmostEqual(ev2["p"]["f1"]["macro"], 1.0)
        self.assertLess(ev2["p"]["orientation_by_method"]["macro"], 1.0)


if __name__ == "__main__":
    unittest.main()
