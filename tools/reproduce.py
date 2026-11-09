"""Check the report's headline numbers against results/*.json and run the unit tests.

Usage:
    python tools/reproduce.py            # check saved results, rebuild T01 tables, run tests
    python tools/reproduce.py --rerun    # also re-run the fast experiments (T02, E43, E45)

Each check reads one value from a results file and compares it with the number printed in
the report. Raw data (data/) are needed only for --rerun.

File structure:
    CHECKS   (file, key path, expected, tolerance)
    get      read a nested value
    main
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CHECKS = [
    ("T02_cluster_concentration", "share_of_pairs_in_largest.2", 0.984, 0.0005),
    ("E32_copy_direction_v2", "methods.b_longer_is_later.macro", 0.496, 0.0005),
    ("E34_inflation_curve", "criterion.inflation_points_full_window_cap_none", 19.2, 0.05),
    ("E35_null_simulation", "pair_level.false_positive_rate", 0.863, 0.0005),
    ("E35_null_simulation", "component_level.false_positive_rate", 0.053, 0.0005),
    ("E41v2_lineage_moltbook", "scopes.all.evaluation.depth.macro_tau", 0.033, 0.0005),
    ("E41v2_lineage_collusion_wiki", "scopes.cross_group.evaluation.depth.macro_tau", 0.138, 0.0005),
    ("E43_robustness", "robust_overall", True, 0),
    ("E45_hash_collisions", "share_of_distinct_shingles_in_a_collision", 0.0060, 0.00005),
    ("E46_parent_recovery", "scopes.all.mst_tree.f1.macro", 0.699, 0.0005),
    ("E46_parent_recovery", "scopes.all.go_no_go.b_direction.passes", False, 0),
    ("E47_hash64", "conclusions_unchanged", True, 0),
    ("E47_hash64", "copy_direction.pairs_jaccard_changed", 0, 0),
    ("E49_lsh_recall", "bins.0.5-0.6.recall", 0.486, 0.0005),
    ("E48_order_invariance", "partitions_identical_all", True, 0),
    ("E48_order_invariance", "go_met_any", True, 0),
    ("E50_parent_recovery_orders", "stable", True, 0),
]


def get(d: dict, path: str):
    """Nested lookup with dotted keys.

    Args:
        d: Dict.
        path: Dotted path.

    Returns:
        The value.
    """
    parts = path.split(".")
    while parts:
        for n in range(len(parts), 0, -1):
            key = ".".join(parts[:n])
            if isinstance(d, dict) and key in d:
                d, parts = d[key], parts[n:]
                break
        else:
            raise KeyError(path)
    return d


def main() -> None:
    """Run the checks."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--rerun", action="store_true")
    args = ap.parse_args()
    py = sys.executable
    if args.rerun:
        for s in ("T02_cluster_concentration", "E43_robustness", "E45_hash_collisions"):
            subprocess.run([py, str(REPO / "experiments" / f"{s}.py")], check=True, cwd=REPO)
    ok = True
    for name, path, exp, tol in CHECKS:
        val = get(json.loads((REPO / "results" / f"{name}.json").read_text())["results"], path)
        good = val == exp if isinstance(exp, bool) else abs(float(val) - exp) <= tol
        ok &= good
        print(f"{'OK ' if good else 'BAD'} {name}:{path} = {val} (report: {exp})")
    subprocess.run([py, str(REPO / "experiments" / "T01_report_numbers.py")], check=True, cwd=REPO, capture_output=True)
    print("T01 tables rebuilt")
    t = subprocess.run([py, "-m", "unittest", "discover", "-s", "tests"], cwd=REPO, capture_output=True, text=True)
    print(t.stderr.strip().splitlines()[-1])
    ok &= t.returncode == 0
    print("ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
