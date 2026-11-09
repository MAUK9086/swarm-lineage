# Checklist for evaluating content-only forensic methods on agent text

Each item names the experiment in this repository that applies it. Numbers are in
`results/E##_*.json`; the reasoning is in `EXPERIMENT_LOG.md`.

1. **State what the method predicts.** Time order (which text appeared first) and
   provenance (which text was copied from which) are different targets. Test provenance
   where true parent links exist. (E41-v2: time order; E46: true revision parents.)
2. **Keep time and order-bearing fields away from the method.** Pass a table without the
   time column; exclude sequence numbers, diff bases, collection times and composite ids.
   (`src/evaluate.py` is the only module that reads `t`; `assert_public` guards the rest.)
3. **Test for row-order and id leakage.** Shuffle rows before processing and check that
   results do not depend on the input order. (E41b found a leak; E48 checks invariance.)
4. **Report documents, pairs and clusters separately.** A few clusters can hold almost all
   pairs. (T02: two clusters hold 98.4% of 8.4M Moltbook pairs.)
5. **Measure candidate-retrieval recall.** Approximate near-duplicate search misses pairs,
   mostly near the threshold. (E49.)
6. **Report cluster concentration** and how much the largest cluster contributes. (T02, E43.)
7. **Define the estimand and the sampling unit.** Pair-weighted, cluster-weighted and
   author-merged accuracy answer different questions. (E32, E34, E43.)
8. **Use cluster-aware uncertainty.** Bootstrap over clusters, not pairs, and check
   calibration with a null that shuffles time within clusters. (E35: 86% vs 5% false alarms.)
9. **Test sensitivity to the cluster definition and thresholds.** (E34, E43.)
10. **Test robustness to samples, seeds and implementation details** such as hash width.
    (E42, E44, E45, E47.)
11. **Compare against simple baselines.** Every direction cue here is compared with "the
    longer text is later". (E32, E36-v2, E41-v2, E46.)
12. **Record every experiment before it runs, including failures and deviations.**
    (`EXPERIMENT_LOG.md`; decision ledger in the report, Table 4.)
