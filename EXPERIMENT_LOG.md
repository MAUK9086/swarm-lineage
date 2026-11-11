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
- Code: experiments/E00_profile.py @ eb1cb5d
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
- Code: experiments/E01_timestamps.py @ d190204 (re-run at d0695e7 after a metadata-only
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
- Code: experiments/E02_leakage.py @ d190204 (re-run at d0695e7, see E01)
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
- Code: experiments/E20_profile.py @ b34d280
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
- Code: experiments/E30_profile.py @ 08a1b7e (first launch failed on a missing python-dateutil
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
- Code: experiments/E31_copy_direction_pilot.py, src/copydir.py @ 3144a46 (see implementation note)
- Params: shingle k = 5 words; num_perm 128; LSH threshold 0.5; Jaccard window
  [0.5, 0.95]; cap of 20,000,000 different-author candidate pairs (uniform subsample, seed
  42, only if exceeded); 1,000 bootstrap resamples; seed 42.
- Implementation note (written 2026-11-07 23:03 IST, before any E31 result exists): the first launch
  at 2f909c2 was stopped by the environment's low-memory guard while computing MinHash; it
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
- Code: experiments/E32_copy_direction_v2.py, src/copydir.py, src/evaluate.py @ a59faca
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
- Code: experiments/E33_agents_fields.py, src/hf_download.py @ aaf7e3c (first run at 6e14b07
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
- Code: experiments/E37_metadata_monitor_pilot.py, src/labels.py, src/monitor.py @ 19fe8af
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
- Code: experiments/E38_monitor_matched.py, src/monitor_data.py @ fa88267
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
- Code: experiments/E34_inflation_curve.py, src/clusters.py @ fa88267 (figure titles and
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
- Code: experiments/E35_null_simulation.py, src/clusters.py @ fa88267 (results file stamped
  e499ba6: it ran in the same chain after E34, after an unrelated log/figure commit; E35
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
- Code: experiments/E36_replication.py, configs/E36_pipeline.json @ fa88267 (results stamped
  e499ba6-dirty: the run started after an unrelated commit, and the E34 plotting function
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

---

### Scope amendment: E41 lineage tree  (2026-11-08 20:14 IST)
- E41 tests a lineage-order hypothesis (does a near-duplicate tree recover time order?).
  The Final scope entry said no new hypotheses about dating would be added; E41 is added
  at the user's explicit request and is recorded here as an amendment. It is analysed
  under the same cluster-aware rules (component-level primary, naive pair-level shown
  only for contrast, a within-cluster null for false-positive rates).

### E41 - Lineage tree from near-duplicate components  (2026-11-08 20:14 IST)
- Question: Within clusters of near-duplicate posts, does a minimum spanning tree rooted
  by a "features-gained" rule put earlier posts nearer the root, i.e. does tree depth
  recover time order better than chance and better than text length?
- Hypothesis / expected: NO-GO is the expected outcome. The root rule picks the node with
  the highest mean containment C(node in other) = |A and B| / |A|, which is largest for
  small shingle sets, so the root will tend to be the shortest text and depth partly
  tracks distance from the shortest text. E32 / E34 found length near chance at the
  cluster level, so depth is expected near chance too (macro tau CI covering 0). The naive
  pair-level tau is expected to be further from 0 with a far narrower CI, and the null
  should show a high false-positive rate for the naive analysis and about 5% for the
  macro analysis.
- Go / no-go criterion (pre-registered): "a lineage signal exists" if the depth method's
  macro Kendall tau has a component-bootstrap 95% CI that excludes 0 AND its macro tau is
  above the length baseline's macro tau. (A CI entirely below 0 would also exclude 0; that
  case would be reported as a reversed signal, not as support for lineage.)
- Method (frozen in configs/E41_lineage.json; method code in src/lineage.py never reads
  t; all scoring, node times and the null are in src/evaluate.py):
  Nodes: posts in the standard table are collapsed by normalised text (whitespace
  collapsed, lower-cased; empty texts dropped); each node keeps its post count. Node time
  for evaluation = earliest post time among its posts (first appearance of the text).
  Candidate components: 5-word shingles, MinHash (128 permutations, seed 42) and banded
  LSH (threshold 0.5; 25 bands x 5 rows) from E31's code, applied to one representative
  text per node; all nodes sharing any band bucket are joined (union-find over bucket
  members, same and different authors), without listing pairs. This is a deviation from
  "all near-duplicate pairs" forced by scale (E31: up to 381M candidate pair instances,
  most same-author); it is fixed here before running.
  Lineage components: candidate components with >= 5 nodes; if more than 200 nodes, a
  seeded uniform sample of 200 (seed 42). Exact Jaccard (hashed shingles, as in E31) for
  every pair of sampled nodes; edges = pairs with 0.5 <= Jaccard <= 0.95; connected
  pieces of that graph with >= 5 nodes are the lineage components. Counts of candidate
  components, capped components and fragments are reported.
  Tree: minimum spanning tree of each lineage component's edge graph, weight 1 - Jaccard.
  Root = node with the highest mean containment C(node in other) over all other nodes in
  the component (ties random, seed 42). Inferred order = hop depth from the root, ties
  broken by a seeded random key.
  Baseline: length order (shorter representative text earlier, ties random, seed 42).
  Evaluation: Kendall tau-b between inferred order and node time per component. Primary =
  macro mean over components with a component-bootstrap 95% CI (1,000 resamples).
  Naive contrast = pooled pair-level tau over all within-component node pairs (tau =
  2p - 1, p = share of concordant pairs among pairs without tied times) with a Wald CI.
  Null: 1,000 draws (seed 42 + r) permuting node times within each component; for depth
  and length, the false-positive rate of the macro analysis (CI excludes 0) and of the
  naive analysis (Wald CI excludes 0), with Wilson CIs.
  Figure: the 4 largest lineage components drawn as trees (root at top, depth downwards),
  nodes coloured by true time rank within the component (single-hue sequential scale),
  root marked: figures/E41_lineage_trees.png.
- Code: experiments/E41_lineage.py, src/lineage.py, src/evaluate.py, configs/E41_lineage.json @ 0a6d6f0
- Config SHA-256 (configs/E41_lineage.json, LF enforced): 5b6c45ef7d350bcb854e00ed567d13535d5a2f4db374644adebf502ddf45b6db
- Params: see config; corpus = data/interim/moltbook_slim.parquet only; not run on any
  other corpus.
- Results: (results/E41_lineage_moltbook.json, figures/E41_lineage_trees.png)
  Config SHA-256 in results matches. Posts 300,000 (4 empty) -> 284,974 nodes (2,475 with
  more than one post). Candidate components with >= 5 nodes: 700 (86,064 nodes; 17 capped
  at 200). Lineage components: 488 with 8,447 nodes (8,676 posts), 251,194 within-component
  node pairs; component size median 8 (5 to 200); tree max depth median 2 (1 to 24); the
  root was the shortest text in 252 of 488 components.

  | order | macro tau [component bootstrap CI] | naive pooled tau [Wald CI] | null FPR macro | null FPR naive |
  |---|---|---|---|---|
  | depth | 0.098 [0.074, 0.124] | 0.082 [0.078, 0.086] | 0.052 [0.040, 0.068] | 0.716 [0.687, 0.743] |
  | length | 0.057 [0.026, 0.086] | 0.035 [0.031, 0.038] | 0.052 [0.040, 0.068] | 0.707 [0.678, 0.734] |

  Figure components: 200, 200, 198, 174 nodes; depth-vs-time tau (tau-a) +0.29, +0.14,
  +0.02, +0.04.
  GO (pre-registered rule): yes (CI excludes 0; 0.098 > 0.057).
- Interpretation: Met the rule, against the pre-registered expectation. The figure then
  showed leaves in near time order, which pointed to a row-order dependence (see E41b).
  E41b withdrew the GO: with rows shuffled, depth falls to 0.033, below length. The null
  results hold in both runs: the macro analysis is calibrated (about 5% false positives)
  and the naive pooled analysis is not (about 71%).
- Decision / next step: GO withdrawn by E41b (row-order leak). See E41b.

### E41b - Post-hoc leakage check: row order  (2026-11-08 20:20 IST)
- Why (written after seeing E41's result, before this check runs): E41 met its GO rule,
  but its tree figure shows leaves laid out in near time order, because node indices follow
  the standard table's row order and data/interim/moltbook_slim.parquet is stored roughly
  in dump-date order (E30 sampled from a dump-date-sorted pool). The method never reads t,
  but two steps can depend on row order: minimum-spanning-tree tie-breaking among equal
  Jaccard distances (frequent in templated text) and component labelling. If the GO comes
  from row order, it is an artifact.
- Check (post-hoc, not part of E41's pre-registration): shuffle the rows of the standard
  table once (seed 42) into data/interim/moltbook_slim_rowshuffled.parquet and run the
  frozen E41 script unchanged with the same config (--name moltbook_rowshuffled).
- Reading rule, fixed now: if the shuffled run's depth macro tau CI still excludes 0 and
  stays above the length baseline, E41's signal is not a row-order artifact. If the depth
  macro tau falls to the length baseline or to 0, E41's GO is attributed to a row-order
  leak and withdrawn.
- Code: experiments/E41_lineage.py (unchanged) @ 0a6d6f0; shuffle step recorded in results.
- Results: (results/E41_lineage_moltbook_rowshuffled.json, figures/E41b_lineage_trees_rowshuffled.png)
  Shuffle: data/interim/moltbook_slim_rowshuffled.parquet = the same 300,000 rows,
  pandas sample(frac=1, random_state=42). Same config SHA-256. 489 lineage components,
  8,454 nodes, 253,356 node pairs (one more component than E41: candidate-component
  sampling depends on node indices).

  | order | macro tau [CI] | naive pooled tau [CI] | null FPR macro | null FPR naive |
  |---|---|---|---|---|
  | depth | 0.033 [0.006, 0.063] | 0.004 [-0.000, 0.008] | 0.049 | 0.714 |
  | length | 0.050 [0.021, 0.083] | 0.048 [0.044, 0.052] | 0.058 | 0.708 |

  Figure components: 200, 200, 195, 182 nodes; depth-vs-time tau-a +0.016, -0.014, +0.011,
  -0.023. The frozen script writes its figure to a fixed path, so the shuffled run's figure
  was renamed to E41b_lineage_trees_rowshuffled.png and the original was restored from
  commit fc7e973.
- Interpretation: The depth signal is mostly a row-order artifact. With the rows in
  random order, depth's macro tau falls from 0.098 to 0.033 and goes below the length
  baseline (0.050), which barely moves (0.057 -> 0.050) because it does not depend on node
  indices. The mechanism matches the hypothesis behind the check: many equal Jaccard
  distances in templated clusters, so scipy's spanning tree breaks ties by index, and
  index order followed time order in the stored table. Length's small positive macro tau
  (CI excluding 0 in both runs) is an unregistered observation and is not claimed.
- Decision / next step: Per the reading rule fixed before the check, E41's GO is
  withdrawn; the lineage claim is not supported. Lesson for the paper and for the frozen
  pipelines: a dataset-agnostic script must not inherit row order from the adapter. Any
  future version of E41 (and, for safety, E36) should shuffle rows with a seeded
  permutation inside the script, under a new config hash. Neither script was changed here.
  The user's planned collusion.wiki run should not use E41 as it stands: the collusion
  adapter orders revisions by page and sequence, which is time order within each page.

---

### Amendment: frozen pipelines v2 (E36-v2, E41-v2)  (2026-11-09 09:46 IST)
- Reason: (1) E41b showed a row-order leak: E41's result depended on the row order of
  the standard table, which followed time in the stored Moltbook sample. (2) Corpora
  differ structurally: on Moltbook group_id is a submolt (2,628 distinct in the 300k sample,
  1 missing), on collusion.wiki it is a page, so copying within a group and copying across
  groups are different phenomena and should be reported separately.
- Changes, both scripts: (a) seeded row shuffle of the standard table before any
  processing, using pandas DataFrame.sample(frac=1, random_state=42) followed by a reset
  index (the same call as E41b); (b) a pair_scope option with values all, within_group and
  cross_group; every run reports all three. The v1 scripts and configs stay frozen and
  unchanged; v2 is new files that import v1's functions so shared logic stays identical.
- E36-v2 scope rule: a scored pair is within_group if both docs have the same non-missing
  group_id, cross_group otherwise (pairs with a missing group_id count as cross_group and
  are counted). Pair finding runs once; each scope filters the scored pairs, then E31
  pair-level scoring and the E32 component pipeline (components recomputed on that scope's
  pairs) run per scope.
- E41-v2 scope rule: applies to the verified edges that build lineage components. Each
  collapsed node has the set of group_ids of its posts; an edge is within_group if the two
  nodes share at least one group_id, cross_group if they share none; all keeps every edge.
  Candidate components, node sampling and the Jaccard matrix are computed once; each scope
  builds its own connected pieces, trees and evaluation, with tree and length random
  generators re-seeded per scope exactly as in v1.
- Pre-registered checks:
  E36-v2 row-order independence (scope all vs E31 / E32). Exact match is NOT expected,
  because the Bernoulli pair sample hashes row indices and the seeded tie-breaks and caps
  follow pair order. Pass requires both: (i) quantities that do not depend on row order
  match exactly: docs, docs with shingles, LSH band-sum bound, pair-generation path, and
  both analytic exact-duplicate pair counts; (ii) sample-dependent estimates agree in
  expectation: component-level macro accuracy for (a), (b), (i), (ii) inside E32's
  component-bootstrap 95% CIs, and pair-level accuracy for (a), (b), (c) within 2
  percentage points of E31 (pair-level CIs are too narrow to use; E35).
  E41-v2 (scope all vs E41b): expected to reproduce E41b exactly, since the shuffle call
  and all seeds are identical; the check passes if depth and length macro tau equal E41b's
  to within 1e-9, and is reported as "in expectation" if they only fall inside E41b's CIs.
  E41-v2 GO: the E41 rule (depth macro tau CI excludes 0 AND depth macro tau > length macro
  tau), with scope all as primary; within_group and cross_group are secondary and
  descriptive.
- Expected: E36-v2 all passes (i) and (ii); within_group and cross_group component-level
  accuracies near chance for all cues. E41-v2 all reproduces E41b (depth 0.033 below
  length 0.050, NO-GO); within_group and cross_group near chance.
- Code: experiments/E36_replication_v2.py, experiments/E41_lineage_v2.py,
  src/lineage.py (new scoped function only) @ 60ccf9d
- Config SHA-256 (LF enforced): configs/E36_pipeline_v2.json =
  fe569c7fa2df1ee30a862fda44a7408d2a4d89fb10a9cd33b2778201375c32f7;
  configs/E41_lineage_v2.json =
  d315478469faf5999d69aa304c12975d09f0f8ef1d3bc6172d60cb26197254ba
- Corpus: data/interim/moltbook_slim.parquet only.
- Results: (results/E41v2_lineage_moltbook.json, results/E36v2_replication_moltbook.json,
  figures/E41v2_trees_moltbook_{all,within_group,cross_group}.png)
  Runs at 60ccf9d (E36-v2 stamped 60ccf9d-dirty: src/adapters/collusion_wiki.py was being
  edited by the user during the run; E36-v2 code and config unchanged). Config SHA-256 in
  both results files match the values above.

  E41-v2 (Moltbook): 700 candidate components, 17 capped; verified edges all 203,811,
  within 193,691, cross 10,120; 156 nodes carry more than one group.

  | scope | components / nodes | depth macro tau [CI] | length macro tau [CI] | depth naive tau [CI] | null FPR macro / naive (depth) | GO |
  |---|---|---|---|---|---|---|
  | all | 489 / 8,454 | 0.033 [0.006, 0.063] | 0.050 [0.021, 0.083] | 0.004 [-0.000, 0.008] | 0.049 / 0.714 | no |
  | within_group | 453 / 7,993 | 0.020 [-0.009, 0.051] | 0.034 [0.005, 0.066] | 0.013 [0.009, 0.017] | 0.054 / 0.711 | no |
  | cross_group | 76 / 1,026 | 0.024 [-0.048, 0.097] | 0.091 [-0.003, 0.184] | -0.099 [-0.111, -0.086] | 0.048 / 0.704 | no |

  Check vs E41b: all-scope depth and length macro and naive tau identical (difference
  0.0), 489 components in both: exact reproduction, passes.

  E36-v2 (Moltbook): pairs scored 8,360,718 (E31: 8,361,829); within_group 5,740,400;
  cross_group 2,620,318; no missing groups.

  | scope | pairs / components scored | pair-level (b) | component (a) | component (b) [CI] | component (c) | component (i) | component (ii) [CI] |
  |---|---|---|---|---|---|---|---|
  | all | 8,360,718 / 559 | 0.696 | 0.500 | 0.565 [0.530, 0.601] | 0.557 | 0.546 | 0.557 [0.523, 0.595] |
  | within_group | 5,740,400 / 578 | 0.645 | 0.507 | 0.558 [0.525, 0.592] | 0.552 | 0.557 | 0.562 [0.531, 0.596] |
  | cross_group | 2,620,318 / 69 | 0.807 | 0.474 | 0.518 [0.423, 0.624] | 0.5125 | 0.590 | 0.585 [0.485, 0.692] |

  Row-order check (scope all vs E31 / E32): (i) exact items all match (docs 300,000; 299,959
  with shingles; band-sum bound 381,518,142; bernoulli_fallback; exact-duplicate pairs
  2,115,898 and 1,983,717): PASS. (ii) pair-level within 2 points of E31: (a) +0.003,
  (b) +0.009, (c) +0.037 points: pass; component-level inside E32's CIs: (a) 0.500 inside;
  (b) 0.565 outside [0.461, 0.533]; (i) 0.5458 outside [0.4717, 0.5457]; (ii) 0.557 outside
  [0.470, 0.541]: FAIL. Overall: FAIL.
- Interpretation:
  E41-v2 behaves as pre-registered: the all scope reproduces E41b exactly and no scope
  shows a lineage signal (NO-GO in all three). In the cross_group scope the naive pooled
  tau is significantly negative (-0.099) while the macro tau is near 0, another case of
  naive pooling giving a confident wrong-signed answer.
  E36-v2 fails its pre-registered row-order check on the component-level estimates. The
  pair-level estimates and all row-order-free quantities agree with E31, but E32's
  component-level length accuracy (0.496) becomes 0.565 [0.530, 0.601] after the shuffle.
  The likely cause is the Bernoulli pair sample, not a systematic order effect: on
  Moltbook only about 5% of candidate pairs are kept, and the kept set (hashed on row
  indices) changes with row order. That changes which components exist and which pairs
  represent them, and the component bootstrap CI does not include that sampling
  variation. Supporting evidence (from the user's collusion.wiki runs below, which use the
  exact pair path with no sampling): v1 and v2 give the same counts and component-level
  length accuracy 0.8924 vs 0.8925. This is not proven by one shuffle on Moltbook.
  Consequences: (1) E32's NO-GO stands under v2: the edit cues do not beat length by 5
  points ((ii) 0.557 vs (b) 0.565). (2) The statement "length is at chance at the cluster
  level on Moltbook" (E32, E34) is not robust: under v2 it is 0.565, CI excluding 0.5.
  (3) The inflation lesson stands but its size depends on the pair sample: pair-level 0.696
  vs component-level 0.565 under v2 (13 points), vs 19 points with E31's sample (E34).
- Decision / next step: v2 scripts and configs are the frozen versions going forward
  (E41 v1 should not be used). The E36-v2 check failure is reported as is. To separate
  pair-sampling variance from order effects would need a new pre-registration: several
  shuffle seeds (or several Bernoulli salts) on Moltbook, reporting the spread of the
  component-level estimates. Not run here.

### Held-out runs on collusion.wiki (run by the user)  (2026-11-09 11:17 IST)
- Provenance: run by the user outside this session, as planned in "Corpus change #2".
  The user extended src/adapters/collusion_wiki.py (stub replaced: reads
  data/interim/collusion_slim.parquet from E20; doc_id <- rev_id, text <- body, group_id <-
  page_id, author_id <- label, with blank labels replaced by "blank_" + rev_id, t <- t_utc)
  and wrote data/interim/collusion_standard.parquet (14,591 rows). The adapter does not
  shuffle rows; the v2 scripts shuffle internally. Runs: E36 v1, E36-v2, E41 v1, E41-v2,
  all at 60ccf9d with the adapter edit uncommitted (stamped 60ccf9d-dirty); config SHA-256
  in the results match the frozen configs (v1 5ac6686a / 5b6c45ef, v2 fe569c7f / d3154784).
  E41 v1 carries the E41b row-order risk (revisions are stored in page / sequence order).
  The analysis below reads only the aggregate results files; no raw data was opened.
- Pre-registered rules applied (fixed earlier, unchanged): copy-direction GO (E32): an edit
  cue beats "longer is later" by >= 5 points at component level with its CI lower bound
  above the length point estimate. Lineage GO (E41): depth macro tau CI excludes 0 AND
  depth macro tau > length macro tau.
- Results: (results/E36_replication_collusion_wiki.json, results/E36v2_replication_collusion_wiki.json,
  results/E41_lineage_collusion_wiki.json, results/E41v2_lineage_collusion_wiki.json)
  Pair finding (identical in v1 and v2): 14,591 docs (14,514 with shingles); exact pair path
  (no sampling); 276,415 different-author candidate pairs; 221,509 exact-duplicate pairs
  excluded; 36,735 in window, 24 with equal times, 36,711 scored over 8,214 docs.

  E36 copy direction (component level, cap 20, template filter):

  | run / scope | pairs / components | pair-level (b) | (a) random | (b) length [CI] | (c) containment | (i) extension | (ii) ins/del |
  |---|---|---|---|---|---|---|---|
  | v1 all | 36,711 / 1,140 | 0.774 | 0.5125 | 0.8924 [0.878, 0.907] | 0.887 | 0.879 | 0.889 |
  | v2 all | 36,711 / 1,140 | 0.771 | 0.510 | 0.8925 [0.878, 0.907] | 0.889 | 0.879 | 0.889 |
  | v2 within_group | 27,504 / 1,115 | 0.837 | 0.503 | 0.941 [0.929, 0.952] | 0.942 | 0.9395 | 0.942 |
  | v2 cross_group | 9,207 / 297 | 0.5747 | 0.545 | 0.659 [0.614, 0.703] | 0.634 | 0.6105 | 0.640 |

  E41 lineage (macro Kendall tau [component-bootstrap CI]):

  | run / scope | components / nodes | depth | length | depth naive pooled | null FPR macro / naive (depth) | GO |
  |---|---|---|---|---|---|---|
  | v1 all | 379 / 4,883 | 0.692 [0.652, 0.731] | 0.757 [0.717, 0.793] | 0.472 | 0.048 / 0.581 | no |
  | v2 all | 373 / 4,845 | 0.694 [0.654, 0.731] | 0.764 [0.727, 0.800] | 0.495 | 0.041 / 0.593 | no |
  | v2 within_group | 314 / 4,246 | 0.797 [0.762, 0.831] | 0.867 [0.836, 0.899] | 0.507 | 0.069 / 0.589 | no |
  | v2 cross_group | 80 / 866 | 0.138 [0.075, 0.202] | 0.3745 [0.298, 0.453] | 0.015 | 0.059 / 0.670 | no |

  E41 nodes: 11,819 (465 with more than one post; 77 empty posts); root was the shortest
  text in 325 of 379 (v1) and 326 of 373 (v2, all) components.
- Interpretation:
  Copy direction: NO-GO under the pre-registered rule; no edit cue beats length (within
  1.4 points of it overall and within pages; 1.9 to 4.9 points below it across pages). But unlike Moltbook, "longer is later" is strongly right on
  collusion.wiki: 0.89 at component level overall and 0.94 within a page. Within a page this
  mostly reflects how a wiki works: successive saves of one page usually add text, so it is
  page growth, not copying between agents. Across pages (the closer analogue of copying),
  length is right in 0.659 [0.614, 0.703] of components, clearly above chance; the edit cues
  are no better. The algebraic equivalence of (c), (ii) and length (E31 / E32 notes) shows
  again: they track (b) closely.
  Lineage: NO-GO in every run and scope, because depth is below the length baseline, but
  both are strongly positive within pages (depth 0.80, length 0.87) and weaker but still
  positive across pages (depth 0.14, length 0.37). The tree adds nothing beyond length.
  Evaluation lesson again: the null keeps the macro analysis near 5% false positives while
  the naive pooled analysis is at 55-67%; and the naive pooled tau differs from the macro
  tau by up to 0.29 (within-page depth: 0.507 vs 0.797), in both directions (cross-page
  length: naive 0.495 above macro 0.3745).
  Robustness: v1 and v2 agree closely here (same pair counts; component-level length 0.8924
  vs 0.8925; lineage depth 0.692 vs 0.694), so the E41 v1 row-order risk did not materially
  affect this corpus, and with no pair sampling the copy-direction pipeline is effectively
  order-independent (see the E36-v2 discussion above).
- Decision / next step: Report collusion.wiki as the held-out corpus: copy-direction and
  lineage methods give NO-GO under the frozen rules; length alone orders wiki revisions
  well within pages and moderately across pages; the cluster-aware evaluation stays
  calibrated on a second corpus. The adapter change is committed with these results.

### E42 - Pair-sample sensitivity of copy-direction estimates (Moltbook)  (2026-11-09 11:47 IST)
- Question: How much do the component-level copy-direction estimates depend on which 5.2%
  Bernoulli sample of candidate pairs is drawn? E32 (one sample) gave length 0.496, E36-v2
  (another sample, via a row shuffle) gave 0.565 [0.530, 0.601]; the component bootstrap
  CI does not include pair-sampling variance.
- Hypothesis / expected: The spread across samples is comparable to the gap between E32
  and E36-v2, so a single sample cannot settle whether length is above chance on Moltbook.
- Reading rule (pre-registered): if all 4 seeds give a length component-level CI lower bound
  above 0.5, report "length weakly orders Moltbook copies" with the across-seed range;
  otherwise report "unresolved; sample-dependent" with the range. Anchor check: seed 42
  reproduces E31's pair sample, so its component-level results must equal E32 within 1e-9.
- Method: Moltbook 300k sample, rows in stored order (as E31). Shingle hashes, MinHash
  (seed 42) and the LSH band bound computed once. For seeds 42, 43, 44, 45: different-author
  Bernoulli pair sample at E31's fallback rate (20,000,000 / band bound), exact Jaccard,
  exact duplicates excluded, window 0.5-0.95, equal-time pairs dropped; pair-level accuracy
  for random, length, containment with Wald CIs (no 8M-pair bootstrap, to save time); the
  frozen E32 component pipeline (template filter, cap 20, component bootstrap) for random,
  length, containment, extension, insertion vs deletion. Across seeds: mean, sd, range.
- Code: experiments/E42_pair_sample_sensitivity.py @ 4e28b77 (results stamped 979f89c: report scripts were committed during the run; E42 code unchanged)
- Params: seeds 42-45; config configs/E36_pipeline.json (v1); MinHash seed 42.
- Results: (results/E42_pair_sample_sensitivity.json)
  Rate 0.0524 (band bound 381,518,142). Seed 42 reproduces E32 exactly (all compared
  component-level values within 1e-9: pass).

  | seed | pairs scored | components / scored | pair-level length | random | length [CI] | containment | extension | ins/del |
  |---|---|---|---|---|---|---|---|---|
  | 42 | 8,361,829 | 1,198 / 547 | 0.6961 | 0.5105 | 0.4964 [0.4607, 0.5332] | 0.5069 | 0.5081 | 0.5055 |
  | 43 | 8,361,974 | 1,162 / 545 | 0.6960 | 0.4877 | 0.5277 [0.4941, 0.5616] | 0.5258 | 0.5285 | 0.5366 |
  | 44 | 8,359,102 | 1,157 / 547 | 0.6961 | 0.4894 | 0.4946 [0.4560, 0.5305] | 0.5196 | 0.4987 | 0.5051 |
  | 45 | 8,361,597 | 1,177 / 539 | 0.6959 | 0.4978 | 0.5048 [0.4687, 0.5382] | 0.5060 | 0.5303 | 0.5127 |

  Across seeds (component level): length mean 0.5059, sd 0.0152, range 0.4946-0.5277, 0 of 4
  seeds with CI lower bound above 0.5; containment mean 0.5146; extension 0.5164; ins/del
  0.5150 (1 of 4 seeds with CI above 0.5); random mean 0.4964. Pair-level length mean
  0.6960, sd 0.0001.
  Reading (pre-registered rule): "unresolved; sample-dependent".
- Interpretation: Across four fresh pair samples, cluster-level "longer is later" on
  Moltbook is centred near chance (mean 0.506) and never significantly above it; E36-v2's
  0.565 is the high end of a five-sample range of 0.495-0.565. The pair-sampling spread
  (sd 0.015 over four samples, 7 points over five) is comparable to the component-bootstrap
  CI half-width (about 0.035), so a single sample's CI understates the total uncertainty.
  Pair-level accuracy is the same in every sample (0.696, sd 0.0001): stable, and wrong
  about the cluster-level quantity. No cue is consistently above length.
- Decision / next step: Report Moltbook cluster-level length as near chance and
  sample-dependent (0.49-0.57 over five samples), not as a robust signal. E32's
  conclusion stands; E36-v2's higher value is attributed to pair-sampling variation.

### Repository note: history rewrite  (2026-11-09 12:40 IST)
- Git history was rewritten once to remove a tool name from one log line (E31
  implementation note) and from early .gitignore lines, before making the repository
  public. File contents are otherwise unchanged. Commit hashes cited in this log were
  updated to the new hashes; results files keep the hashes recorded at run time, and
  results/hash_map.json maps old to new.

### Report analyses: T01 report numbers, T02 cluster concentration, report figures  (2026-11-09 12:43 IST)
- Purpose: compute every derived number quoted in the final report from saved results,
  and describe how concentrated the Moltbook near-duplicate pairs are. These are
  descriptive analyses with no hypothesis or go/no-go rule, and were not pre-registered.
- Method: T02 reads E31's scored pairs, builds connected components exactly as E34/E35
  do, and reports cluster sizes and the share of pairs held by the largest clusters.
  T01 reads only results/*.json and derives ratios, shares, margins and the report tables
  (results/T01_tables.md: corpora, cue equivalences, pre-registered decisions).
  FIG_report draws the four report figures (figures/R1-R4, PNG and vector PDF).
- Code: experiments/T02_cluster_concentration.py @ 88a1988; experiments/T01_report_numbers.py @ 88a1988;
  experiments/FIG_report.py @ 88a1988
- Results: (results/T02_cluster_concentration.json, results/T01_report_numbers.json)

  | item | value |
  |---|---|
  | Moltbook pairs / clusters / posts in pairs | 8,361,829 / 1,198 / 62,111 |
  | share of pairs in the largest 1 / 2 / 10 clusters | 50.6% / 98.4% / 99.86% |
  | pairs per cluster | median 1, max 4,229,393; 793 clusters with one pair; 13 with >= 1,000 |
  | posts per cluster | median 2, max 24,793 |
  | E35 null: pair-level sd / Wald SE at 0.5 | 0.0019 / 0.000173 (ratio 11.0) |
  | within-group share of scored pairs (E36-v2) | Moltbook 68.7%, collusion.wiki 74.9% |
  | lineage null false-positive range (E41-v2, all corpora and scopes) | naive 55.1-73.4%, cluster-level 4.1-6.9% |
  | Moltbook cluster-level length over five pair samples (E42 + E36-v2) | 0.495-0.565 |

- Interpretation: The pair-level evidence on Moltbook is essentially two clusters, which
  explains the inflation (E34), the false-positive rate (E35) and the sample dependence
  (E42) in one fact. The earlier FIG1 (naive vs proper) is retired from the report: its
  monitor point rested on E38's 13 positives; its message is carried by the new figures.
- Decision / next step: The report quotes only numbers present in results/*.json. The
  public Swarm Traces release appears in the report only as motivation (no timestamps),
  not as an evaluated corpus.

### Report revision after external review  (2026-11-09 12:54 IST)
- T03 (experiments/T03_appendix_trees.py): redraws E41's four largest stored-order trees
  with the v2 figure layout (figures/A1_trees_stored_order.png) from the saved trees and
  the unshuffled table; the per-tree taus (+0.29, +0.14, +0.02, +0.04) match E41's saved
  values. No new analysis.
- T01 tables: the corpora table now reports clusters scored after the template filter for
  both corpora (Moltbook 547 from E32, collusion.wiki 1,140 from E36-v2) instead of a
  median that was not computed for the wiki; the decision ledger now lists every
  pre-registered outcome (adds E20, E30, E33, E41b, E36-v2 check, E41-v2 and both
  held-out runs).
- Not added: a collusion.wiki tree figure. Its four largest within-page trees are flat
  stars with per-tree taus between -0.33 and +0.07; the within-page macro tau of 0.80
  comes from the many small page histories, so the figure would mislead.
- Checked and kept: the null spread ratio is 11.0 (sd 0.0019 vs Wald SE 0.000173 at
  p = 0.5, E35); the lineage-root shares (54% Moltbook, 87% wiki) are from E41-v2.

### E43 - Copy-direction robustness: Jaccard threshold, two-stage bootstrap, author-merged clusters  (2026-11-09 13:25 IST)
- Question: Does the Moltbook copy-direction result (E32: no cue beats length; cluster-level
  length near chance) survive (a) stricter Jaccard lower bounds with components recomputed,
  (b) a CI that also includes pair-sampling variance, and (c) merging clusters that share
  an author?
- Hypothesis / expected: Yes for all three. Stricter thresholds cut chaining but leave
  every cue within a few points of length; the two-stage CI is wider than E32's
  cluster-bootstrap CI by less than half; author merging reduces the number of units and
  widens the CI.
- Go / no-go criterion (pre-registered, robustness reading rule): the negative result is
  called robust if, in every variant, (1) no cue (containment, extension, insertion/deletion)
  passes E32's GO rule against length (margin >= 5 points and CI low above the length
  point), and (2) the cluster-level length 95% CI includes 0.5. Any variant that breaks
  (1) or (2) is reported as such and the report text is weakened accordingly.
- Method: Reads E31's scored pairs. (a) For Jaccard lower bounds 0.5 (anchor), 0.6, 0.7,
  0.8 (upper 0.95): recompute connected components on the kept pairs, apply E32's
  template filter and cap of 20 pairs per cluster, score all cues with the cluster
  bootstrap; record the largest cluster's share of pairs. The 0.5 row must reproduce E32.
  (b) At 0.5: per cluster, all eligible pairs are scored by length and containment;
  two-stage bootstrap = resample clusters, then draw min(20, n) pairs without replacement
  inside each drawn cluster (hypergeometric on the correct count). (c) At 0.5: clusters
  that share any author are merged by union-find; the capped scored pairs are re-grouped by
  merged unit and re-bootstrapped. Truth only via src/evaluate.py.
- Code: experiments/E43_robustness.py @ 3820059
- Params: thresholds 0.5/0.6/0.7/0.8, upper 0.95, cap 20, template filter on, n_boot 1000,
  seed 42.
- Results: (results/E43_robustness.json; anchor row reproduces E32 exactly, 1e-12)

  | Jaccard >= | pairs | clusters scored | largest cluster share | length | containment | extension | ins/del |
  |---|---|---|---|---|---|---|---|
  | 0.5 | 8,361,829 | 547 | 50.6% | 0.496 (0.461-0.533) | 0.507 (0.471-0.542) | 0.508 (0.472-0.546) | 0.505 (0.470-0.541) |
  | 0.6 | 888,672 | 360 | 95.3% | 0.504 (0.456-0.549) | 0.520 (0.470-0.564) | 0.518 (0.471-0.563) | 0.508 (0.462-0.552) |
  | 0.7 | 328,847 | 237 | 96.8% | 0.536 (0.484-0.592) | 0.494 (0.440-0.551) | 0.486 (0.432-0.545) | 0.486 (0.431-0.545) |
  | 0.8 | 115,036 | 92 | 84.2% | 0.551 (0.465-0.637) | 0.539 (0.453-0.627) | 0.510 (0.423-0.597) | 0.532 (0.448-0.622) |

  | variant (Jaccard 0.5) | length | containment |
  |---|---|---|
  | two-stage bootstrap (clusters, then min(20, n) pairs), all 8,352,662 eligible pairs | 0.493 (0.456-0.527), width ratio 0.99 | 0.496 (0.461-0.531), width ratio 0.99 |
  | author-merged units (547 clusters -> 113 units) | 0.507 (0.423-0.585) | 0.509 (0.424-0.592) |

  Largest cue margin over length in any variant: +0.016 (containment, 0.6); author-merged
  extension 0.504, ins/del 0.522 (0.440-0.604). No cue passes the GO rule in any variant;
  the length CI includes 0.5 in every variant. robust_overall = true.
- Interpretation: The Moltbook negative result is robust to the similarity threshold, to
  re-sampling pairs within clusters and to merging clusters that share authors. Stricter
  thresholds do not break up the concentration: one cluster still holds 84-97% of pairs,
  so the concentration is not an artefact of chaining at 0.5. The two-stage CI is no wider
  than the cluster bootstrap, so the choice of 20 pairs inside clusters adds little
  variance; the larger spread in E42 comes from which pairs, and so which clusters, enter
  the Bernoulli sample. Author merging leaves 113 units and widens the CI to about +/-0.08.
- Decision / next step: Report as a robustness paragraph and appendix table. Replace the
  draft's "the cluster bootstrap excludes pair-sampling variance" with the more precise
  statement above.

### E44 - Lineage robustness: sampling and tie-break seeds, depth-only tau-b, depth ties, 200-node cap  (2026-11-09 13:25 IST)
- Question: Is E41-v2's Moltbook lineage result (depth tau below length tau in all three
  scopes; GO not met) stable over the seeds that choose nodes in components over 200 nodes
  and break depth ties, and does it hold when depth ties are kept (tau-b) instead of broken
  at random?
- Hypothesis / expected: Yes. Depth has many ties, so depth-only tau-b will be similar to
  the random-tie-break value; the cap affects only 17 of 700 candidate components.
- Go / no-go criterion (pre-registered, robustness reading rule): robust if, for every seed
  and scope, E41-v2's GO rule fails (CI excludes 0 AND depth above length is not met), and
  depth-only tau-b is below length tau. Any seed/scope that breaks this is reported.
- Method: v2 pipeline (rows shuffled, seed 42 MinHash and LSH buckets unchanged). For seeds
  42-46, the seed sets both the node sample of capped components and the tree/length
  tie-break generators. Per seed and scope: macro Kendall tau and cluster-bootstrap CI for
  depth (random tie-break), depth-only (ties kept, tau-b) and length; share of
  within-component node pairs tied in depth. No null re-runs (E41-v2 calibrated them).
  Seed 42 must reproduce E41-v2 (all scope depth 0.0332, length 0.0501).
- Code: experiments/E44_lineage_robustness.py @ 3820059
- Params: seeds 42-46, n_boot 1000, other parameters from configs/E41_lineage_v2.json.
- Results: (results/E44_lineage_robustness.json; seed 42 reproduces E41-v2 exactly, 1e-12)

  | scope | depth, random tie-break (min-max over 5 seeds) | depth, ties kept (tau-b) | length | pairs tied in depth |
  |---|---|---|---|---|
  | all | 0.002-0.033 | 0.016-0.038 | 0.050-0.062 | 47-48% |
  | within group | 0.012-0.033 | 0.017-0.034 | 0.028-0.045 | 47-48% |
  | across groups | 0.002-0.045 | 0.014-0.077 | 0.037-0.091 | 47-58% |

  E41-v2 GO rule met in 0 of 15 seed x scope runs. Depth tau-b below length in 13 of 15;
  the exceptions are seed 45 within group (0.034 vs 0.031) and seed 44 across groups
  (0.077, CI -0.002 to 0.154, vs 0.037, CI -0.057 to 0.130). Lineage components per seed
  480-491 (all scope); 200-node cap: 17 of 700 candidate components capped, 8,454 of 86,064
  candidate nodes in lineage components at seed 42. robust = false by the pre-registered
  reading rule.
- Interpretation: Trees never pass the pre-registered test, so the NO-GO decision stands.
  The stricter reading "depth below length" fails in 2 of 15 runs, both with overlapping
  intervals and both near zero. On Moltbook, depth and length are both close to zero and
  cannot be separated; the report must not say that trees are below length on Moltbook,
  only that they do not beat it. Seed 42's depth value (0.033) is the highest of five.
- Decision / next step: Weaken the Moltbook lineage wording in the report accordingly.
  The collusion.wiki statement (depth below length) rests on E41-v2 wiki results, which
  were not re-run here.

### E45 - 32-bit shingle-hash collisions  (2026-11-09 13:25 IST)
- Question: How many distinct shingles in the Moltbook 300k sample share a 32-bit hash?
- Hypothesis / expected: About n^2 / 2^33 for n distinct shingles; a negligible share.
- Go / no-go criterion (pre-registered): negligible if fewer than 0.1% of distinct
  shingles are involved in a collision; otherwise report and flag as a limitation.
- Method: For every shingle of every post, compute the 32-bit hash used by the pipeline
  and a 64-bit blake2b hash; count distinct 64-bit values (taken as distinct shingles) and
  distinct 32-bit values among them.
- Code: experiments/E45_hash_collisions.py @ 3820059
- Params: k = 5 words, seed not used (deterministic).
- Results: (results/E45_hash_collisions.json) 25,612,365 distinct shingles; 25,535,954
  distinct 32-bit values; 76,411 lost to collisions (expected n^2/2^33 = 76,368);
  152,674 distinct shingles (0.60%) share a 32-bit value with another. Criterion
  (< 0.1%): not met.
- Interpretation: Collisions occur at the rate expected for 32-bit hashes, and 0.6% of
  distinct shingles are involved, above the pre-registered bar. A collision changes a
  pair's Jaccard only when the two colliding shingles fall in the two texts of the same
  pair, which this count does not measure.
- Decision / next step: State in the limitations that the pipeline uses 32-bit shingle
  hashes, with 0.6% of distinct shingles in a collision; 64-bit hashes are a one-line
  change for future runs. No re-run of the frozen pipelines.

### Report revision after second external review  (2026-11-09 IST)
- Added the robustness analyses E43-E45 (registered above before running) and folded them
  into the report: new Section 4.4, appendix Table 4, and a type column in the decision
  ledger (gating / confirmatory / check / post-hoc / robustness), all generated by
  experiments/T01_report_numbers.py from results/*.json.
- Text changes: the algebra claim is narrowed to the containment and edit cues as
  implemented; the null is described as a conditional permutation null and the 86.3% as the
  type-I rate of the pair-pooled Wald procedure under it; blindness is defined operationally;
  the row-order leak is described as a failure of our implementation; the monitor labels are
  described as a proxy and the monitor is removed from the abstract; the wiki lineage result
  is stated as "some order information, less than length"; following E44 the Moltbook lineage
  result is stated as "trees do not beat length; the two cannot be ordered"; a protocol and
  deviations paragraph and the 200-node cap coverage (Moltbook 8,454 of 86,064 candidate
  texts; wiki 4,845 of 6,536) were added; E45's collision rate is listed as a limitation.
- Figures: two-lane pipeline schematic (R1); Figure 2C labelled by inferential procedure;
  Figure 3 redesigned (length emphasised, wiki cross-page row shaded); Figure 4B notes the
  missing CI. Appendix figure A1 dropped.
- Not done: complete-linkage clustering of the largest cluster (24,793 posts), stated as a
  limitation; no re-run of the metadata monitor.

### E46 - Revision-parent recovery on collusion.wiki (ground truth: diff_base)  (2026-11-09 14:30 IST)
- Question: Time order is not provenance. Where true parent links exist (wiki revisions
  record their diff base), do the text-only lineage trees recover them, and does tree depth
  orient a recovered edge better than length?
- Hypothesis / expected: The minimum spanning tree recovers many true parent edges within
  pages (successive revisions are the most similar texts), well above a random spanning
  tree on the same verified edges. Orientation by tree depth is not better than "shorter is
  parent".
- Go / no-go criterion (pre-registered): (a) structure: MST undirected edge F1 (macro over
  components) exceeds the random-spanning-tree F1 by >= 10 points with the MST CI low above
  the random point; (b) direction: on true edges recovered by the MST, depth orientation is
  correct more often than length orientation by >= 5 points with the depth CI low above the
  length point. Both reported whatever the outcome.
- Method: E41-v2 pipeline on the standard wiki table (rows shuffled, seed 42), scopes all /
  within page / across pages; the method never sees diff_base. Evaluator only: the
  rev_id -> diff_base map from collusion_slim.parquet, mapped to nodes; a true edge is
  eligible if both revisions are in the same scored lineage component and in different
  nodes (exact-duplicate revisions collapse into one node; counted). Predicted edges: MST
  parent links; baselines: random spanning tree of the verified-edge graph (seeded) and
  "length parent" (each node's parent = most similar shorter neighbour among verified edges).
  Metrics per component, macro with cluster bootstrap: undirected precision, recall, F1;
  direction accuracy on recovered true edges; root has no true parent in its component;
  coverage = eligible / all true edges.
- Deviation: collusion.wiki is the held-out corpus; this run is executed by the author
  (not the earlier user-run setup), after the frozen held-out runs. Stated in the report.
- Code: experiments/E46_parent_recovery.py @ 08245e4 (first run @ 3dd6c6a had a bug in
  src/evaluate.py revision_parents: links whose parent is a page's first revision were
  dropped, 8,559 of 10,012 links loaded; fixed before any result was used; numbers below are
  from the corrected run)
- Params: configs/E41_lineage_v2.json; n_boot 1000; seed 42.
- Results: (results/E46_parent_recovery.json; components reproduce E41-v2: 373 / 4,845 nodes)

  Coverage (all scope): 10,012 true links; 3,590 eligible (3,583 node edges in 357
  components); 23 within one node (identical text); 297 across components; 6,102 outside
  scored lineage components (small page histories below 5 texts or outside candidate groups).

  | predicted parent (all scope, macro over 357 components) | precision | recall | F1 | orientation correct | root has no true parent |
  |---|---|---|---|---|---|
  | spanning tree (depth) | 0.675 (0.640-0.707) | 0.761 (0.728-0.788) | 0.699 (0.666-0.730) | 0.920 (0.903-0.937) | 0.913 (0.882-0.944) |
  | most similar shorter text | 0.695 (0.663-0.725) | 0.741 (0.708-0.771) | 0.700 (0.664-0.732) | 0.978 (0.966-0.990) | 0.973 (0.953-0.990) |
  | random spanning tree | 0.293 (0.268-0.316) | 0.343 (0.314-0.371) | 0.305 (0.280-0.330) | 0.463 (0.421-0.505) | 0.238 (0.196-0.283) |
  | length, on the tree's recovered links | | | | 0.959 (0.943-0.973) | |

  Within page: tree F1 0.745 vs random 0.325; orientation 0.923 vs length 0.965. Across
  pages: no true parent link can be a predicted edge (diff_base links are within a page),
  so F1 is 0 for every rule; rule (a) not applicable there.
  Rule (a) structure: GO (all and within page). Rule (b) direction: NO-GO (length 0.04
  above depth).
- Interpretation: Where provenance is known, the text-only trees recover about three
  quarters of true parent links, far above a random tree on the same similarity graph, so
  the structure step works. But the simple rule "parent = most similar shorter text" does
  as well (F1 0.70 vs 0.70), and length orients recovered links better than tree depth.
  This repeats the time-order result with ground-truth provenance: what the tree adds over
  similarity plus length is nothing measurable. Only within-page histories are tested;
  cross-agent copying across pages has no recorded parents.
- Decision / next step: Report as a new results subsection with a table.

### E47 - 64-bit shingle hashes: do the conclusions change?  (2026-11-09 14:30 IST)
- Question: E45 found 0.60% of distinct shingles in a 32-bit collision. Do the Moltbook
  copy-direction and lineage conclusions change with 64-bit hashes in the exact stage?
- Hypothesis / expected: No. Few pairs change Jaccard; cluster-level estimates move by
  well under their CI half-width.
- Go / no-go criterion (pre-registered): conclusions unchanged if every GO/NO-GO outcome
  (E32 rule for copy direction, E41-v2 rule per scope for lineage) is the same and every
  cluster-level estimate moves by less than half of its 32-bit CI half-width.
- Method: (a) recompute exact Jaccard of all E31 pairs with 64-bit blake2b shingle hashes;
  count changed pairs and pairs leaving 0.5-0.95; re-run the E32 component pipeline (as in
  E43) on the corrected pair set. (b) E41-v2 Moltbook lineage with 64-bit hashes in the
  exact verification stage; LSH candidate buckets keep the 32-bit MinHash signatures.
- Code: experiments/E47_hash64.py @ d9f175e-dirty
- Params: as E32 / E41-v2; seed 42.
- Results: (results/E47_hash64.json)
  (a) Copy direction: exact Jaccard changed for 0 of 8,361,829 E31 pairs (max change 0.0);
  0 pairs leave 0.5-0.95. Clusters 1,198; scored 547; largest cluster 50.6% of pairs;
  cluster-level length 0.4964 (identical to E32), extension 0.5081, ins/del 0.5055;
  pair-level length 0.696; GO outcome unchanged (NO-GO).
  (b) Lineage: verified edges 203,811 (all), 489 lineage components, 8,454 nodes, identical
  to E41-v2; depth / length macro tau identical in all three scopes (all 0.0332 / 0.0501).
  conclusions_unchanged = true.
- Interpretation: The 76,411 colliding shingle values found in E45 never fall in the two
  texts of the same scored pair, so no Jaccard value used by the pipelines changes. The
  limitation is reduced to the candidate (MinHash) stage, which still hashes to 32 bits.
- Decision / next step: Replace the collision limitation in the report with this result.

### E48 - Input-order invariance of the v2 lineage pipeline (Moltbook)  (2026-11-09 14:30 IST)
- Question: Does the v2 lineage result depend on the order in which rows arrive?
- Hypothesis / expected: Candidate partitions are identical across input orders; lineage
  taus vary within the E44 seed range.
- Go / no-go criterion (pre-registered): invariant if the LSH candidate partition (as sets
  of node hashes) is identical for all five shuffles; E41-v2's GO rule must fail in every
  shuffle and scope. Tau differences reported as they are.
- Method: five row-shuffle seeds 101-105; all other seeds 42. Compare candidate partitions,
  lineage component membership, share of identical tree edges (by node hash pairs), macro
  tau for depth and length.
- Code: experiments/E48_order_invariance.py @ 474e715
- Params: configs/E41_lineage_v2.json; n_boot 1000.
- Results: (results/E48_order_invariance.json; order 42 reproduces E41-v2 exactly)

  | scope | lineage components | components identical to order 42 | tree edges shared with order 42 (Jaccard of edge sets) | depth tau (6 orders) | length tau (6 orders) | depth < length |
  |---|---|---|---|---|---|---|
  | all | 481-490 | 89.4% | 21.5-22.8% | 0.007-0.037 | 0.046-0.059 | 6 of 6 |
  | within group | 446-455 | 88.5% | 20.2-21.5% | -0.001-0.036 | 0.017-0.037 | 5 of 6 |
  | across groups | 74-76 | 93.4% | 47.5-54.2% | 0.008-0.031 | 0.041-0.091 | 6 of 6 |

  Candidate partitions identical for all six orders (17 of 700 candidate groups capped in
  each). E41-v2 GO rule met in 1 of 18 order x scope runs: order 104, within group, depth
  0.036 (0.008-0.067) vs length 0.031. invariant_by_rule = false.
- Interpretation: The LSH stage is invariant to input order, but the trees are not: with
  many tied similarity weights in templated clusters, the spanning tree and the subsample of
  capped groups depend on node order, and only about a fifth of tree edges survive a change
  of input order. Under one of 18 orders, one scope passes the pre-registered rule, a rate
  close to what chance would give; the other 17 do not. A single lineage run is therefore
  not a stable result, and the NO-GO conclusion holds across orders rather than within any
  one of them. Breaking ties by a stable content hash would make trees order-invariant;
  this was not applied to the frozen pipeline.
- Decision / next step: Report the order dependence of tree structure, the 1-of-18 pass
  and the fix as a recommendation; do not claim invariance.

### E49 - LSH retrieval recall on a Moltbook subsample  (2026-11-09 14:30 IST)
- Question: What share of truly eligible near-duplicate pairs does the banded LSH stage find?
- Hypothesis / expected: High recall above J 0.7, lower in 0.5-0.6 (S-curve of 25x5 bands).
- Go / no-go criterion (pre-registered): descriptive; recall reported per Jaccard bin.
  Flagged as a limitation if overall recall in 0.5-0.95 is below 0.8.
- Method: seeded sample of 20,000 posts; exact all-pairs Jaccard by sparse matrix product
  over 64-bit shingle ids; truth = different-author, non-identical pairs with J in
  [0.5, 0.95]; candidates = pairs sharing a band bucket (128 perms, 25x5, seed 42).
- Code: experiments/E49_lsh_recall.py @ d9f175e
- Params: sample 20,000, seed 42.
- Results: (results/E49_lsh_recall.json) 24,933,525 pairs share a shingle; 1,329,876
  eligible pairs (among 4,405 posts); 886,906 LSH candidate pairs. Recall 0.511 overall;
  by Jaccard bin: 0.5-0.6 0.486 (1,255,860 pairs), 0.6-0.7 0.907 (48,299), 0.7-0.8 0.995
  (16,707), 0.8-0.9 1.000 (8,496), 0.9-0.95 1.000 (514). Different-author candidates in
  the eligible window: 0.769. Criterion (>= 0.8): not met.
- Interpretation: LSH at threshold 0.5 misses about half of the pairs just above 0.5,
  which are 94% of eligible pairs in this sample; above 0.6 it finds 91-100%. Pair-level
  totals are therefore underestimates. The copy-direction conclusions do not rest on the
  0.5-0.6 band: E43 found the same results with lower bounds 0.6-0.8, where recall is
  0.91 or more.
- Decision / next step: State the recall in the report's limitations and robustness text.

### E50 - Revision-parent recovery under other input orders (collusion.wiki)  (2026-11-09 14:47 IST)
- Question: E48 showed that tree structure depends on input order. Are E46's parent-recovery
  results stable across input orders?
- Hypothesis / expected: Within-page wiki histories have fewer exact ties than Moltbook
  templates, so MST F1 varies little; length keeps orienting recovered links better.
- Go / no-go criterion (pre-registered): stable if, over row-shuffle seeds 42 and 101-105,
  the all-scope MST F1 stays within +/-0.05 of E46 and both E46 rule outcomes (structure GO,
  direction NO-GO) are the same in every order. Otherwise report the range.
- Method: E46 code (imported) with the row-shuffle seed varied; everything else as E46.
  Executed by the author on the held-out wiki (same deviation as E46).
- Code: experiments/E50_parent_recovery_orders.py @ 5ed65e5
- Params: seeds 42, 101-105; n_boot 1000.
- Results: (results/E50_parent_recovery_orders.json; order 42 reproduces E46 exactly)
  All scope over six orders: tree F1 0.691-0.702; random tree 0.305-0.323; length parent
  0.690-0.701; tree orientation 0.911-0.920; length orientation on the same links
  0.954-0.960. Structure GO and direction NO-GO in every order. stable = true.
- Interpretation: Unlike Moltbook (E48), parent recovery on wiki page histories is stable
  under input order; the tree still adds nothing over "most similar shorter text".
- Decision / next step: State the range in Section 4.5.

### Report revision after third external review  (2026-11-09 IST)
- New analyses E46-E50 (registered above before running) folded into the report:
  Section 4.5 and Table 3 (revision-parent recovery, E46/E50); Section 4.4 adds hash width
  (E47), input order (E48) and LSH recall (E49); the ledger (Table 4) and robustness table
  (Table 5) include all five. The metadata monitor moved to Appendix C with Figure 4.
- Wording: abstract states Moltbook length as "no stable advantage (0.495-0.565 over five
  pair samples)" and that tree structure depends on input order; plain-language edits
  requested by the reviewer; estimands stated in the evaluation paragraph.
- Repository: CHECKLIST.md, DATA.md, tests/ (unit tests), pinned requirements.txt and
  tools/reproduce.py (checks headline numbers against results and runs the tests).
- E46 and E50 were run by the author on the held-out collusion.wiki data; stated in the
  report's protocol paragraph.

### E51 - AI Village feasibility: how much agent-to-agent copying is there?  (2026-11-11 IST)
- Question: Does the AI Village chat contain enough agent-to-agent reuse to build a copy
  benchmark (the funding proposal's weeks 1-3 go/no-go), and is it concentrated like Moltbook?
- Hypothesis / expected: Some edited reuse exists (agents see recent group chat), probably
  concentrated in a few templates; unclear whether it clears the bar.
- Go / no-go criterion (pre-registered, same as the funding proposal): GO if, pooled over
  all five villages, there are at least 200 candidate copy events in at least 30 independent
  clusters. A candidate copy event is an agent message with at least one EARLIER message by a
  DIFFERENT agent with exact 5-word-shingle Jaccard in [0.5, 0.95] (edited reuse). Exact or
  near-exact reuse (Jaccard > 0.95) is counted separately and not used for the bar. Clusters
  are connected components of the reuse graph over unique normalised texts.
- Method: chat_messages for the five villages (main, open-chat, swarm, saboteur-rpg,
  game-jam); agent speakers only for both copy and source (human messages reported
  separately); messages with fewer than 5 words have no shingles and are excluded. Candidate
  pairs by MinHash/LSH (128 permutations, threshold 0.5, seed 42) over unique normalised
  texts, then exact Jaccard. Also reported: largest cluster's share of events, time gap from
  the most recent qualifying source (exposure through recent chat), events per village.
  Exposure checks against computer_use_turns are a later step (stage 2), not part of this.
- Data: data/raw/ai_village/ (gitignored; gated dataset, terms: no training, cite AI Digest /
  AI Village, notify of publications). Results: aggregates only, no message text.
- Code: experiments/E51_ai_village_feasibility.py @ 6d46c90 (first run crashed on an empty event list in
  swarm-village before any result was saved; guard added, no logic changed)
- Params: Jaccard window [0.5, 0.95], shingle k = 5, seed 42.
- Results: (results/E51_ai_village_feasibility.json)

  | village | agent messages | agents | edited pairs (0.5-0.95) | edited-reuse events | clusters | exact-reuse events |
  |---|---|---|---|---|---|---|
  | main | 219,454 | 58 | 4,549 | 41 | 30 | 157 |
  | open-chat | 39,721 | 23 | 337 | 13 | 10 | 21 |
  | swarm | 3,848 | 133 | 5 | 0 | 0 | 0 |
  | saboteur-rpg | 1,592 | 6 | 0 | 0 | 0 | 0 |
  | game-jam | 838 | 6 | 0 | 0 | 0 | 0 |
  | pooled | 265,453 | | | 54 | 40 | 178 |

  Median gap to the most recent qualifying source: 0.14 s (main), 0.86 s (open-chat).
  GO criterion (>= 200 events in >= 30 clusters): NOT MET (54 events).
- Exploratory diagnostic (not pre-registered, run after the result): of the 4,549 edited pairs in
  main-village, 99.2% have the same single agent on both sides (agents re-posting edited
  versions of their own messages); 38 pairs cross agents, 87% of them first posted within
  2 seconds of each other (simultaneous posts, not reading and copying) and 13% more than 60 s
  apart. Open-chat: 95.8% same-agent; 14 cross-agent pairs, 71% within 2 s.
- Interpretation: AI Village agents rarely reuse each other's wording. Near-duplicate text in
  the chat is almost entirely self-repetition, and the few cross-agent matches are mostly
  simultaneous posts. Verbatim or lightly edited agent-to-agent copying, the basis of the
  proposed benchmark, is too rare here (on the order of ten plausible events). Influence
  between agents in the Village, if present, would be paraphrase or idea-level, which 5-word
  shingles do not measure.
- Decision / next step: Do not build the copy benchmark on AI Village chat. Revise the funding
  proposal: primary ground truth from an instrumented agent simulation (parent ids logged),
  with real-world provenance from Wikipedia copy records; AI Village only for an exploratory
  idea-propagation study (semantic, not verbatim).

### E52 - AI Village feasibility, part 2: do agents restate each other's content (paraphrase)?  (2026-11-11 06:35 IST)
- Question: E51 found almost no verbatim or lightly edited copying between AI Village agents.
  Is there enough paraphrased, lagged, cross-agent restatement (agent B says something agent A
  said earlier in the same room, in different words) to support an idea-propagation study?
- Hypothesis / expected: Unclear. Agents share a group chat and goals, so semantic similarity
  will be common; the open question is whether restatements that are novel to the later agent,
  lagged by more than a minute, and about specific content (not status boilerplate) are common
  enough.
- Go / no-go criterion (pre-registered): GO only if both hold at cosine >= 0.80:
  (a) pooled over all five villages, at least 200 restatement events in at least 30 clusters
  (same bar as E51);
  (b) in a seeded random sample of 30 events (seed 42), at least 15 are "specific": the later
  message restates a concrete item from the source (a fact, number, name, URL, plan step,
  finding or claim) that is not generic boilerplate (greetings, status/progress updates,
  acknowledgements, restating the shared goal). Classified by reading the pair, before
  looking at any other statistic of the sample.
  Otherwise NO-GO: AI Village is dropped from the funded plan's ground-truth role.
- Method: agent chat messages with at least 10 words, embedded with sentence-transformers
  all-MiniLM-L6-v2 (normalised; text truncated at the model's 256-token limit). A message m by
  agent A at time t is a restatement event if some message s by a different agent B, in the
  same room, with 60 s <= t - t_s <= 24 h, has cosine(m, s) >= 0.80, and A has no message (any
  room) in [t - 24 h, t_s) with cosine >= 0.80 to m (A had not said it before B did). Each
  message counts once. Clusters: connected components of the graph of all qualifying
  (m, s) edges. Also reported: events at cosine 0.70 and 0.90 (descriptive only); share of
  events whose best source also has 5-word-shingle Jaccard >= 0.5 (lexical reuse E51 could
  see); distinct (source agent, later agent) pairs; lag quantiles; and, descriptively, the
  rate of cosine >= 0.80 among cross-agent same-room pairs by lag bin (1-10 min, 10-60 min,
  1-6 h, 6-24 h), where a falling rate is consistent with propagation but also with topic
  drift.
- Data: data/raw/ai_village/ chat_messages (gitignored, gated; terms: no training, cite AI
  Digest / AI Village, notify of publications). Embedding is inference only, not training.
  The 30-event reading sample is written to data/derived/ (gitignored); results hold
  aggregates only, no message text.
- Code: experiments/E52_ai_village_semantic.py @ (filled after commit)
- Params: cosine 0.80 (0.70, 0.90 descriptive), min 10 words, lag [60 s, 24 h], seed 42.

### E53 - Wikipedia {{Copied}} records: are they usable ground truth for cross-page copying?  (2026-11-12 IST)
- Question: Wikipedia's attribution policy asks editors who copy text between articles to tag
  both talk pages with {{Copied}}, naming source page, destination page and, optionally, the
  source revision (from_oldid) and the destination edit (to_diff). 22,147 pages transclude
  the template (API count, 2026-11-11). How many records resolve to exact revisions, and does
  the destination edit really contain text from the source revision?
- Hypothesis / expected: A majority of records carry revision ids; most resolvable edits
  contain substantial source text, with some failures (rewritten text, split/merge
  boilerplate, wrong ids).
- Go / no-go criterion (pre-registered): GO as a ground-truth source for the funded plan if
  (a) in a seeded random sample of 400 transcluding pages, at least 50% of template records
  give both from_oldid and to_diff (or to_oldid), and the implied total over all 22,147
  pages is at least 5,000 resolvable records; and (b) in a seeded random sample of 60
  resolvable records, at least 70% of destination edits have 5-word-shingle containment
  >= 0.5 of the added text in the source revision text.
- Method: list all transcluding pages via the MediaWiki API (list=embeddedin); sample 400
  (seed 42); fetch current wikitext; parse every {{Copied}} template (aliases included,
  numbered parameter sets counted as separate records). For (b): fetch the to_diff edit's
  added text (action=compare against its parent) and the source revision text, strip markup
  crudely (templates, refs, links to their labels), compute containment of the added text's
  5-word shingles in the source. Records with added text under 50 words are counted
  separately and excluded from (b).
- Data: Wikipedia API, CC BY-SA text kept under data/raw/wiki_copied/ (gitignored); results
  hold counts and page/revision ids only.
- Code: experiments/E53_wiki_copied_feasibility.py @ 5e19fb6
- Params: sample 400 pages, 60 records, containment threshold 0.5, min 50 added words, seed 42.
- Results: (results/E53_wiki_copied_feasibility.json)

  | quantity | value |
  |---|---|
  | pages transcluding {{Copied}} (incl. 3 redirects) | 22,148 |
  | sampled pages / parsed records | 400 / 463 |
  | records with from_oldid / with destination revision | 304 / 339 |
  | resolvable records (both) | 268 (57.9%) |
  | implied resolvable total (0.67 per page x 22,148) | about 14,800 |
  | (a) GO | MET |
  | checked records: ok / added text < 50 words / missing revision | 46 / 13 / 1 |
  | ok records with containment >= 0.5 | 29 of 46 (63.0%) |
  | containment p25 / median / p75 | 0.31 / 0.75 / 0.97 |
  | (b) GO (>= 70%) | NOT MET |

  Overall GO: NOT MET.
- Interpretation: The records exist at scale and most give exact revisions, but taken at face
  value they are not clean ground truth: in about a third of checked records the destination
  edit's added text has little 5-word overlap with the named source revision. Causes are not
  separated here (rewritten text, wrong or approximate revision ids, or the crude line-level
  diff and markup stripping). The median record is a near-verbatim copy.
- Decision / next step: Do not use {{Copied}} records as labels without verification. If used,
  only as a filtered subset whose destination edit is verified to contain source text, with the
  filter's own error rate measured by hand on a sample; the filter must not use the cues being
  evaluated (length, containment direction), or the benchmark becomes circular.

#### Correction (2026-11-12): timestamp unit bug in E51 and E52
pandas 3 parses these timestamps as datetime64[us], so `.astype("int64")` gave microseconds,
while E51 and E52 treat the integers as nanoseconds. Found while profiling E52's slow run (no
E52 result had been written; that run was stopped). Effects:
- E51 event counts, clusters, exact-reuse counts and the NO-GO are unaffected (they depend only
  on time order).
- E51 time gaps were 1000x too small: the logged medians "0.14 s (main), 0.86 s (open-chat)"
  are really about 140 s and 860 s. The exploratory diagnostic's "within 2 s" and "more than
  60 s" cut-offs were really 2,000 s and 60,000 s, so the statement that cross-agent pairs are
  mostly simultaneous posts is withdrawn.
- E52 as first run used windows of about 1,000 days instead of 24 h and 16.7 h instead of 60 s.
Fix: `.dt.as_unit("ns")` before the integer cast in both scripts. E51 is re-run with the fix and
with the diagnostic written into the script (descriptive outputs only, fields `diag_*`); E52 is
re-run unchanged otherwise. Corrected numbers are added below each entry; the original rows
stay for the record.

#### E51 corrected re-run (2026-11-12, after the unit fix; results/E51_ai_village_feasibility.json)
All counts are identical to the first run (events 54, clusters 40, exact-reuse 178, GO NOT MET).
Corrected time gaps from each event to its most recent qualifying source: median 138 s
(p25 33 s, p75 708 s) in main-village; 861 s (199 s, 1,565 s) in open-chat.
Diagnostic, now computed in the script (`diag_*`): same single agent on both sides of an edited
pair 99.2% (main), 95.8% (open-chat), unchanged. Pairs whose texts were first posted by different
agents: 38 (main) and 14 (open-chat). Their first-post gap: median 123 s and 939 s; within 2 s:
2.6% and 0%; within 60 s: 37% and 14%; over 1 h: 13% and 29%.
Corrected interpretation: the few cross-agent near-copies are mostly genuine lagged reuse
(minutes apart), not simultaneous posts. The conclusion is unchanged: verbatim or lightly edited
copying between agents is real but rare (about 50 cases in 265k agent messages), far too few
for a copy benchmark.
