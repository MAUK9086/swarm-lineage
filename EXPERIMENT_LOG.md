# Experiment log

Append-only. The question, hypothesis and go/no-go criterion of each entry are written
before the experiment runs; results, interpretation and decision are filled in
afterwards from the matching results/E##_*.json file.

Global seed: 42.

---

### E00 - Corpus profile and slim Parquet  (2026-11-07 21:12 IST)
- Question: What does data/raw/redacted.jsonl.gz contain: row count, fields, their types
  and presence rates, example values, and how the decoded program text is stored?
- Hypothesis / expected: Over 80,000 rows (the Swarm Traces report says "over 80,000
  reassembled attack payloads"). A flat schema of id, cite, kind, parent_id, time_utc,
  tags, text (seen in the first rows). Per the report, about 3% of payloads have a time
  estimate, so time_utc should be null for roughly 97% of rows. Text is expected to be
  stored as decoded plain source, not base64. No dedicated agent-name field is expected.
- Go / no-go criterion (pre-registered): GO to E01/E02 if (a) every line parses,
  (b) every row has a non-empty id and a text field, (c) ids are unique, and (d) at least
  one row has a non-null time field. Failure of (a)-(c) means fixing the reader first;
  failure of (d) means E01/E02 cannot run as planned.
- Method: Stream the file twice. Pass 1: for each top-level field count presence,
  non-null and non-empty values, value types, string-length stats, the first 3 distinct
  example values (truncated to 150 chars) and value counts when the field has few distinct
  values. Check id format, uniqueness and file order; whether parent_id values resolve to
  ids in the file; whether the cite suffix equals a hash prefix of the text. Describe text
  storage with generic checks (empty, newlines, CRLF, non-ASCII, base64-only charset,
  length percentiles). Pass 2: write data/interim/corpus_slim.parquet.
- Code: experiments/E00_profile.py @ 5d20b3e
- Params: example truncation 150 chars, 3 examples per field; value counts kept for
  fields with <= 200 distinct values; no sampling; seed 42.
- Results: (results/E00_profile.json)

  | item | value |
  |---|---|
  | file size | 15,214,685 bytes (gz) |
  | rows | 189,579 |
  | parse errors | 0 |
  | schema | one key set on all rows: id, cite, kind, parent_id, time_utc, tags, text |
  | kind | payload 91,037; recovered_text 75,534; response 23,008 |
  | id | str, R + 7 digits, unique, R0000001..R0189579, no gaps, increasing in file order |
  | cite | "<id>:<8 hex>"; suffix = first 8 hex of SHA-256(text) on 189,579 / 189,579 rows (MD5 0, SHA-1 0) |
  | parent_id | non-null on 61,125 rows (32.2%): response 18,417, recovered_text 42,708, payload 0; 26,248 distinct parents, all resolve to ids in the file; max 858 children per parent |
  | time_utc | present as a key on every row, null on all 189,579 rows |
  | tags | non-empty on 37 rows (all recovered_text), 35 distinct values, e.g. "article-evidence;g236-command;g23619cmd.bin;command-000001" |
  | text | str on every row, none empty; length min 1, median 119, mean 344.0, p99 3,540, max 445,502; 65,219,859 chars total |
  | text storage | plain decoded text, one string per row: 75,736 rows contain newlines, 395 CRLF, 8,422 non-ASCII, 43,648 leading/trailing whitespace, 12 rows (len >= 40) look base64-only |
  | agent-name field | none |
  | slim Parquet | data/interim/corpus_slim.parquet: id, kind, parent_id, text, tags, time_utc, id_num, text_len; 189,579 rows, 11,985,271 bytes |

  Go/no-go: (a) pass, (b) pass, (c) pass, (d) FAIL (no non-null time value).
- Interpretation: The corpus is clean and well-formed but this redacted release carries
  no time estimates at all. That matches the report, which labels every cited program
  "time uncertain". It differs from the expectation (~3% timed) taken from the report's
  limitations section, which describes the authors' internal data, not this release.
  Agent names are not a field; they would have to come from the text. The only explicit
  sequence labels are the 37 tagged rows (G236 command numbers). Row count (189,579) is
  larger than "over 80,000 payloads" because it also includes responses and recovered
  text; the payload kind alone is 91,037.
- Decision / next step: Per the pre-registered criterion, E01/E02 cannot run as planned.
  They are still run as specified so the null result is recorded with code and numbers.
  Ground-truth source (1) in the project goal (rows with time estimates) is not
  available from time_utc; any replacement (e.g. timestamps embedded in the text) is a
  method change that needs a decision before it is tried.
