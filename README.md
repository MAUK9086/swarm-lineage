# swarm-lineage

Content-only forensics on agent-swarm text: can the text of near-duplicate posts tell which
copy came first, and does timing metadata alone flag coordinated agents? Every method sees
a table without timestamps; true time is read only by `src/evaluate.py` when scoring.

Developed on Moltbook (SimulaMet observatory archive) and run unchanged on the
collusion.wiki export. Work for the Apart Swarm Alignment sprint (November 2026).

## Main findings

- The standard copy-direction cues (shingle containment, insertion vs deletion, prefix/suffix
  extension, spanning-tree lineage) reduce to comparing text length, and none beats
  "the longer text is later" by the pre-registered margin on either corpus.
- Near-duplicate pairs are highly clustered (on Moltbook the two largest clusters hold 98% of
  8.4M pairs). Scoring pairs instead of clusters inflates accuracy by 13-29 points and gives
  an 86% false-positive rate under a cluster-preserving null (5% when scoring per cluster).
- Where true parent links exist (collusion.wiki revision history), the spanning trees
  recover them well above a random tree, but a "most similar shorter text" rule does as
  well, and length orients the recovered links better than tree depth (E46).
- A lineage result that passed its pre-registered rule was a row-order leak; the frozen
  pipelines now shuffle rows before processing.

`CHECKLIST.md` lists the evaluation checks we recommend for content-only forensic methods,
each linked to the experiment that applies it. `DATA.md` describes every field and whether
methods may see it.
`FUTURE_WORK.md` lists what a conference version would need, candidate datasets with recorded
copying, and related meta-evaluation work.

Every experiment is pre-registered in `EXPERIMENT_LOG.md` (question, hypothesis and go/no-go
rule written before the run; results and decision after).

## Layout

```
src/adapters/     corpus adapters -> standard table (doc_id, text, group_id, author_id, t)
src/copydir.py    shingles, MinHash/LSH pair finding, direction cues (never sees t)
src/lineage.py    clusters, spanning trees, lineage order (never sees t)
src/evaluate.py   the only module that reads t: accuracy, Kendall tau, bootstrap CIs, nulls
src/monitor*.py   metadata-only monitor features and data loading
experiments/      one script per experiment (E00 ... E50), report numbers (T01-T03), figures
configs/          frozen pipeline configurations (SHA-256 recorded in EXPERIMENT_LOG.md)
results/          E##_*.json: aggregates and ids only, with params, seed and git hash
figures/          report and experiment figures
tools/            report builder; reproduce.py checks headline numbers and runs the tests
tests/            unit tests (cue equivalences, time isolation, row-order invariance, metrics)
```

## Running the frozen pipelines on a new corpus

1. Write an adapter in `src/adapters/` that returns the standard table and save it as Parquet.
2. Copy direction (pair finding, four cues, pair-level and cluster-level scoring, three pair scopes):
   `python -I experiments/E36_replication_v2.py --table <table.parquet> --name <corpus>`
3. Lineage trees (three edge scopes, within-cluster null):
   `python -I experiments/E41_lineage_v2.py --table <table.parquet> --name <corpus>`

Both scripts shuffle rows with a fixed seed (42) before any processing and read their
parameters from `configs/E36_pipeline_v2.json` and `configs/E41_lineage_v2.json`.

## Setup

```
pip install -r requirements.txt
python -m unittest discover -s tests     # unit tests, no data needed
python tools/reproduce.py                # check report numbers against results/*.json
```

Data are not included. Moltbook: Hugging Face `SimulaMet/moltbook-observatory-archive`
(downloaded by `experiments/E30_profile.py`). collusion.wiki: export from https://collusion.wiki,
converted with `src/adapters/collusion_wiki.py`. No post or revision text is stored in this
repository.
