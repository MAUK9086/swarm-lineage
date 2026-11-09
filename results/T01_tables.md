Table 1

| Corpus | Role | Documents | Timestamped | Near-duplicate pairs scored | Clusters (components) |
|---|---|---|---|---|---|
| Swarm Traces (public release) | motivation | 189,579 rows | 0 | - | - |
| Moltbook (300k-post sample of 3,602,713) | development | 300,000 posts | 100% | 8,360,718 | 1,212 |
| collusion.wiki export | held-out | 14,591 revisions | 100% | 36,711 | 1,179 |

Table 2

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
