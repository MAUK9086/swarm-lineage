# swarm-lineage

Recovering relative time order and copy/mutation lineage for payloads in the Swarm
Traces redacted corpus, and checking the inferred order against independent ground
truth (rows with time estimates, version tags written in the payloads, numbered
command sequences).

Work for the Apart Swarm Alignment Hackathon (deadline 9 Nov 2026).

## Layout

```
src/            shared code (streaming reader, result helpers, later: normalise, families, lineage)
experiments/    one standalone script per experiment (E00_profile.py, ...)
results/        E##_name.json per experiment (numbers, params, seed, git hash) and summary.csv
figures/        E##_*.png
EXPERIMENT_LOG.md   lab notebook; each entry is pre-registered before the run
```

## Setup

```
pip install -r requirements.txt
```

Place the corpus at `data/raw/redacted.jsonl.gz`. The `data/` directory is not tracked;
results files hold aggregates and row ids only.

Run an experiment from the repo root, e.g. `python experiments/E00_profile.py`.
All randomness uses seed 42.
