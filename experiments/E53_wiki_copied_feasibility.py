"""E53 - Wikipedia {{Copied}} records: are they usable ground truth for cross-page copying?

(a) Sample 400 pages that transclude Template:Copied (or a redirect to it), parse every record
and count how many give both a source revision (from_oldid) and a destination edit (to_diff or
to_oldid). (b) For 60 sampled resolvable records, compare the text added by the destination edit
with the source revision: 5-word-shingle containment of the added text in the source.

Raw wikitext is cached under data/raw/wiki_copied/ (gitignored). Results hold counts and ids only.

File structure:
    Constants         API, sample sizes, thresholds
    api               polite MediaWiki API GET with retries
    transcluding      all pages that use the template or its redirects
    parse_records     {{Copied}} records in one page's wikitext
    revision_text     wikitext and parent id of one revision (cached)
    strip_markup      crude wikitext to plain text
    check_record      containment of a destination edit's added text in the source revision
    main
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import numpy as np
import requests
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.copydir import shingles  # noqa: E402
from src.io_utils import REPO_ROOT, SEED, append_summary, save_result  # noqa: E402

API = "https://en.wikipedia.org/w/api.php"
UA = "SwarmLineageFeasibility/0.1 (https://github.com/MAUK9086/swarm-lineage)"
CACHE = REPO_ROOT / "data" / "raw" / "wiki_copied"
N_PAGES, N_CHECK = 400, 60
CONTAIN_MIN, MIN_ADDED_WORDS = 0.5, 50
GO_RESOLVABLE_SHARE, GO_RESOLVABLE_TOTAL, GO_CONTAIN_SHARE = 0.5, 5000, 0.7
KEY_RE = re.compile(r"^(from|from_oldid|to|to_diff|to_oldid|diff|date)(\d*)$")

SESSION = requests.Session()
SESSION.headers["User-Agent"] = UA


def api(**params: Any) -> dict[str, Any]:
    """GET the MediaWiki API with retries.

    Args:
        **params: Query parameters (format=json is added).

    Returns:
        Parsed JSON response.
    """
    params = {"format": "json", "formatversion": "2", **params}
    for attempt in range(5):
        try:
            r = SESSION.get(API, params=params, timeout=60)
            if r.status_code == 200:
                time.sleep(0.1)
                return r.json()
        except requests.RequestException:
            pass
        time.sleep(2 ** attempt)
    raise RuntimeError(f"API failed: {params}")


def transcluding() -> tuple[list[str], list[str]]:
    """All pages transcluding Template:Copied, and the template's redirect names.

    Returns:
        (sorted page titles, template names including redirects)
    """
    names = ["Copied"]
    cont: dict[str, Any] = {}
    while True:
        r = api(action="query", list="backlinks", bltitle="Template:Copied", blfilterredir="redirects",
                blnamespace=10, bllimit="max", **cont)
        names += [b["title"].split(":", 1)[1] for b in r["query"]["backlinks"]]
        if "continue" not in r:
            break
        cont = r["continue"]
    titles: list[str] = []
    cont = {}
    while True:
        r = api(action="query", list="embeddedin", eititle="Template:Copied", eilimit="max", **cont)
        titles += [p["title"] for p in r["query"]["embeddedin"]]
        if "continue" not in r:
            break
        cont = r["continue"]
    return sorted(set(titles)), names


def _templates(text: str, names: list[str]) -> list[str]:
    """Bodies of top-level {{name ...}} calls for any of the given names (brace-matched)."""
    pat = re.compile(r"\{\{\s*(?:" + "|".join(re.escape(n) for n in names) + r")\s*(?=[|}])", re.IGNORECASE)
    out = []
    for m in pat.finditer(text):
        depth, k = 0, m.start()
        while k < len(text) - 1:
            if text.startswith("{{", k):
                depth += 1
                k += 2
            elif text.startswith("}}", k):
                depth -= 1
                k += 2
                if depth == 0:
                    out.append(text[m.end():k - 2])
                    break
            else:
                k += 1
    return out


def _revid(value: str) -> int | None:
    """Revision id from a bare number or a diff/oldid URL."""
    value = value.strip()
    if value.isdigit():
        return int(value)
    q = parse_qs(urlparse(value).query)
    for key in ("diff", "oldid"):
        if key in q and q[key][0].isdigit():
            return int(q[key][0])
    m = re.search(r"(?:diff|oldid)=(\d+)", value)
    return int(m.group(1)) if m else None


def parse_records(text: str, names: list[str]) -> list[dict[str, Any]]:
    """{{Copied}} records in one page; numbered parameter sets are separate records.

    Args:
        text: Page wikitext.
        names: Template name and redirects.

    Returns:
        One dict per record with from, to, from_oldid, to_rev (ints or None).
    """
    recs = []
    for body in _templates(text, names):
        groups: dict[str, dict[str, str]] = {}
        for part in body.split("|")[1:]:
            if "=" not in part:
                continue
            k, v = part.split("=", 1)
            m = KEY_RE.match(k.strip().lower())
            if m:
                groups.setdefault(m.group(2) or "0", {})[m.group(1)] = v.strip()
        if groups.get("0") and "1" in groups and not groups["0"].get("from"):
            groups.pop("0")
        for g in groups.values():
            to_rev = None
            for key in ("to_diff", "diff", "to_oldid"):
                if g.get(key):
                    to_rev = _revid(g[key])
                    if to_rev:
                        break
            recs.append({"from": g.get("from"), "to": g.get("to"),
                         "from_oldid": _revid(g["from_oldid"]) if g.get("from_oldid") else None, "to_rev": to_rev})
    return recs


def revision_text(revid: int) -> tuple[str | None, int | None]:
    """Wikitext and parent id of a revision, cached on disk.

    Args:
        revid: Revision id.

    Returns:
        (wikitext or None if hidden/missing, parent revision id)
    """
    path = CACHE / f"rev_{revid}.json"
    if path.exists():
        d = json.loads(path.read_text(encoding="utf-8"))
        return d["text"], d["parent"]
    r = api(action="query", prop="revisions", revids=revid, rvprop="ids|content", rvslots="main")
    text, parent = None, None
    pages = r.get("query", {}).get("pages", [])
    if pages and pages[0].get("revisions"):
        rev = pages[0]["revisions"][0]
        parent = rev.get("parentid")
        text = rev.get("slots", {}).get("main", {}).get("content")
    CACHE.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"text": text, "parent": parent}), encoding="utf-8")
    return text, parent


def strip_markup(t: str) -> str:
    """Crude wikitext to plain text: drop refs, templates, tags; keep link labels."""
    t = re.sub(r"<ref[^>/]*/>", " ", t)
    t = re.sub(r"<ref[^>]*>.*?</ref>", " ", t, flags=re.S)
    for _ in range(5):
        t = re.sub(r"\{\{[^{}]*\}\}", " ", t)
    t = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", t)
    t = re.sub(r"\[https?://\S+\s*([^\]]*)\]", r"\1", t)
    t = re.sub(r"<[^>]+>", " ", t)
    return t.replace("'''", "").replace("''", "")


def check_record(rec: dict[str, Any]) -> dict[str, Any]:
    """Containment of the destination edit's added text in the source revision text.

    Args:
        rec: Record with from_oldid and to_rev.

    Returns:
        Dict with status ('ok', 'short', 'missing') and containment.
    """
    dest, parent = revision_text(rec["to_rev"])
    src, _ = revision_text(rec["from_oldid"])
    before = revision_text(parent)[0] if parent else ""
    if dest is None or src is None:
        return {"status": "missing"}
    old_lines = set((before or "").splitlines())
    added = strip_markup("\n".join(ln for ln in dest.splitlines() if ln not in old_lines))
    if len(added.split()) < MIN_ADDED_WORDS:
        return {"status": "short", "added_words": len(added.split())}
    sa, ss = shingles(added), shingles(strip_markup(src))
    return {"status": "ok", "added_words": len(added.split()),
            "containment": len(sa & ss) / len(sa) if sa else 0.0}


def main() -> None:
    """Run E53 and write results/E53_wiki_copied_feasibility.json."""
    titles, names = transcluding()
    rng = np.random.default_rng(SEED)
    sample = sorted(rng.choice(len(titles), size=min(N_PAGES, len(titles)), replace=False).tolist())
    sample_titles = [titles[k] for k in sample]
    recs: list[dict[str, Any]] = []
    pages_without = 0
    for k in tqdm(range(0, len(sample_titles), 50), desc="pages", unit="batch"):
        batch = sample_titles[k:k + 50]
        r = api(action="query", prop="revisions", titles="|".join(batch), rvprop="content", rvslots="main")
        for p in r["query"]["pages"]:
            text = (p.get("revisions") or [{}])[0].get("slots", {}).get("main", {}).get("content", "")
            got = parse_records(text, names)
            pages_without += not got
            for g in got:
                recs.append({"page": p["title"], **g})
    resolvable = [r for r in recs if r["from_oldid"] and r["to_rev"]]
    share = len(resolvable) / len(recs) if recs else 0.0
    per_page = len(resolvable) / len(sample_titles)
    implied = per_page * len(titles)

    pick = sorted(rng.choice(len(resolvable), size=min(N_CHECK, len(resolvable)), replace=False).tolist())
    checks = []
    for k in tqdm(pick, desc="check", unit="rec"):
        c = check_record(resolvable[k])
        checks.append({"page": resolvable[k]["page"], "from_oldid": resolvable[k]["from_oldid"],
                       "to_rev": resolvable[k]["to_rev"], **c})
    ok = [c for c in checks if c["status"] == "ok"]
    contained = [c for c in ok if c["containment"] >= CONTAIN_MIN]
    cont = np.array([c["containment"] for c in ok]) if ok else np.array([])
    res = {
        "transcluding_pages": len(titles), "template_names": len(names),
        "sample_pages": len(sample_titles), "sample_pages_without_parsed_record": pages_without,
        "records": len(recs), "records_with_from_oldid": sum(1 for r in recs if r["from_oldid"]),
        "records_with_to_rev": sum(1 for r in recs if r["to_rev"]),
        "resolvable_records": len(resolvable), "resolvable_share": share,
        "resolvable_per_page": per_page, "implied_resolvable_total": implied,
        "go_a": bool(share >= GO_RESOLVABLE_SHARE and implied >= GO_RESOLVABLE_TOTAL),
        "checked": len(checks), "check_status": {s: sum(1 for c in checks if c["status"] == s)
                                                 for s in ("ok", "short", "missing")},
        "contained_ge_0.5": len(contained), "contained_share_of_ok": len(contained) / len(ok) if ok else None,
        "containment_quantiles": {q: float(np.percentile(cont, p)) for q, p in (("p25", 25), ("median", 50),
                                                                                ("p75", 75))} if ok else None,
        "checks": checks,
    }
    res["go_b"] = bool(ok and len(contained) / len(ok) >= GO_CONTAIN_SHARE)
    res["go"] = bool(res["go_a"] and res["go_b"])
    save_result("E53_wiki_copied_feasibility", res, {"n_pages": N_PAGES, "n_check": N_CHECK,
                                                    "containment_min": CONTAIN_MIN, "min_added_words": MIN_ADDED_WORDS,
                                                    "shingle_k": 5, "api": API})
    append_summary("E53", {"resolvable_share": share, "implied_total": implied,
                           "contained_share": res["contained_share_of_ok"], "go": res["go"]})
    print(json.dumps({k: v for k, v in res.items() if k != "checks"}, indent=1))


if __name__ == "__main__":
    main()
