Corpora

| Corpus | Role | Texts | Timed | Pairs | Clusters | Scored clusters |
|---|---|---|---|---|---|---|
| Moltbook | development | 300,000 posts | 100% | 8,361,829 | 1,198 | 547 |
| collusion.wiki | held-out | 14,591 revisions of 4,579 pages | 100% | 36,711 | 1,179 | 1,140 |

Cues

| Cue | Predicts A came first when | Equivalent to | Evidence (Moltbook unless noted) |
|---|---|---|---|
| Length | A is shorter (characters) | (reference rule) | ties on 16.7% of pairs |
| Shingle containment | A's shingles are more fully contained in B | A has fewer distinct shingles | ties on 52.1% of pairs |
| Insertion vs deletion | the diff A to B inserts more words than it deletes | A has fewer words | same prediction on 100% of 1,216 untied pairs |
| Extension | more of A survives as B's prefix and suffix | A has fewer words; coin flip if nothing shared | 870 of 1,767 pairs tied |
| Lineage root | A is the text most contained in the others | the shortest text is the root | root is shortest in 54% of clusters (87% on the wiki; E41-v2, all scope) |

Ledger

| Exp. | Type | Pre-registered claim | Outcome | Key number |
|---|---|---|---|---|
| E01-E02 | gating | public Swarm Traces rows carry time | NO-GO | 0 of 189,579 rows timestamped |
| E20 | gating | collusion.wiki: >= 5,000 timed revisions and >= 200 pages with >= 5 revisions | GO | 14,591 revisions; 453 pages |
| E30 | gating | Moltbook: >= 100k timed posts, >= 1,000 agents with >= 20 posts, >= 1% duplicates | GO | 3,602,713 posts; 23,513 agents; 9.35% |
| E31 | confirmatory | containment beats length by >= 5 pts (pairs) | NO-GO | 0.590 vs 0.696 |
| E32 | confirmatory | edit cue beats length by >= 5 pts (clusters) | NO-GO | length 0.496; best cue 0.508 |
| E33 | gating | owner handles link >= 100 multi-agent owners | NO-GO | 10 owners with >= 2 agents |
| E34 | confirmatory | pair-level inflates by >= 5 pts | confirmed | 19.2 pts |
| E35 | confirmatory | naive FPR > 10% while cluster FPR <= 10% | confirmed | 86.3% vs 5.3% |
| E37 | confirmatory | metadata monitor AUROC >= 0.75 (unmatched) | GO by rule, not adopted | 0.960; post count alone 0.948 |
| E38 | confirmatory | matched monitor AUROC >= 0.75 and recall >= 0.30 | NO-GO | 0.691, recall 0.077 |
| E41 | confirmatory | tree depth orders time, beats length | GO, withdrawn (E41b) | 0.098 -> 0.033 after row shuffle |
| E41b | check | E41 survives a row shuffle (reading rule fixed before the check) | no: GO withdrawn | depth 0.033 < length 0.050 |
| E36-v2 | check | row shuffle leaves estimates unchanged (Moltbook) | fail (cluster level) | exact items pass; length 0.565 outside E32 CI |
| E41-v2 | confirmatory; scopes exploratory | lineage signal in any scope (Moltbook); reproduces E41b | NO-GO; reproduced exactly | all 0.033, within_group 0.020, cross_group 0.024 |
| E42 | post-hoc | length above chance on every pair sample | unresolved; sample-dependent | length 0.495-0.528 over 4 samples |
| Held-out (E36-v2) | confirmatory | collusion.wiki: edit cue beats length by >= 5 pts | NO-GO | length 0.892; best cue 0.889 |
| Held-out (E41-v2) | confirmatory | collusion.wiki: tree depth beats length | NO-GO | depth 0.694 vs length 0.764 |
| E43 | robustness | no cue beats length; length CI includes 0.5 (Jaccard 0.6-0.8, two-stage, author-merged) | robust | length 0.496-0.551; 113 author-merged units |
| E44 | robustness | lineage NO-GO stable over 5 seeds; depth tau-b below length | NO-GO stable; tau-b rule fails | GO in 0 of 15 runs; tau-b below length in 13 of 15 |
| E45 | robustness | < 0.1% of distinct shingles in a 32-bit hash collision | not met | 0.60% of 25,612,365 |
| E46 | confirmatory (added late) | wiki: MST recovers true parent links (F1 >= random + 10 pts); depth orients them better than length (+5 pts) | structure GO; direction NO-GO | F1 0.70 vs 0.31; orientation 0.92 vs 0.96 |
| E47 | robustness | conclusions unchanged with 64-bit shingle hashes | unchanged | 0 of 8,361,829 pairs changed; length 0.496 |
| E48 | robustness | candidate partitions identical over 6 input orders; no GO in any order and scope | not invariant | partitions identical: True; GO in 1 of 18 runs; tree edges shared 22-23% |
| E49 | descriptive | LSH recall of eligible pairs >= 0.8 (else limitation) | below 0.8 | recall 0.51; J 0.5-0.6 0.49, J >= 0.7 at least 0.995 |

Robustness

| Variant (Moltbook) | Clusters | Length | Best other cue / tree depth |
|---|---|---|---|
| Jaccard 0.5-0.95 (largest cluster: 51% of pairs) | 547 | 0.496 (0.461-0.533) | 0.508 |
| Jaccard 0.6-0.95 (largest cluster: 95% of pairs) | 360 | 0.504 (0.456-0.549) | 0.520 |
| Jaccard 0.7-0.95 (largest cluster: 97% of pairs) | 237 | 0.536 (0.484-0.592) | 0.494 |
| Jaccard 0.8-0.95 (largest cluster: 84% of pairs) | 92 | 0.551 (0.465-0.637) | 0.538 |
| Two-stage bootstrap: clusters, then pairs | 547 | 0.493 (0.456-0.527) | - |
| Clusters that share an author merged | 113 | 0.507 (0.423-0.585) | 0.522 |
| Lineage, all pairs, 5 seeds (Kendall tau range) | - | 0.050 to 0.062 | depth 0.002 to 0.033; ties kept 0.016 to 0.038 |
| Lineage, same submolt, 5 seeds (Kendall tau range) | - | 0.028 to 0.045 | depth 0.012 to 0.033; ties kept 0.017 to 0.034 |
| Lineage, across submolts, 5 seeds (Kendall tau range) | - | 0.037 to 0.091 | depth 0.002 to 0.045; ties kept 0.014 to 0.077 |
| 64-bit shingle hashes (8,361,829 pairs) | 547 | 0.496 (0.461-0.533) | 0.508 |
| Lineage, all pairs, 64-bit hashes (Kendall tau) | - | 0.050 | depth 0.033 |
| Lineage, all pairs, 6 input orders (Kendall tau range) | - | 0.046 to 0.059 | depth 0.007 to 0.037 |

Parents

| Predicted parent | Precision | Recall | F1 | Orientation correct | Root has no true parent |
|---|---|---|---|---|---|
| spanning tree (depth) | 0.68 (0.64-0.71) | 0.76 (0.73-0.79) | 0.70 (0.67-0.73) | 0.92 (0.90-0.94) | 0.91 (0.88-0.94) |
| most similar shorter text | 0.70 (0.66-0.73) | 0.74 (0.71-0.77) | 0.70 (0.66-0.73) | 0.98 (0.97-0.99) | 0.97 (0.95-0.99) |
| random spanning tree | 0.29 (0.27-0.32) | 0.34 (0.31-0.37) | 0.31 (0.28-0.33) | 0.46 (0.42-0.51) | 0.24 (0.20-0.28) |
| length, on the tree's recovered links | - | - | - | 0.96 (0.94-0.97) | - |
