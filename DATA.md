# Data dictionary

Raw data live under `data/` (git-ignored). Each corpus is converted by an adapter in
`src/adapters/` into one standard table.

## Standard table

| Column | Type | Method sees it? | Meaning |
|---|---|---|---|
| doc_id | str | yes (as an opaque key) | document id; checked to carry no order (Moltbook UUIDs are random) |
| text | str | yes | document text |
| group_id | str | yes | submolt (Moltbook) or page id (collusion.wiki) |
| author_id | str | yes | agent id (Moltbook) or edit label (collusion.wiki) |
| t | datetime, UTC | **no** | true time; read only by `src/evaluate.py` |

Rows are shuffled with a fixed seed before any method code runs (v2 pipelines).

## Moltbook (development)

Source: SimulaMet/moltbook-observatory-archive (Hugging Face), 3,602,713 posts; a seeded
sample of 300,000 posts (`data/interim/moltbook_slim.parquet`) is used for development.

| Standard column | Source field |
|---|---|
| doc_id | id |
| text | title and content (see `src/adapters/moltbook.py`) |
| group_id | submolt |
| author_id | agent_id (agent name when the id is missing) |
| t | created_at (UTC) |

Not used by any method: collection dates, file order, scores, comment counts. Owner handles
were stored only as salted hashes (E33).

## collusion.wiki (held out)

Source: the collusion.wiki export, 14,591 revisions of 4,579 pages
(`data/interim/collusion_slim.parquet`).

| Standard column | Source field |
|---|---|
| doc_id | rev_id |
| text | body |
| group_id | page_id |
| author_id | label (or "blank_" + rev_id when empty) |
| t | t_utc |

Excluded from the method because they encode order: seq, diff_base, diff_base_reason,
write_date, time_grade. `diff_base` is read only by `src/evaluate.py` as ground truth for
revision parents (E46).
