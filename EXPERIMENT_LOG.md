# Experiment log

Append-only. The question, hypothesis and go/no-go criterion of each entry are written
before the experiment runs; results, interpretation and decision are filled in
afterwards from the matching results/E##_*.json file.

Global seed: 42.

---

### E00 - Corpus profile and slim Parquet  (2026-11-07 21:09 IST)
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

### E01 - Time estimates: coverage, source, span  (2026-11-07 21:11 IST)
- Question: How many rows have a time estimate, where does it come from, what span does
  it cover, and what does its distribution look like?
- Hypothesis / expected: Written after E00, which found time_utc null on all 189,579
  rows and no other time, date or provenance field. Expected: 0 rows with a time
  estimate, no source field, no span, no histogram.
- Go / no-go criterion (pre-registered): GO for using time_utc as ground truth if at
  least 100 rows have a parseable time estimate. Otherwise NO-GO: time_utc cannot serve
  as ground-truth source (1).
- Method: Load the slim Parquet; parse time_utc as UTC; count non-null, parseable and
  unparseable values overall and per kind. List any column whose name suggests a time
  source or provenance. If any times parse: report min, max and span, and plot an hourly
  histogram to figures/E01_time_hist.png.
- Code: experiments/E01_timestamps.py @ 7647235 (re-run at b8875d5 after a metadata-only
  fix to the dirty flag in src/io_utils.py; numbers identical)
- Params: GO threshold 100 rows; histogram bin 1 hour; seed 42 (no sampling).
- Results: (results/E01_timestamps.json)

  | item | value |
  |---|---|
  | rows | 189,579 |
  | time columns | time_utc only |
  | source / provenance columns | none |
  | time_utc non-null | 0 (payload 0 / 91,037; recovered_text 0 / 75,534; response 0 / 23,008) |
  | parseable / unparseable | 0 / 0 |
  | span | none |
  | histogram | not produced (no data) |

  GO: no (0 < 100).
- Interpretation: The release has no time estimates and no field naming a time source.
  The report says its estimates came from gzip header bytes, JWTs, Docker build times
  and timestamps in recovered responses. None of these appear as a field here; if they
  exist, they are inside the text.
- Decision / next step: NO-GO for time_utc as ground-truth source (1). Recorded as a null
  result. Whether to try extracting timestamps from the text is left open for a decision.

### E02 - Leakage check: row id vs time  (2026-11-07 21:11 IST)
- Question: Does the row id number track time, i.e. is file order a leak of time order?
- Hypothesis / expected: Written after E00/E01 pre-registration. With no time estimates
  expected, the correlation should not be computable.
- Go / no-go criterion (pre-registered): Computed only if at least 30 rows have both an
  id number and a parseable time. If computed: |rho| >= 0.5 with p < 0.01 means id order
  leaks time order, and any later ordering method must be compared against id order as
  a baseline. If fewer than 30 rows, the result is "not computable" and the leakage
  question stays open.
- Method: From the slim Parquet take rows with both id_num and a parsed time_utc;
  Spearman rho and two-sided p-value overall and per kind (per kind only if n >= 30).
- Code: experiments/E02_leakage.py @ 7647235 (re-run at b8875d5, see E01)
- Params: minimum n 30; thresholds |rho| >= 0.5, p < 0.01; seed 42 (no sampling).
- Results: (results/E02_leakage.json)

  | item | value |
  |---|---|
  | rows with id_num and time | 0 |
  | Spearman rho / p | not computable |
  | per kind | none |

- Interpretation: Not computable. The leakage question is open. E00 did show that ids are
  a dense 1..189,579 sequence in file order with kinds interleaved (first response at
  R0053433, first recovered_text at R0062486), so id order is some kind of ordering. It
  is unknown whether it follows time, crawl order or chain order.
- Decision / next step: Leakage stays untested. If a time signal is recovered later
  (e.g. from text), re-run E02 unchanged on it before using id order in any comparison.

---

### Corpus change: Swarm Traces -> collusion.wiki export  (2026-11-07 21:42 IST)
- What changed: The project corpus moves from the Swarm Traces redacted release
  (data/raw/redacted.jsonl.gz) to the collusion.wiki export (data/raw/collusion/,
  expanded from full-wiki-logs.zip). The goal is now content-only recovery of time order
  and copy/mutation lineage in this agent message board, validated against the true
  revision timestamps, which are hidden from the method.
- Change from the original ground truth: source (1) "payloads with time estimates" is
  replaced by the export's own revision timestamps. Sources (2) version tags and (3)
  numbered command sequences belonged to the Swarm Traces corpus and are dropped with it.
- Why: E00-E02 found 0 timestamps across 189,579 Swarm Traces rows, so source (1) did not
  exist there. The follow-up plan to pull timestamps and version markers out of the
  payload text (E03/E04, including a narrowed version that left out credentials,
  embedded encoded blobs and agent names) was stopped by safety classifiers before any
  code ran. E03/E04 were never run and have no results.
- What is kept: E00-E02 stay as the motivating result (no usable time signal in the
  public Swarm Traces release). All hard rules and the experiment protocol are unchanged.
  Collusion experiments are numbered from E20.

### E20 - collusion.wiki export profile and slim Parquet  (2026-11-07 21:42 IST)
- Question: What is in the export (manifest, pages, revisions, events, labels), and does it
  have enough timed revision histories to serve as ground truth for content-only ordering?
- Hypothesis / expected: From a first look at manifest.json: date cut
  revision.write_date >= 2026-05-01; 14,591 revisions on 4,579 pages across 4 wikis (dse
  13,403); 5,217 delete events; all manifest self-checks passing. Revisions carry a
  `time` field in ISO-8601 UTC ("...Z"), so the parse rate should be close to 100%. Most
  pages are expected to have only 1-2 revisions, so the 200-page threshold for 5+
  revisions is the uncertain part. Revisions have `diff_base`; it is expected to point to
  the previous revision of the same page.
- Go / no-go criterion (pre-registered): GO if at least 5,000 revisions have a parseable
  timestamp AND at least 200 pages have 5 or more revisions. Otherwise NO-GO for this
  corpus as an ordering benchmark.
- Method: Read manifest.json first; record the cut, counts and every self-check. For each
  data file record fields, types, presence and non-null rates and distinct counts;
  examples (truncated to 80 chars) go only to an untracked file. Revisions: parse `time`
  and report format, parse rate, span, time_grade mix and a daily histogram; revisions per
  page and per label (distribution only); check whether diff_base points to the same
  page's previous seq; text length percentiles; distinct exact texts by body_sha256 (and
  verify the hash). Pages later deleted: share of held pages with a delete event after
  their first revision, cross-checked against pages.n_deletions. Write
  data/interim/collusion_slim.parquet.
- Code: experiments/E20_profile.py @ 674419c
- Params: example truncation 80 chars; value counts only for low-cardinality categorical
  fields (<= 30 distinct, excluding names, labels, IPs, free text); GO thresholds 5,000
  revisions and 200 pages with >= 5 revisions; seed 42 (no sampling).
- Results: (results/E20_profile.json, figures/E20_daily_revisions.png)

  | item | value |
  |---|---|
  | manifest | generated 2026-09-03T03:42:36Z; cut revision.write_date >= 2026-05-01; counts revisions 14,591, pages 4,579, labels 3,103 |
  | manifest self-checks | 122 / 122 ok |
  | SHA256SUMS | 5 / 5 files verified |
  | files (rows, bytes) | pages 4,579 (2,973,326); revisions 14,591 (41,521,492); events 19,913 (8,543,896); labels 3,103 (1,471,940); plain .jsonl |
  | wikis (revisions) | dse 13,403; probier 1,013; fractal 169; dorfwiki 6 |
  | timestamp field | revisions.time, ISO-8601 UTC "...Z" on 14,591 / 14,591; parsed 14,591 (100%) |
  | time grade | reqlog 14,482; rclog 103; write_date 6; uncertainty_seconds = 1 on all rows |
  | span | 2026-05-24T06:02:19Z to 2026-07-02T17:51:22Z (39.5 days); revisions on 28 distinct days |
  | revisions per page | median 1, p75 2, p95 8, p99 28, mean 3.19, max 2,327; pages >= 2: 1,453; >= 5: 453; >= 10: 195; >= 20: 80; >= 50: 16; 8,927 revisions sit on pages with >= 5 |
  | revisions per label | 3,102 non-blank labels + 899 blank-label revisions; median 2, p95 14, p99 36, max 317; labels >= 5 revisions: 722; top 10 labels hold 10.6% of labelled revisions |
  | prev link | diff_base on 10,012 of 10,029 revisions with seq > 1, always = same page's seq-1; 17 null (earlier revisions not published); seq 1 never has a diff_base |
  | seq vs time | seq contiguous on all 4,579 pages; 4,562 start at seq 1; of 10,012 consecutive pairs time increases in 9,783, ties in 229, decreases in 0 |
  | text length (chars) | min 0, p5 27, p25 326, median 1,092, p75 2,986.5, p95 5,642, p99 7,635.8, max 38,832; 77 empty bodies |
  | exact texts | 11,867 distinct body_sha256 over 14,591 revisions; 291 hashes on > 1 page, covering 1,767 revisions; 1,317 within-page repeats; recomputed UTF-8 SHA-256 matches body_sha256 on 14,340 |
  | deletions | 5,217 delete events, 3,969 on held pages; 3,898 / 4,579 held pages (85.1%) deleted after their first revision; equals pages with n_deletions > 0 (3,898); deleted_live is false on all pages |
  | slim Parquet | data/interim/collusion_slim.parquet, 14,591 rows, 18 columns, 2,516,883 bytes |

  GO: yes (14,591 >= 5,000 timed revisions; 453 >= 200 pages with >= 5 revisions).
- Interpretation: The export is internally consistent: all 122 manifest checks pass, the
  checksums verify, page revision counts agree with pages.n_revs on every page, and
  delete-event counts agree with pages.n_deletions. Timestamps are complete and precise
  (1 s), so the ground truth is strong. Activity is bursty: the figure shows most
  revisions between 16 and 22 June 2026. Histories are long-tailed: most pages have a
  single revision and one page has 2,327, so per-page results will need weighting or
  capping. Three things are order leaks and must be hidden from any content-only method:
  seq, rev_id (which ends in "@seq") and diff_base all encode within-page order exactly
  (seq never disagrees with time). request_time, success_time, write_date and archived_at
  are further time fields. The 251 hash mismatches equal the manifest's non-ASCII body
  count (250 UTF-8 + 1 Latin-1), which suggests the stored hash is over the original
  bytes; this was not checked row by row. "Deleted" here means a logged admin deletion;
  deleted_live is false everywhere, so pages were apparently restored or kept in the
  archive, and the field's exact meaning is unconfirmed. Cross-page exact copies exist
  (291 texts shared by more than one page), which is direct evidence of copying for the
  lineage part.
- Decision / next step: GO. Use the collusion export as the benchmark. Before any method
  experiment, define the hidden-field list (time and all time-like fields, seq, rev_id
  suffix, diff_base, diff_base_reason, hunks, archived_at) and the evaluation units
  (within-page order on pages with >= 5 revisions; cross-page copy direction). Stop here
  for review.

---

### Corpus change #2: collusion.wiki -> Moltbook for method development  (2026-11-07 22:19 IST)
- What changed: The collusion.wiki analysis (E21: leakage audit and baselines) was stopped
  by safety classifiers before any code ran; E21 has no code or results. E20 is kept as a
  profile-only result. New plan: develop and freeze the method on a benign agent corpus,
  Moltbook (SimulaMet/moltbook-observatory-archive, public, Hugging Face, MIT licence).
  The user then runs the frozen pipeline blind on collusion.wiki themselves.
- Ground truth: Moltbook post creation times (created_at), hidden from the method.
- Architecture rule (all new code): every corpus goes through an adapter that outputs one
  standard table: doc_id, text, group_id, author_id, t. Only src/evaluate.py may read t;
  method code takes a table without t. src/adapters/collusion_wiki.py is a stub mapping
  page_id->group_id, label->author_id, body->text, time->t.
- Note on order: before writing the adapter, the dataset's file listing, README and the
  schema of one small posts file were inspected (no statistics computed). The listing is
  re-recorded by E30.
- Kept: all hard rules and the protocol. Moltbook experiments are numbered from E30.

### E30 - Moltbook profile and 300k-post sample  (2026-11-07 22:19 IST)
- Question: Is the Moltbook archive a usable development corpus: enough timestamped posts,
  enough prolific agents, and enough duplicated / near-duplicated text to study copying?
- Hypothesis / expected: The listing shows 220 daily posts files (1.74 GB) and 217 comments
  files (0.96 GB). The README says posts are near-complete to end of March 2026 and that
  some tables are backfilled, so the same post id may appear in several daily files; posts
  are deduplicated by id (latest dump kept) before counting. Expected: well over 100k
  posts with created_at; many agents with 20+ posts; a noticeable duplicate rate, since
  agent posting is often templated.
- Go / no-go criterion (pre-registered): GO if at least 100,000 posts with a parseable
  timestamp, AND at least 1,000 agents with 20 or more posts, AND an exact-or-near
  duplicate rate of at least 1%. Exact duplicate rate = share of posts whose normalised
  text (adapter text, whitespace collapsed, lower-cased) hash occurs more than once. Near
  duplicates are measured in E31; for E30 the exact rate alone decides the third
  criterion, and if it is below 1% the criterion is reported as undecided until E31.
- Method: List all files and sizes. Download posts and comments (comments are under 2 GB).
  Read posts file by file (column subset), deduplicate by id, then report fields, types
  and null rates, created_at parse rate and span, posts per agent (agent_id), posts per
  submolt, exact duplicate rate, and text length percentiles. Comments: row count, id
  dedup, timestamp parse rate and span only. Write data/interim/moltbook_slim.parquet with
  a 300,000-post random sample (seed 42) through src/adapters/moltbook.py.
- Code: experiments/E30_profile.py @ 7879fa0 (first launch failed on a missing python-dateutil
  in the isolated interpreter before reading any data; dependency installed, same code re-run)
- Params: sample 300,000 drawn without replacement from deduplicated posts with a
  parseable created_at, seed 42; adapter text = title + blank line + content; exact
  duplicate rate computed over posts with non-empty normalised text (empty texts would all
  collide); GO thresholds 100,000 / 1,000 agents with >= 20 posts / 1%.
- Results: (results/E30_profile.json)

  | item | value |
  |---|---|
  | listing | 990 files, 2,726,655,750 bytes; posts 220 files / 1,742,133,398 B; comments 217 / 959,325,583 B; agents 207 / 20,297,460 B; others small |
  | downloaded | posts and comments (comments < 2 GB) |
  | posts schema | id, agent_id, agent_name, submolt, title, content, url (str); score, comment_count, is_pinned (int); created_at, fetched_at (UTC timestamp); dump_date (str); nulls: agent_id 16, agent_name 16, submolt 2, others 0 |
  | dedup | 3,602,713 rows across files, 3,602,713 unique ids, 0 dropped |
  | created_at | parsed 3,602,713 (100%); 2026-01-27T18:01:13Z to 2026-09-11T16:03:58Z (226.9 days); Feb 1,630,146, Mar 732,648, Apr 403,985, then declining to Sep 39,271 |
  | posts per agent | 181,589 agents; median 4, p95 48, p99 221, max 46,575; >= 20 posts: 23,513; >= 100: 4,087; top 10 agents 7.8% of posts |
  | posts per submolt | 7,458 submolts; median 2, p99 1,417.6, max 2,213,800; top 10 submolts 84.5% of posts |
  | exact duplicates | 3,602,666 non-empty posts, 3,317,748 distinct texts; 336,995 posts in 52,077 duplicate groups (rate 9.35%); largest group 15,930; 33,948 groups with >= 2 authors covering 255,812 posts |
  | text length (chars) | p5 77, p25 108, median 356, p75 722, p95 2,329, p99 4,356, max 40,302 |
  | id format | 3,602,713 / 3,602,713 UUID-shaped (no numeric ids) |
  | comments | 2,553,100 rows, all unique ids; created_at parsed 99.999% (33 missing); 2026-02-02 to 2026-09-11 |
  | sample | data/interim/moltbook_slim.parquet: 300,000 posts from a pool of 3,602,713, standard columns, 102,516,315 bytes |

  GO: yes (3,602,713 >= 100,000; 23,513 >= 1,000; 9.35% >= 1%).
- Interpretation: A large, fully timestamped corpus with heavy copying: about one post in
  eleven shares its exact text with another post, and most duplicate groups span more than
  one author, so cross-author copying is common. Activity is concentrated in February
  2026 and in a few submolts (one holds 2.2M posts), so group_id is very unbalanced. Ids
  are UUID-shaped; whether they are random (v4) or time-ordered was not checked and should
  be audited before ids are trusted as opaque. The README's backfill note did not produce
  duplicate post ids in this release.
- Decision / next step: GO. Run E31 (copy-direction pilot) on the 300k sample.

### E31 - Copy-direction pilot on near-duplicate posts  (2026-11-07 22:54 IST)
- Question: For near-duplicate Moltbook posts written by different authors, can content
  alone tell which post came first, better than a length heuristic?
- Hypothesis / expected: Rule (c) is expected to land close to rule (b), so a NO-GO is
  the likely outcome. Reason, noted before running: for a pair with shingle sets A and B,
  containment(A in B) = |A∩B|/|A| and containment(B in A) = |A∩B|/|B| share the same
  numerator, so "A is more fully contained" holds exactly when |A| < |B|. Rule (c) is
  therefore "the post with fewer distinct shingles came first", which differs from (b)
  (character length) only where distinct-shingle count and character length disagree.
  Both are expected to be above 50% if copies tend to add text; (a) is expected near 50%.
  The rule is run as specified; this is recorded so the outcome is not read as a surprise.
- Go / no-go criterion (pre-registered): GO if (c) beats (b) by at least 5 percentage
  points in pairwise accuracy, with non-overlapping bootstrap 95% CIs, on at least 500
  scored pairs.
- Method: Public table only (doc_id, text, group_id, author_id) from the 300k sample;
  t read only by src/evaluate.py for scoring. 5-word shingles (lower-cased word tokens);
  MinHash (128 permutations, seed 42) + LSH (threshold 0.5) for candidate pairs; keep
  pairs with different, non-null authors; compute exact Jaccard; exact duplicates (same
  normalised text) are counted and excluded; keep 0.5 <= Jaccard <= 0.95. Pairs with equal
  timestamps are excluded and counted. Predict which post came first with (a) random,
  (b) the longer post is later, (c) containment rule; ties in (b)/(c) broken at random
  (seed 42). Score pairwise accuracy with a pair-level bootstrap 95% CI (1,000 resamples,
  used for GO). Secondary, not used for GO: a bootstrap over connected components of the
  pair graph, since pairs sharing documents are not independent; and the agreement rate
  between (b) and (c).
- Code: experiments/E31_copy_direction_pilot.py, src/copydir.py @ 10d6367 (see implementation note)
- Params: shingle k = 5 words; num_perm 128; LSH threshold 0.5; Jaccard window
  [0.5, 0.95]; cap of 20,000,000 different-author candidate pairs (uniform subsample, seed
  42, only if exceeded); 1,000 bootstrap resamples; seed 42.
- Implementation note (written 2026-11-07 23:03 IST, before any E31 result exists): the first launch
  at 5349d4f was stopped by the environment's low-memory guard while computing MinHash; it
  wrote no results. Diagnostics using text only (no times) showed the cause: shingles held
  as Python strings, plus large templated clusters (largest LSH bucket 8,882 posts; band
  sum of C(n,2) = 381,518,142). Changes, none to the method, window, cap or GO rule:
  (1) shingles stored as sorted 32-bit blake2b hashes in a flat array, so Jaccard is
  computed on hashed shingles (collisions negligible at these set sizes); (2) MinHash
  computed with datasketch's legacy arithmetic and its seed-42 permutations, but with
  blake2b-32 shingle hashes instead of sha1-32; LSH uses datasketch's (bands, rows) =
  (25, 5) for threshold 0.5, with banding done in numpy; (3) the different-author filter
  is applied while pairs are generated, so same-author pairs are never stored; (4) the
  20,000,000 cap is applied exactly as pre-registered (uniform subsample, seed 42) if the
  different-author pairs exceed it; only if more than 60,000,000 pairs accumulate does the
  run fall back to a seeded per-pair Bernoulli sample at rate 20,000,000 / band-sum bound,
  and the results record which path ran; (5) exact-duplicate pairs are counted
  analytically from text-hash groups (all pairs and different-author pairs) as well as
  within the generated pairs. Verified on 3,000 texts: the sampled generator at rate 1.0
  reproduces the unsampled different-author pair set exactly (7,811 pairs).
- Results: (results/E31_copy_direction_pilot.json)

  | item | value |
  |---|---|
  | docs / with shingles | 300,000 / 299,959 |
  | LSH band-sum bound | 381,518,142 |
  | pair path | bernoulli_fallback (memory guard of 60,000,000 different-author pairs tripped on the exact path); sampling rate 0.0524 |
  | different-author candidate pairs (sampled) | 10,808,912 (below the 20,000,000 cap, no further subsample) |
  | exact-duplicate pairs (analytic, whole sample) | 2,115,898 total; 1,983,717 different-author |
  | exact-duplicate pairs excluded (in sampled pairs) | 104,013 |
  | non-exact Jaccard > 0.95 / < 0.5 | 32,324 / 2,310,745 |
  | pairs in [0.5, 0.95] | 8,361,830; 1 dropped for equal times; scored 8,361,829 |
  | distinct docs / components in scored pairs | 62,111 / 1,198 |
  | Jaccard of scored pairs | p5 0.500, p25 0.538, median 0.538, p75 0.583, p95 0.636 |

  | method | accuracy | pair bootstrap 95% CI | ties (random) | component bootstrap 95% CI (secondary) |
  |---|---|---|---|---|
  | (a) random | 0.5000 | 0.4997 - 0.5004 | - | 0.4989 - 0.5012 |
  | (b) longer is later | 0.6961 | 0.6958 - 0.6964 | 1,396,762 | 0.4743 - 0.7199 |
  | (c) containment | 0.5902 | 0.5898 - 0.5905 | 4,360,308 | 0.4665 - 0.6675 |

  Agreement (b) vs (c): 68.7%. GO: no (margin c - b = -10.6 points; CIs do not show c above b).
- Interpretation: NO-GO, as anticipated in the hypothesis, and more clearly than
  expected: containment is 10.6 points below the length rule. The reason is visible in the
  ties: under (c) 52% of scored pairs (4,360,308 / 8,361,829) have equal shingle-set sizes
  and fall to a coin flip, because the pairs are dominated by fixed-length templates whose
  Jaccard sits at the bottom of the window (median 0.538). Character length still
  separates many of those pairs. On a pair basis, "the longer post is later" is right
  69.6% of the time. The pairs are far from independent: 8.36M pairs come from only 62,111
  posts in 1,198 connected components. Under the secondary component bootstrap the CIs
  for (b) (47.4%-72.0%) and (c) (46.6%-66.8%) both include 50%, so neither rule is shown to
  beat chance once cluster dependence is accounted for. The pair-level CIs used for GO
  are therefore over-confident. The pre-registered exact path could not run: the
  different-author pairs exceeded the 60M memory guard, so the logged Bernoulli fallback
  was used.
- Decision / next step: NO-GO for containment as a copy-direction signal. The length
  baseline is the reference to beat, but its advantage is not robust to cluster
  dependence. Before any further method work, the evaluation should change so that
  template clusters do not dominate: e.g. cap pairs per component or per document, score
  per component, and report component-level CIs as primary. That is a new
  pre-registration, not a change to E31. Stop here for review.

### E32 - Copy direction v2: cluster-level scoring and edit-based cues  (2026-11-07 23:21 IST)
- Question: Once template clusters cannot dominate the score, does an edit-based cue
  (extension, or insertion vs deletion) tell which of two near-duplicate posts came first
  better than "the longer post is later"? Separately: are Moltbook post ids UUID v7
  (time-ordered), which would make doc_id an order leak?
- Hypothesis / expected: NO-GO, derived before running. Both cues, as specified, reduce
  to comparing token counts:
  (ii) for a word-level diff from A to B with m matched tokens, inserted = |B| - m and
  deleted = |A| - m, so inserted - deleted = |B| - |A|. "More inserted than deleted means
  later" is exactly "more tokens means later".
  (i) the common prefix + suffix length L is the same seen from either post, so
  kept(A in B) = L/|A| > kept(B in A) = L/|B| exactly when |A| < |B| (if L > 0); when L = 0
  it is a tie (coin flip).
  So (ii) is the token-count version of (b), and (i) is (ii) with extra coin flips on
  pairs that share no prefix or suffix. Expected: (ii) close to (b), (i) at or below
  (ii), neither 5 points above (b). Ids: expected UUID v4 (random), in which case nothing
  changes.
- Go / no-go criterion (pre-registered): GO if (i) or (ii) beats (b) by at least 5
  percentage points in component-level (macro) accuracy, with that method's component
  bootstrap 95% CI excluding (b)'s point estimate (CI lower bound above it), on at least
  200 scored components. Otherwise NO-GO, and the content-only dating claim is dropped.
- Method:
  Pairs: reuse the 8,361,829 scored different-author near-duplicate pairs from E31
  (data/interim/E31_pairs.parquet; Jaccard 0.5-0.95, exact duplicates excluded). Connected
  components are computed over all of them. Template filter: a component is dropped if
  every one of its pairs (before capping) has equal shingle-set sizes; the count of
  dropped components and their pairs is reported. Cap: at most 20 pairs per remaining
  component, chosen uniformly at random (seed 42).
  Methods (public table only; ties broken at random, seed 42, counts reported):
  (a) random; (b) longer-is-later (characters); (i) extension: tokens = lower-cased word
  tokens; L = longest common prefix + longest common suffix (suffix limited so the two do
  not overlap in the shorter post); the post with the larger L / own token count came
  first; (ii) insertion vs deletion: difflib SequenceMatcher on token lists (autojunk off);
  inserted = tokens only in B (insert + replace opcodes), deleted = tokens only in A
  (delete + replace); if inserted > deleted predict A first, if fewer predict B first.
  Scoring (src/evaluate.py, the only reader of t): per-component accuracy = mean over its
  capped pairs; primary = macro mean over components with a component bootstrap 95% CI
  (1,000 resamples, seed 42); secondary = micro accuracy over capped pairs. Pairs with
  equal timestamps are dropped and counted.
  UUID audit: version nibble and variant of every post id in the full archive (3,602,713
  ids, raw id column only). If more than 50% are v7, also report Spearman rho between the
  48-bit embedded timestamp and t on the 300k sample, and add doc_id to the hidden list.
- Code: experiments/E32_copy_direction_v2.py, src/copydir.py, src/evaluate.py @ 150a817
- Params: pairs from E31; cap 20 pairs per component; template-filter rule as above;
  1,000 component bootstrap resamples; GO margin 5 points; minimum 200 components; v7
  threshold 50%; seed 42.
- Results: (results/E32_copy_direction_v2.json)

  | item | value |
  |---|---|
  | UUID audit | 3,602,713 ids, all version 4 (random); variant chars 8/9/a/b in near-equal shares; v7 share 0 |
  | input | 8,361,829 pairs over 62,111 posts in 1,198 components |
  | template filter | 651 components dropped (all pairs equal shingle-set size), holding 9,167 pairs |
  | after cap (20 per component) | 547 components, 1,767 pairs; 0 dropped for equal time; pairs per component min 1, median 1, max 20 |

  | method | macro accuracy | component bootstrap 95% CI | micro | ties (random) |
  |---|---|---|---|---|
  | (a) random | 0.5105 | 0.4763 - 0.5439 | 0.4946 | - |
  | (b) longer is later | 0.4964 | 0.4607 - 0.5332 | 0.5020 | 266 |
  | (i) extension | 0.5081 | 0.4717 - 0.5457 | 0.4935 | 870 |
  | (ii) insertion vs deletion | 0.5055 | 0.4699 - 0.5406 | 0.4782 | 551 |

  Diagnostics: (ii) agrees with the token-count rule on 100% of pairs without a token-count
  tie (551 ties); agreement (i) vs (ii) 75.0%, (b) vs (ii) 72.3%.
  GO: no. Margins over (b): (i) +1.2 points, (ii) +0.9 points; neither CI lower bound is
  above (b)'s point estimate.
- Interpretation: NO-GO. Once each cluster counts once, every rule, the length baseline
  included, is indistinguishable from chance: all four CIs cover 50%. E31's 69.6% for
  "longer is later" came almost entirely from a few very large components; capped at 20
  pairs each they no longer dominate, and most remaining components contribute a single
  pair. The 100% agreement between (ii) and the token-count rule confirms the derivation
  in the hypothesis: the insertion/deletion cue is a length rule. The extension cue adds
  coin flips on the 870 pairs with no shared prefix or suffix. Post ids are random UUID
  v4, so doc_id does not leak order and nothing is added to the hidden list.
- Decision / next step: Per the pre-registered rule, the content-only dating claim is
  dropped. Near-duplicate copy direction on Moltbook cannot be recovered from length or
  edit-direction cues at the cluster level. Any further work needs a cue that does not
  reduce to comparing lengths, and a new pre-registration. Stop here for review.

### E33 - Moltbook agents subset: fields and owner linkage  (2026-11-07 23:26 IST)
- Question: What fields does the agents subset have, how complete are they, and how are
  agents linked to owners (how many agents per owner)?
- Hypothesis / expected: Schema of one file (names and types only, inspected before
  writing this entry): id, name, description, karma, follower_count, following_count,
  is_claimed, owner_x_handle, first_seen_at, last_seen_at, created_at, avatar_url,
  dump_date. Files are daily snapshots, so agents repeat across files and are deduplicated
  by id (latest dump kept). Expected: an owner handle on a minority of agents (claimed
  ones), and a heavy-tailed agents-per-owner distribution with some owners running many
  agents.
- Go / no-go criterion (pre-registered): GO for using owner linkage in later experiments
  if at least 10% of deduplicated agents have an owner handle AND at least 100 owners
  have 2 or more agents.
- Method: Download the agents subset. Report every field's presence and non-null rate and
  types, over rows and over deduplicated agents. Privacy rule: example values (truncated
  to 80 chars) are shown only for an allow-list of non-personal fields (id, karma,
  follower_count, following_count, first_seen_at, last_seen_at, created_at, dump_date).
  Every other field, including owner_x_handle, is_claimed, name, description, avatar_url
  and any field not seen in the inspected schema, gets counts only: agents with a value,
  distinct values, and length stats for free text. Owner linkage: handles normalised
  (strip, lower-case, leading @ removed); count agents with a handle, distinct owners,
  agents-per-owner distribution, and a cross-tab with is_claimed. Raw handles are never
  written or printed. For later use, data/interim/moltbook_agent_owner.parquet (untracked)
  holds agent_id and owner_key = HMAC-SHA256(salt, normalised handle), truncated to 16 hex
  chars; the salt is 32 random bytes in data/interim/owner_salt.bin (untracked, not
  seeded, so the keys cannot be rebuilt from public handles). Before saving, the script
  checks that no result string equals any raw handle or agent name.
- Code: experiments/E33_agents_fields.py, src/hf_download.py @ b9a761e (first run at 8da3bf9
  crashed while writing owner keys because missing handles arrived as NaN; nothing was
  saved or printed; fixed and re-run)
- Params: example allow-list as above; truncation 80 chars; GO thresholds 10% and 100
  owners; seed 42 (no sampling).
- Results: (results/E33_agents_fields.json)

  | field | rows non-null rate | dedup non-null | type | shown |
  |---|---|---|---|---|
  | id | 100% | 182,860 | str (UUID) | examples |
  | name | 100% | 182,860 | str | counts only |
  | description | 99.7% | 182,356 | str | counts only |
  | karma | ~100% | 182,859 | double in 74 files, int64 in 133 | median 0, p95 20, p99 205, min -286,181, max 235,871 |
  | follower_count | 100% | 182,860 | int64 | median 0, p99 20, max 8,096 |
  | following_count | 100% | 182,860 | int64 | median 1, p99 5, max 5,977 |
  | is_claimed | 100% | 182,860 | int64 | counts: 1 = 129,268; 0 = 53,592 |
  | owner_x_handle | 30.4% | 55,551 | str | counts only |
  | first_seen_at | 60.2% | 110,144 | UTC timestamp | 2026-01-30 to 2026-09-11 |
  | last_seen_at | 60.3% | 110,262 | UTC timestamp | 2026-02-08 to 2026-09-11 |
  | created_at | 70.7% | 129,295 | UTC timestamp | 2026-01-27 to 2026-08-06 |
  | avatar_url | 0.5% | 960 | str | counts only |
  | dump_date | 100% | 182,860 | str | examples |

  Files 207; rows 182,906; unique agents 182,860 (46 repeat rows dropped); no fields outside
  the inspected schema.
  Owner linkage: 55,551 agents with a handle (30.4%), 55,541 distinct owners; agents per
  owner: 1 for 55,531 owners, 2 for 10 owners (max 2; 20 agents under multi-agent owners).
  Cross-tab: every agent with a handle is claimed (55,551); 73,717 claimed agents have no
  handle; 53,592 unclaimed agents have none. Leak check: 0 hits. Owner keys (HMAC, salted)
  written to data/interim/moltbook_agent_owner.parquet for 55,551 agents (untracked).
  GO: no (share 30.4% >= 10%, but only 10 owners have >= 2 agents, below 100).
- Interpretation: Owner handles are almost one-to-one with agents, so in this export an
  owner key identifies a single agent and adds nothing beyond author_id for grouping. This
  is consistent with one agent per X account on the platform, but that was not verified.
  The handle is missing for 73,717 claimed agents, so absence of a handle does not mean
  unclaimed. Timestamps on agents are incomplete (60-71%), unlike post created_at (100%).
  karma changes type across files (double vs int64) and has extreme negative values.
- Decision / next step: NO-GO for owner linkage as a grouping signal. The salted owner keys
  stay available in data/interim but are not planned for use. Stop here for review.

### E37 - Metadata-only monitor pilot for coordinated posting  (2026-11-07 23:50 IST)
- Question: Can a monitor that sees no text (only posting times and account metadata)
  separate authors who take part in multi-author exact-duplicate posting from organic
  authors, and how quickly does it degrade when the coordinated authors jitter their
  timestamps?
- Hypothesis / expected: Synchrony and burstiness features should separate the classes
  (AUROC above 0.75) and beat karma alone. Jitter should erode recall at 1% FPR quickly
  once it exceeds the 60 s synchrony window. Known confound, stated before running:
  organic authors need >= 20 posts while coordinated authors can have one post, so
  interval and hour-entropy features partly encode activity level. Two diagnostics (not
  used for GO) measure this: a post-count-only model, and a matched re-run in which
  coordinated authors also need >= 20 posts.
- Go / no-go criterion (pre-registered): GO if the gradient-boosted model (primary,
  fixed now) reaches test AUROC >= 0.75 AND its group-bootstrap 95% CI lower bound is
  above the karma-only model's test AUROC point estimate. Logistic regression is reported
  alongside but does not decide GO.
- Method:
  Labels (content used only here, then discarded): every Moltbook post (3,602,713) gets
  the E30 normalised-text hash (whitespace collapsed, lower-cased, blake2b-64; empty
  texts ignored). Within each hash group, sorted by time, any 24-hour window that holds
  posts by >= 3 distinct authors marks all posts in it. An author is coordinated if any
  of their posts is marked. Organic = >= 20 posts and no marked post. Other authors are
  excluded. Seeded sample: at most 10,000 authors per class (seed 42). After labels and
  groups are built, text and hashes are dropped; only author ids, timestamps and agent
  metadata go into features.
  Groups: authors are linked if they share any exact-duplicate text (any hash with >= 2
  authors); connected components are the groups. Train/test split 70/30 by group
  (GroupShuffleSplit, seed 42), so no duplicate cluster spans both sides.
  Features (no text, nothing derived from text): synchrony from all posts by other
  authors: share of the author's posts with >= 1 other-author post within +/-60 s,
  mean log1p count of such posts, and mean ratio of that count to the expected count from
  the global posting rate in the same UTC hour; intervals between the author's posts:
  median and mean log interval, coefficient of variation, burstiness (sd-mean)/(sd+mean),
  share of intervals < 60 s, minimum interval; UTC hour-of-day entropy (normalised by
  log 24); account created_at clustering from the agents table: log1p count of other agents
  created within +/-60 s and within +/-1 h (missing flag if created_at is absent); karma
  (signed log1p), follower_count and following_count (log1p). Post count is NOT a
  feature, except in the post-count diagnostic.
  Models: HistGradientBoostingClassifier (default parameters, random_state 42; handles
  missing values natively); logistic regression (median imputation + missing indicators,
  standard scaling, max_iter 2,000). Baselines: random scores (seed 42); karma-only
  logistic regression on signed log1p karma + missing flag.
  Metrics on the test set: AUROC and recall at 1% FPR (threshold = 99th percentile of the
  organic test scores), each with a 95% CI from 1,000 bootstrap resamples of test groups
  (threshold recomputed in each resample).
  Evasion test: for jitter J in {0, 1, 5, 30, 120} minutes, every post of a coordinated
  test author is shifted by U(-J, +J) minutes (seed 42). Their posts are replaced in the
  global timeline, features are recomputed, and the trained models are re-scored. Recall
  at 1% FPR uses the unchanged organic threshold, with a group-bootstrap CI. Plotted to
  figures/E37_jitter_recall.png.
- Architecture note: this is a detection task, not a dating task, so posting time is the
  monitor's input by design and the "t is hidden" rule does not apply. The hidden quantity
  is the label, built from content in src/labels.py; monitor features come from
  src/monitor.py, which never receives text. E37 reads all raw posts (not the 300k sample)
  through the Moltbook adapter's author_id / text helpers.
- Code: experiments/E37_metadata_monitor_pilot.py, src/labels.py, src/monitor.py @ 03149e7
- Params: 24 h window, >= 3 authors; organic >= 20 posts; <= 10,000 authors per class;
  +/-60 s synchrony; 70/30 group split; 1,000 group-bootstrap resamples; jitter
  {0, 1, 5, 30, 120} min; scikit-learn 1.9.1; seed 42 everywhere.
- Results: (results/E37_metadata_monitor_pilot.json, figures/E37_jitter_recall.png)

  | item | value |
  |---|---|
  | posts / authors | 3,602,697 / 181,589 |
  | marked posts | 210,886 |
  | coordinated / organic authors | 59,127 (6,987 with >= 20 posts) / 16,526 |
  | sample | 10,000 coordinated + 10,000 organic; all 20,000 found in the agents table |
  | train | 7,260 authors, 496 coordinated, 6,837 groups |
  | test | 12,740 authors, 9,504 coordinated, 2,931 groups |
  | groups on both sides | 0 |
  | feature missingness | interval features 11.9%, cv / burstiness 15.4%, created_at clustering 42.6%, others 0% |

  | model (test) | AUROC | 95% CI (group bootstrap) | recall at 1% FPR | 95% CI |
  |---|---|---|---|---|
  | gradient-boosted trees (primary) | 0.9605 | 0.9549 - 0.9980 | 0.8594 | 0.8541 - 0.9899 |
  | logistic regression | 0.9215 | 0.9191 - 0.9896 | 0.6662 | 0.6451 - 0.9383 |
  | random | 0.5009 | 0.4648 - 0.5132 | 0.0105 | 0.0000 - 0.0180 |
  | karma only | 0.5886 | 0.5740 - 0.6691 | 0.0022 | 0.0000 - 0.0113 |
  | diagnostic: post count only | 0.9482 | 0.9292 - 0.9857 | 0.8825 | 0.4598 - 0.8926 |

  Matched diagnostic (coordinated authors also >= 20 posts; 121 train / 1,117 test
  coordinated): gradient-boosted AUROC 0.7220 (CI 0.6606 - 0.9892), recall 0.1397; logistic
  AUROC 0.6551 (CI 0.6100 - 0.9895), recall 0.1379.
  Largest standardised logistic coefficients: iv_mean_log +5.82, iv_median_log -3.95,
  sync_mean_log1p +1.72, burstiness -1.11, iv_share_lt_60s +0.91.
  Jitter (recall at 1% FPR, fixed organic threshold), 0 / 1 / 5 / 30 / 120 min:
  gradient-boosted 0.859 / 0.863 / 0.860 / 0.858 / 0.855; logistic 0.666 / 0.676 / 0.654 /
  0.636 / 0.588.
  GO (pre-registered rule): yes. AUROC 0.9605 >= 0.75 and CI lower bound 0.9549 > karma-only
  0.5886.
- Interpretation: The pre-registered rule is met, but the result does not support a
  metadata monitor for coordination, for three reasons visible in the same run.
  (1) Activity confound: post count alone reaches AUROC 0.948, close to the full model's
  0.960. With activity matched, the model falls to 0.722 (logistic 0.655), below the 0.75
  bar, with recall at 1% FPR around 0.14. The interval features at the top of the
  logistic model mostly encode how many posts an author has.
  (2) Unbalanced group split: coordinated authors are tied into large duplicate-sharing
  components, so the group split put 9,504 of the coordinated authors in test and only
  496 in train. The models learned coordination from about 500 examples, and the test is
  dominated by a few large groups. That shows in the bootstrap CIs, where the point
  estimate sits at the bottom edge of the interval (e.g. 0.9605 in 0.9549 - 0.9980). These
  CIs do not measure generalisation uncertainty well.
  (3) Jitter barely moves the gradient-boosted recall (0.859 to 0.855 at +/-120 min). The
  primary model therefore does not rely on the 60 s synchrony signal the monitor was
  meant to test; it relies on per-author activity patterns that jitter does not change.
  The logistic model, which weights synchrony more, loses about 8 points by 120 min.
  The earlier pattern holds: Moltbook exact-duplicate posting happens mostly in short
  bursts by low-activity accounts.
- Decision / next step: Formally GO, but not adopted as evidence for a metadata monitor;
  the matched diagnostic (0.722) is below the GO bar. A follow-up needs a new
  pre-registration that (a) defines both classes with the same activity floor (e.g. >= 20
  posts) as the primary analysis, (b) splits by group with class stratification and
  isolates or holds out the largest components separately, and (c) reports synchrony-only
  features as their own model, so the jitter test measures what it is meant to. Stop here
  for review.

---

### Final scope  (2026-11-08 00:50 IST)
- Paper direction, fixed now: (1) a pre-registered negative result: content-only cues
  (length, containment, extension, insertion vs deletion) do not recover copy direction
  between near-duplicate agent posts once clusters are scored properly (E31, E32);
  (2) a cluster-aware evaluation lesson for agent-corpus forensics: pair-level or
  author-level evaluation of clustered agent text inflates estimates and false-positive
  rates (E34, E35, E38 vs E37). No new hypotheses about dating are added.
- Remaining work: E38 (monitor, activity-matched), E34 (inflation curve), E35 (null
  simulation), E36 (frozen replication script, Moltbook only), FIG1 (combined figure).

### E38 - Metadata monitor, activity-matched, with feature-set ablation  (2026-11-08 00:50 IST)
- Question: With both classes at the same activity floor, and a split that respects
  duplicate-sharing components, does a metadata-only monitor detect coordinated authors,
  and which feature family carries the signal?
- Hypothesis / expected: E37's matched diagnostic (AUROC 0.722, recall at 1% FPR about
  0.14) suggests NO-GO on recall. Expected: (a) full AUROC near 0.7; (c) activity-only
  close to (a); (b) synchrony-only weaker; (d) creation clustering and (e) karma near
  chance. Jitter should hurt (b) more than (a).
- Go / no-go criterion (pre-registered): "a metadata monitor works" if feature set (a)
  with gradient-boosted trees reaches pooled out-of-fold AUROC >= 0.75 AND pooled
  out-of-fold recall at 1% FPR >= 0.30. Numbers are reported either way.
- Method: Labels and components exactly as in E37 (24 h window, >= 3 authors; components
  from any shared exact-duplicate text). Population: coordinated authors with >= 20 posts
  and organic authors (>= 20 posts, no marked post); up to 5,000 per class (seed 42).
  Held-out set: components ranked by the number of sampled authors (ties by component
  id); the top 1% of components that contain sampled authors (rounded up) are held out
  and reported on their own. The rest goes to StratifiedGroupKFold (5 folds, shuffle,
  seed 42; groups = components, strata = class).
  Feature sets (no text): (a) full = synchrony (3) + post count (log1p) + interval stats
  (7) + hour entropy + creation clustering (3) + karma / followers / following; (b)
  synchrony-only (the 3 features within +/-60 s); (c) activity-only = post count (log1p) +
  the 7 interval stats; (d) creation clustering only (3); (e) karma only. Each set uses
  HistGradientBoostingClassifier (defaults, random_state 42); logistic regression on (a)
  is secondary.
  Metrics: per fold, AUROC and recall at 1% FPR (threshold from that fold's organic
  scores), as mean +/- sd; pooled out-of-fold predictions with a group-bootstrap 95% CI
  (1,000 resamples). Held-out: each set refit on all cross-validation authors; recall at
  the threshold from pooled out-of-fold organic scores; AUROC against held-out organic
  authors if there are >= 20 of them, otherwise against pooled out-of-fold organic scores
  (reported which).
  Jitter on (a) and (b): J in {0, 1, 5, 30, 120} min; every post of every sampled
  coordinated cross-validation author is shifted by U(-J, +J) min (seed 42) in the global
  timeline; their timeline features are recomputed and scored by the fold model in which
  they were test; pooled recall at the fixed J = 0 pooled organic threshold, with a
  group-bootstrap CI.
- Code: experiments/E38_monitor_matched.py, src/monitor_data.py @ 01d35b4
- Params: >= 20 posts both classes; <= 5,000 per class; top 1% components held out; 5 folds;
  1,000 bootstrap resamples; jitter {0, 1, 5, 30, 120} min; seed 42.
- Results: (results/E38_monitor_matched.json)

  | item | value |
  |---|---|
  | population | coordinated >= 20 posts 6,987; organic 16,526; sampled 5,000 + 5,000 |
  | components with sampled authors | 4,866 |
  | held out (top 1% = 49 components) | 5,177 authors, 4,987 coordinated; component sizes 2 to 4,262 |
  | cross-validation | 4,823 authors, **13 coordinated**, 4,817 components |

  | feature set (GBT) | fold AUROC mean +/- sd | fold recall mean +/- sd | pooled AUROC [95% CI] | pooled recall at 1% FPR [CI] | held-out AUROC | held-out recall |
  |---|---|---|---|---|---|---|
  | (a) full | 0.703 +/- 0.132 | 0.067 +/- 0.149 | 0.691 [0.563, 0.821] | 0.077 [0.000, 0.250] | 0.529 | 0.073 |
  | (b) synchrony | 0.520 +/- 0.246 | 0.000 +/- 0.000 | 0.485 [0.273, 0.714] | 0.000 [0.000, 0.000] | 0.537 | 0.011 |
  | (c) activity | 0.656 +/- 0.212 | 0.067 +/- 0.149 | 0.634 [0.437, 0.811] | 0.077 [0.000, 0.250] | 0.583 | 0.018 |
  | (d) creation | 0.570 +/- 0.079 | 0.000 +/- 0.000 | 0.524 [0.391, 0.666] | 0.000 [0.000, 0.000] | 0.411 | 0.004 |
  | (e) karma | 0.583 +/- 0.153 | 0.000 +/- 0.000 | 0.549 [0.358, 0.720] | 0.000 [0.000, 0.000] | 0.518 | 0.000 |
  | (a) logistic (secondary) | 0.665 +/- 0.197 | 0.067 +/- 0.149 | 0.659 [0.515, 0.793] | 0.077 [0.000, 0.250] | - | - |

  Held-out AUROC is against the 190 held-out organic authors. Jitter (pooled recall at
  the fixed threshold, 0 / 1 / 5 / 30 / 120 min): (a) 0.077 / 0.154 / 0.077 / 0.077 / 0.077;
  (b) 0 at every level.
  GO: no (pooled AUROC 0.691 < 0.75; recall 0.077 < 0.30).
- Interpretation: NO-GO, but the cross-validation part is uninformative. The
  pre-registered hold-out rule (top 1% of components by sampled authors) removed almost
  every coordinated author, because activity-matched coordinated authors sit mostly in one
  duplicate-sharing component of 4,262 sampled authors. Cross-validation therefore had 13
  positives; its CIs are very wide and the jitter results move in steps of one author.
  The held-out set is the substantive test: 4,987 coordinated vs 190 organic authors,
  scored by models trained on those 13 positives. There, no feature set exceeds AUROC
  0.583 and recall at 1% FPR stays at or below 0.073. Synchrony alone (b) is at chance
  in both parts. Together with E37's matched diagnostic (0.722, trained on 121
  activity-matched positives), the evidence does not support a metadata-only monitor for
  this kind of coordination on Moltbook. The large drop from E37's headline 0.960 is the
  evaluation lesson: E37's number came from activity differences and an unbalanced split.
- Decision / next step: NO-GO for "a metadata monitor works". No re-run with a changed
  hold-out rule within this scope (that would be a new pre-registration). The degenerate
  split is itself reported as a cluster-structure finding: on Moltbook, activity-matched
  coordinated accounts collapse into one dominant component.

### E34 - Inflation curve: pair-level vs component-level scoring  (2026-11-08 00:50 IST)
- Question: How much does pair-level scoring inflate the "longer is later" estimate and
  shrink its CI compared with component-level scoring, as the Jaccard window and the
  per-component cap vary?
- Hypothesis / expected: Pair-level accuracy is about 0.70 at cap "none" (E31) and stays
  well above component-level macro accuracy, which is near 0.5 (E32 found 0.496 with the
  template filter). The gap and the CI-width ratio should grow with the cap. The number of
  components (effective sample size) is orders of magnitude below the pair count.
- Criterion (pre-registered, descriptive): inflation is called material if, in the
  0.5-0.95 window at cap "none", pair-level accuracy minus component-level macro accuracy
  is >= 5 points.
- Method: E31's 8,361,829 scored pairs (data/interim/E31_pairs.parquet). Length-rule
  predictions recomputed exactly as in E31 (ties random, seed 42, same pair order), so cap
  "none" at 0.5-0.95 reproduces E31's pair-level accuracy. No template filter in the
  main grid (it isolates the clustering effect); one secondary row repeats the 0.5-0.95
  window with E32's template filter. Windows: Jaccard >= 0.5, >= 0.7, >= 0.9 (all <= 0.95).
  For each window, components are recomputed on that window's pairs. Caps: 1, 5, 20, 100,
  none; at most k pairs per component, chosen with a seeded random key (seed 42). For each
  (window, cap): pair-level accuracy over the capped pairs with a Wald 95% CI (the pair
  bootstrap at this n gives the same width; checked once with 200 resamples at
  0.5-0.95 / none); component-level macro accuracy (mean of per-component accuracy) with
  a component-bootstrap 95% CI (1,000 resamples); raw pair count; number of components
  (effective n); CI-width ratio = component width / pair width. Headline figure:
  figures/E34_inflation_curve.png, pair-level vs component-level estimate against cap,
  one panel per window.
- Code: experiments/E34_inflation_curve.py, src/clusters.py @ 01d35b4 (figure titles and
  legend fixed afterwards and the figure redrawn from the saved results; numbers unchanged)
- Params: windows {0.5, 0.7, 0.9}-0.95; caps {1, 5, 20, 100, none}; 1,000 component-bootstrap
  resamples; seed 42.
- Results: (results/E34_inflation_curve.json, figures/E34_inflation_curve.png)
  Check: cap "none" at 0.5-0.95 reproduces E31's pair-level accuracy (0.6960842); 1,396,762
  length ties; no pairs with equal times. Pair bootstrap (200) CI 0.69578 - 0.69640 vs Wald
  0.69577 - 0.69640.

  | window | cap | pairs | components | pair-level acc [Wald CI] | component macro [bootstrap CI] | inflation (pts) | CI width ratio |
  |---|---|---|---|---|---|---|---|
  | 0.5-0.95 | 1 | 1,198 | 1,198 | 0.501 [0.473, 0.529] | 0.501 [0.473, 0.527] | 0.0 | 1.0 |
  | 0.5-0.95 | 5 | 2,060 | 1,198 | 0.511 [0.490, 0.533] | 0.506 [0.480, 0.530] | 0.5 | 1.1 |
  | 0.5-0.95 | 20 | 3,029 | 1,198 | 0.506 [0.488, 0.524] | 0.504 [0.478, 0.528] | 0.2 | 1.4 |
  | 0.5-0.95 | 100 | 6,063 | 1,198 | 0.503 [0.491, 0.516] | 0.504 [0.477, 0.528] | 0.0 | 2.0 |
  | 0.5-0.95 | none | 8,361,829 | 1,198 | 0.696 [0.696, 0.696] | 0.504 [0.477, 0.528] | 19.2 | 81.0 |
  | 0.7-0.95 | 1 | 482 | 482 | 0.461 [0.416, 0.505] | 0.461 [0.419, 0.504] | 0.0 | 1.0 |
  | 0.7-0.95 | 5 | 831 | 482 | 0.444 [0.410, 0.478] | 0.454 [0.417, 0.495] | -1.0 | 1.2 |
  | 0.7-0.95 | 20 | 1,206 | 482 | 0.453 [0.425, 0.481] | 0.449 [0.412, 0.490] | 0.3 | 1.4 |
  | 0.7-0.95 | 100 | 2,504 | 482 | 0.507 [0.488, 0.527] | 0.450 [0.412, 0.490] | 5.8 | 2.0 |
  | 0.7-0.95 | none | 328,847 | 482 | 0.698 [0.697, 0.700] | 0.450 [0.412, 0.490] | 24.8 | 24.7 |
  | 0.9-0.95 | 1 | 80 | 80 | 0.600 [0.493, 0.707] | 0.600 [0.500, 0.700] | 0.0 | 0.9 |
  | 0.9-0.95 | 5 | 180 | 80 | 0.594 [0.523, 0.666] | 0.598 [0.504, 0.688] | -0.3 | 1.3 |
  | 0.9-0.95 | 20 | 352 | 80 | 0.611 [0.560, 0.662] | 0.610 [0.518, 0.695] | 0.1 | 1.7 |
  | 0.9-0.95 | 100 | 1,016 | 80 | 0.598 [0.568, 0.629] | 0.611 [0.518, 0.698] | -1.3 | 3.0 |
  | 0.9-0.95 | none | 9,431 | 80 | 0.858 [0.851, 0.865] | 0.612 [0.519, 0.699] | 24.6 | 12.7 |

  Secondary (0.5-0.95 with E32's template filter; 651 components / 9,167 pairs dropped;
  547 components): cap 1 / 5 / 20 / 100 / none pair-level 0.492 / 0.495 / 0.505 / 0.507 /
  0.696, macro 0.492 / 0.494 / 0.497 / 0.496 / 0.497; inflation at none 19.9 points; CI
  width ratio 117.0.
  Criterion: material (19.2 >= 5 points).
- Interpretation: Inflation is material in every window: 19.2 to 24.8 points at cap
  "none", with CIs 12.7 to 81 times too narrow. The curve is a step, not a gradual rise.
  At caps up to 100, pair-level and component-level estimates nearly coincide; the jump
  appears only when large components contribute all their pairs. A few big clusters with
  a consistent length pattern produce the whole "effect", and the effective sample size
  is the component count (80 to 1,198), not the pair count (9,431 to 8.4M). The 0.9-0.95
  window gives the highest component-level estimate (0.61, CI 0.52 - 0.70) from only 80
  components; this was not pre-registered as a hypothesis and is not claimed. The
  hypothesis that the gap grows smoothly with the cap was wrong: it is near zero until
  the cap is removed (except 0.7-0.95 at cap 100, 5.8 points).
- Decision / next step: Supports the evaluation lesson. Headline figure produced. No
  further dating analysis (final scope).

### E35 - Null simulation: false-positive rate of naive evaluation  (2026-11-08 00:50 IST)
- Question: Under a known null that keeps the real cluster structure, how often does
  pair-level analysis declare a significant "longer is later" effect, compared with
  component-level analysis?
- Hypothesis / expected: Pair-level analysis will declare significance far more often
  than the nominal 5%, because its CI assumes 8.36M independent pairs; component-level
  analysis should be near 5%.
- Criterion (pre-registered, descriptive): naive evaluation is called miscalibrated if
  its false-positive rate is > 10% while the component-level rate is <= 10%.
- Method: Components over E31's pairs (0.5-0.95 window). In each of 1,000 draws (seed
  42 + r), the true timestamps are permuted among the posts within each component, which
  keeps the cluster structure and destroys any real order signal. Length-rule predictions
  stay fixed. Pair-level: accuracy over all 8,361,829 pairs, Wald 95% CI; significant if
  the CI excludes 0.5. Component-level: the cap-20 pair set from E34 (0.5-0.95, no
  filter, fixed selection), macro accuracy with a component-bootstrap 95% CI (1,000
  resamples); significant if the CI excludes 0.5. Pairs with equal permuted times are
  dropped in that draw. False-positive rates are reported with Wilson 95% CIs, along with
  the spread of each estimate across draws.
- Code: experiments/E35_null_simulation.py, src/clusters.py @ 01d35b4 (results file stamped
  378f8c9: it ran in the same chain after E34, after an unrelated log/figure commit; E35
  code unchanged)
- Params: 1,000 draws; Wald CI (pair-level); 1,000 component-bootstrap resamples; seed 42 + r.
- Results: (results/E35_null_simulation.json)

  | analysis | significant draws / 1,000 | false-positive rate [Wilson 95% CI] | estimate across draws: mean (sd) [2.5-97.5%] |
  |---|---|---|---|
  | pair-level, 8,361,829 pairs, Wald CI | 863 | 0.863 [0.840, 0.883] | 0.4999 (0.0019) [0.4961, 0.5036] |
  | component-level, cap 20 (3,029 pairs, 1,198 components) | 53 | 0.053 [0.041, 0.069] | 0.5005 (0.0127) [0.4762, 0.5251] |

  Pairs with equal permuted times per draw: mean 1.18, max 7. Criterion: naive
  miscalibrated (0.863 > 0.10 while 0.053 <= 0.10).
- Interpretation: Under a null that keeps the real cluster structure and removes any
  order signal, naive pair-level analysis declares a significant "longer is later"
  effect in 86% of draws. The estimate itself is unbiased (mean 0.4999), but it varies
  across draws (sd 0.0019) far more than the Wald CI assumes (its full width at this n is
  about 0.0006, from E34). Component-level analysis is close to nominal (5.3%).
- Decision / next step: Supports the evaluation lesson: in clustered agent text,
  pair-level significance is mostly a false positive. Feeds FIG1.

### E36 - Frozen replication script  (2026-11-08 00:50 IST)
- Question: Can the E31/E32 pipeline be packaged as one frozen script that takes any
  adapter's standard table, and does it reproduce E31/E32 exactly on Moltbook?
- Expected: exact reproduction (same counts, same accuracies and CIs), since every step
  is seeded and uses the same code paths.
- Criterion (pre-registered): reproduction passes if, on data/interim/moltbook_slim.parquet,
  all E31 counts and pair-level results for (a) random, (b) length and (c) containment, and
  all E32 counts and component-level results for (a), (b), (i) extension and (ii)
  insertion vs deletion, match the saved results to within 1e-9.
- Method: experiments/E36_replication.py --table <standard-table parquet>. The parameters
  are frozen in configs/E36_pipeline.json, whose SHA-256 is recorded here after the
  commit. Steps: split_truth (t read only by src/evaluate.py); E31 pair finding (shingle
  hashes, MinHash, banded LSH, different-author pairs, 60M memory guard with seeded
  Bernoulli fallback, 20M cap, Jaccard 0.5-0.95, exact duplicates excluded); E31
  pair-level scoring for (a), (b), (c); E32 component pipeline (union-find, template
  filter, cap 20, macro scoring with a component bootstrap) for (a), (b), (c), (i), (ii).
  Pair-level scoring of (i) and (ii) is new: it uses a seeded uniform subsample of
  200,000 scored pairs (word diffs on all 8M pairs are too slow) and is not part of the
  reproduction check. Run only on the Moltbook table; not run on any other corpus.
- Config SHA-256 (configs/E36_pipeline.json, LF line endings enforced by .gitattributes):
  5ac6686ab5779f23bce7f0c296358873e15f8abfd0c33403ce133ae395e8f017
- Code: experiments/E36_replication.py, configs/E36_pipeline.json @ 01d35b4 (results stamped
  378f8c9-dirty: the run started after an unrelated commit, and the E34 plotting function
  had uncommitted edits when results were saved; E36 code and config unchanged)
- Results: (results/E36_replication_moltbook.json)
  Config SHA-256 in results: 5ac6686ab5779f23bce7f0c296358873e15f8abfd0c33403ce133ae395e8f017
  (matches the value recorded above).
  Reproduction check: 63 items compared (E31 counts and pair-level n / accuracy / CI for
  (a), (b), (c); E32 counts and component-level n / macro / CI / micro for (a), (b), (i),
  (ii)); maximum absolute difference 0.0; passes at 1e-9.
  Pair-level (8,361,829 pairs): (a) 0.5000, (b) 0.6961, (c) 0.5902 (identical to E31).
  New, not part of the check: pair-level on a 200,000-pair seeded subsample: (i) extension
  0.5737 [0.5714, 0.5758], 129,778 ties; (ii) insertion vs deletion 0.5890 [0.5866,
  0.5911], 103,989 ties; component-level (c) containment macro 0.5069 [0.4710, 0.5415] on
  547 components.
  Component-level (547 components, 1,767 pairs): (a) 0.5105, (b) 0.4964, (i) 0.5081,
  (ii) 0.5055 (identical to E32).
- Interpretation: The frozen pipeline reproduces E31 and E32 exactly from the standard
  table alone, so it is ready to be handed over. The new pair-level edit-cue numbers show
  the same inflation pattern: (ii) is 58.9% at pair level and 50.6% at component level.
- Decision / next step: experiments/E36_replication.py with configs/E36_pipeline.json
  (SHA-256 above) is the frozen pipeline. Not run on any other corpus in this repo; the
  collusion.wiki run is left to the user (src/adapters/collusion_wiki.py maps the export
  to the standard table).

### FIG1 - Naive vs proper estimates, dating and monitor tasks  (2026-11-08 00:50 IST)
- What: one two-panel figure built only from saved results. Dating: "longer is later"
  accuracy, naive = E34 pair-level (0.5-0.95, cap none) vs proper = E34 component-level
  macro (0.5-0.95, cap 20). Monitor: AUROC, naive = E37 gradient-boosted (activity
  confounded, unbalanced split) vs proper = E38 feature set (a), pooled out-of-fold. Each
  point has its CI; chance lines at 0.5; E35 false-positive rates are noted in the dating
  panel.
- Change after E38 results, presentation only: the monitor panel note also states the
  number of coordinated authors in E38's cross-validation (13) and the held-out AUROC,
  so the cluster-aware point is not read without that context.
- Code: experiments/FIG1_naive_vs_proper.py; output figures/FIG1_naive_vs_proper.png
  (layout adjusted after the first render for overlapping labels; values unchanged).
- Result: dating panel: naive 0.696 [0.696, 0.696] vs cluster-aware 0.504 [0.478, 0.528];
  null false-positive rates 86.3% vs 5.3%. Monitor panel: naive AUROC 0.960 [0.955, 0.998]
  vs cluster-aware 0.691 [0.563, 0.821] (13 coordinated authors in CV; held-out AUROC
  0.529); recall at 1% FPR 0.86 vs 0.08. All values read from results/E34, E35, E37, E38.
