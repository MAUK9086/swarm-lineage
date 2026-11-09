Corpora

| Corpus | Role | Texts | Timestamped | Near-duplicate pairs | Clusters | Clusters scored (after template filter) |
|---|---|---|---|---|---|---|
| Moltbook (sample of 3,602,713 posts) | development | 300,000 posts | 100% | 8,361,829 | 1,198 | 547 |
| collusion.wiki export | held-out | 14,591 revisions of 4,579 pages | 100% | 36,711 | 1,179 | 1,140 |

Cues

| Cue | Predicts A came first when | Equivalent to | Evidence (Moltbook unless noted) |
|---|---|---|---|
| Length | A is shorter (characters) | (reference rule) | ties on 16.7% of pairs |
| Shingle containment | A's shingles are more fully contained in B | A has fewer distinct shingles | ties on 52.1% of pairs |
| Insertion vs deletion | the diff A to B inserts more words than it deletes | A has fewer words | same prediction on 100% of 1,216 untied pairs |
| Extension | more of A survives as B's prefix and suffix | A has fewer words; coin flip if nothing shared | 870 of 1,767 pairs tied |
| Lineage root | A is the text most contained in the others | the shortest text is the root | root is shortest in 54% of clusters (87% on the wiki; E41-v2, all scope) |

Ledger

| Exp. | Pre-registered claim | Outcome | Key number |
|---|---|---|---|
| E01-E02 | public Swarm Traces rows carry time | NO-GO | 0 of 189,579 rows timestamped |
| E20 | collusion.wiki: >= 5,000 timed revisions and >= 200 pages with >= 5 revisions | GO | 14,591 revisions; 453 pages |
| E30 | Moltbook: >= 100k timed posts, >= 1,000 agents with >= 20 posts, >= 1% duplicates | GO | 3,602,713 posts; 23,513 agents; 9.35% |
| E31 | containment beats length by >= 5 pts (pairs) | NO-GO | 0.590 vs 0.696 |
| E32 | edit cue beats length by >= 5 pts (clusters) | NO-GO | length 0.496; best cue 0.508 |
| E33 | owner handles link >= 100 multi-agent owners | NO-GO | 10 owners with >= 2 agents |
| E34 | pair-level inflates by >= 5 pts | confirmed | 19.2 pts |
| E35 | naive FPR > 10% while cluster FPR <= 10% | confirmed | 86.3% vs 5.3% |
| E37 | metadata monitor AUROC >= 0.75 (unmatched) | GO by rule, not adopted | 0.960; post count alone 0.948 |
| E38 | matched monitor AUROC >= 0.75 and recall >= 0.30 | NO-GO | 0.691, recall 0.077 |
| E41 | tree depth orders time, beats length | GO, withdrawn (E41b) | 0.098 -> 0.033 after row shuffle |
| E41b | E41 survives a row shuffle (reading rule fixed before the check) | no: GO withdrawn | depth 0.033 < length 0.050 |
| E36-v2 | row shuffle leaves estimates unchanged (Moltbook) | fail (cluster level) | exact items pass; length 0.565 outside E32 CI |
| E41-v2 | lineage signal in any scope (Moltbook); reproduces E41b | NO-GO; reproduced exactly | all 0.033, within_group 0.020, cross_group 0.024 |
| E42 | length above chance on every pair sample | unresolved; sample-dependent | length 0.495-0.528 over 4 samples |
| Held-out (E36-v2) | collusion.wiki: edit cue beats length by >= 5 pts | NO-GO | length 0.892; best cue 0.889 |
| Held-out (E41-v2) | collusion.wiki: tree depth beats length | NO-GO | depth 0.694 vs length 0.764 |
