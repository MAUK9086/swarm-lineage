Corpora

| Corpus | Role | Texts | Timestamped | Near-duplicate pairs | Clusters | Median pairs per cluster |
|---|---|---|---|---|---|---|
| Moltbook (sample of 3,602,713 posts) | development | 300,000 posts | 100% | 8,361,829 | 1,198 | 1 (largest: 4,229,393) |
| collusion.wiki export | held-out | 14,591 revisions of 4,579 pages | 100% | 36,711 | 1,179 | - |

Cues

| Cue | Predicts A came first when | Equivalent to | Evidence (Moltbook unless noted) |
|---|---|---|---|
| Length | A is shorter (characters) | (reference rule) | ties on 16.7% of pairs |
| Shingle containment | A's shingles are more fully contained in B | A has fewer distinct shingles | ties on 52.1% of pairs |
| Insertion vs deletion | the diff A to B inserts more words than it deletes | A has fewer words | same prediction on 100% of 1,216 untied pairs |
| Extension | more of A survives as B's prefix and suffix | A has fewer words; coin flip if nothing shared | 870 of 1,767 pairs tied |
| Lineage root | A is the text most contained in the others | the shortest text is the root | root is shortest in 54% of clusters (87% on the wiki) |

Ledger

| Exp. | Pre-registered claim | Outcome | Key number |
|---|---|---|---|
| E01-E02 | public Swarm Traces rows carry time | NO-GO | 0 of 189,579 rows timestamped |
| E31 | containment beats length by >= 5 pts (pairs) | NO-GO | 0.590 vs 0.696 |
| E32 | edit cue beats length by >= 5 pts (clusters) | NO-GO | length 0.496; best cue 0.508 |
| E34 | pair-level inflates by >= 5 pts | confirmed | 19.2 pts |
| E35 | naive FPR > 10% while cluster FPR <= 10% | confirmed | 86.3% vs 5.3% |
| E37 | metadata monitor AUROC >= 0.75 (unmatched) | GO by rule, not adopted | 0.960; post count alone 0.948 |
| E38 | matched monitor AUROC >= 0.75 and recall >= 0.30 | NO-GO | 0.691, recall 0.077 |
| E41 | tree depth orders time, beats length | GO, withdrawn (E41b) | 0.098 -> 0.033 after row shuffle |
| E42 | length above chance on every pair sample | unresolved; sample-dependent | length 0.495-0.528 over 4 samples |
