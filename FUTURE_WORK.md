# Future work: from sprint report to conference paper

This note records what the sprint report does not yet cover, what a conference-level version would need,
and the prior work it would have to be positioned against. It was written after the sprint submission
(9 November 2026); nothing here has been run yet.

## 1. Where the work stands

The sprint report is a pre-registered empirical study with three findings: the content cues we tested
reduce to text length; pair-level evaluation of near-duplicate text is badly inflated (two clusters hold
98% of 8.4M Moltbook pairs; 86% vs 5% false alarms under a cluster-preserving null); and a positive
lineage result came from a row-order leak. Against recorded wiki revision parents, trees recover 76% of
links but add nothing over "most similar shorter text".

Realistic reading: a strong workshop paper now; a main-track paper (ACL / EMNLP / ICWSM / NeurIPS
Datasets and Benchmarks) only with the additions below.

## 2. What a main-track version needs, in priority order

1. **A stronger method family.** Reviewers will ask about language-model and embedding judges. Plug them
   into the frozen harness (it takes any predictor of "which text came first") and test whether they
   also reduce to length, and whether pair-level scoring inflates them too.
2. **Evidence that pair-level evaluation is common practice** (Section 4). A literature audit answers the
   objection that nobody evaluates this way.
3. **Ground truth for copying between agents** (Section 3). The wiki gives recorded parents only within a
   page; the central claim needs recorded copy links across authors.
4. **A general statistical result.** Simulations (and, if possible, a simple analytic bound) of how
   pair-level type-I error grows with the skew of cluster sizes, given that a family of n near-duplicates
   yields about n^2/2 pairs; plus a recommended procedure with demonstrated calibration.
5. **Fix the known weaknesses of the sprint version:**
   - break all ties by a stable content hash, so trees do not depend on input order (E48);
   - raise candidate recall near Jaccard 0.5-0.6 (E49: 0.49);
   - try a second cluster definition (complete or average linkage on a subsample);
   - use a held-out corpus that was never profiled.
6. **An experienced collaborator** who has published at the target venue (for example through an Apart
   Research fellowship), and a clean 8-9 page write-up in the venue format.

## 3. Datasets with recorded copying (ground truth beyond time order)

"Recorded copying" means a record of which text was derived from which, not an inference from
timestamps. Candidates found so far:

| Source | What is recorded | Agents? | Fit | Notes |
|---|---|---|---|---|
| AI Village dataset (Hugging Face `aidigestorg/ai-village`, gated) | Full event timeline, chat (~123k messages), memories, ~37k computer-use sessions | Yes, LLM agents | **Best agent-native option.** Timestamped shared chat gives who saw which message before writing; verbatim or near-verbatim reuse after exposure is a strong copy signal | Access by request (author now has access). Raw LLM-call logs excluded |
| Wikipedia "copying within Wikipedia" records | Edit summaries such as "content copied from [[X]]" and `{{copied}}` talk-page templates naming source and destination | No (human editors) | **Best real cross-page ground truth at scale** | No published corpus found; must be built from dumps |
| SOTorrent (Baltes et al., MSR 2019) | Stack Overflow code snippets and their versions, plus links from GitHub files back to Stack Overflow posts | No | Explicit source links for copied code | Open on Zenodo |
| Webis-TRC-12 (Potthast et al., ACL 2013) | 297 crowdsourced essays with logs of which web sources the writers searched and reused | No | Recorded reuse, small | Open on Zenodo |
| METER corpus (Gaizauskas, Clough, Piao et al., LREC 2002) | Press Association wire stories and British newspaper stories, with derivation annotated | No | Classic text-reuse ground truth | About 1,700 documents; availability to be checked |
| Instrumented agent-swarm simulation | Every forwarded message carries its parent id | Yes | Ground truth by construction | Synthetic; must be validated against AI Village or Moltbook statistics |

Proposed combination for a safety venue: AI Village (agent-native, real) plus an instrumented simulation
(full ground truth), with Wikipedia copy records as a large human-written control.

## 4. Literature audit: is it a paper on its own?

**Idea.** Audit how published work evaluates copy direction, text reuse, near-duplicate provenance and
coordination detection. Do papers report clusters, cluster their uncertainty, or control for duplicated
evidence? Then re-analyse the public datasets of audited papers to show the size of the effect.

**Precedents (meta-evaluation published at strong venues):**
- Marie, Fujita & Rubino (ACL 2021): meta-evaluation of 769 machine-translation papers; Outstanding Paper.
- Dror, Baumer, Shlomov & Reichart (ACL 2018): survey of significance testing in ACL/TACL 2017 papers;
  found tests often neglected or misapplied.
- Gorman & Bedrick (ACL 2019, Outstanding Paper) and Søgaard, Ebert, Bastings & Filippova (EACL 2021):
  standard and random splits give over-optimistic estimates.
- Kapoor & Narayanan (Patterns 2023): leakage in 294 papers across 17 fields.
- Krinke & Ragkhitwetsagul (IWSC 2022; arXiv 2505.04311, 2025): BigCloneBench labels unreliable;
  139 of 179 surveyed papers used it for semantic clone detection.
- Mannocci, Mazza, Monreale, Tesconi & Cresci (arXiv 2408.01257, 2024): survey of 84 papers on
  coordinated online behaviour; diverse methods and ground-truth practices limit comparison.

**Closest methodological prior work (must be cited and distinguished):**
- Miller (arXiv 2411.00640, 2024), "Adding Error Bars to Evals": recommends clustered standard errors for
  LLM evaluations; reports clustered errors more than 3x the naive ones.
- Allamanis (Onward! 2019) and Lee et al. (ACL 2022): duplicated data inflates code and language-model
  results.

**Gap.** No audit found of near-duplicate, copy-direction or provenance evaluation that asks whether the
evidence is clustered. The distinctive points here are: pairs grow quadratically within a family, so a few
template families can supply almost all pairs; the effect is extreme for agent swarms (template
broadcasting); and the forensic question (who copied whom) has direct oversight consequences.

**Assessment.**
- An audit of 30-50 papers on its own: workshop or Findings level.
- Audit plus re-analysis of public datasets from the audited papers (showing inflated claims), plus the
  simulation result in Section 2 item 4: plausible main-track ACL / EMNLP / ICWSM paper.
- Audit plus the agent-native benchmark (Section 3) plus LLM judges: the strongest version, suited to a
  NeurIPS Datasets and Benchmarks or a safety-focused main track.

Main risk: the general point that clustered evaluation needs clustered uncertainty is established (Miller,
2024; Hurlbert, 1984). The paper must show that it is violated in practice in this specific area, and
by how much, rather than restate it.

## 5. Suggested plan

1. Weeks 1-2: AI Village exploration (copy events after exposure in shared chat); content-hash tie-breaking.
2. Weeks 3-4: LLM and embedding judges in the frozen harness, scored per cluster and per pair.
3. Weeks 5-6: literature audit protocol (search strings, inclusion rules, coding sheet) registered in
   EXPERIMENT_LOG.md before coding papers; code 30-50 papers.
4. Weeks 7-8: simulation study of inflation versus cluster-size skew; recommended procedure.
5. Then: workshop submission; extend with Wikipedia copy records and a fresh held-out corpus for a
   main-track version.

## Sources checked for this note

- AI Village dataset: https://huggingface.co/datasets/aidigestorg/ai-village
- Wikipedia copying policy: https://en.wikipedia.org/wiki/Wikipedia:Copying_within_Wikipedia
- SOTorrent: https://arxiv.org/abs/1809.02814 ; https://zenodo.org/records/4415593
- Webis-TRC-12: https://webis.de/data/webis-trc-12
- METER corpus: https://eprints.whiterose.ac.uk/78663/
- Marie et al. 2021: https://aclanthology.org/2021.acl-long.566
- Dror et al. 2018: https://aclanthology.org/P18-1128/
- Gorman & Bedrick 2019: https://aclanthology.org/P19-1267
- Søgaard et al. 2021: https://aclanthology.org/2021.eacl-main.156
- Kapoor & Narayanan 2023: https://doi.org/10.1016/j.patter.2023.100804
- Krinke & Ragkhitwetsagul: https://doi.org/10.1109/IWSC55060.2022.00008 ; https://arxiv.org/abs/2505.04311
- Mannocci et al. 2024: https://arxiv.org/abs/2408.01257
- Miller 2024: https://arxiv.org/abs/2411.00640
- LLM diffusion simulations without per-hop provenance: https://arxiv.org/abs/2410.13909 ; https://arxiv.org/abs/2606.13140
