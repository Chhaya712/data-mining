# SetuBid — near-duplicate tender deduplication

Question 2, "twelve thousand tenders, wearing disguise."

Twelve thousand procurement notices scraped from 260 portals contain roughly 5,776 real
opportunities. Each opportunity appears up to nine times, every copy with a different
reference number, a different date and different wording, and no shared identifier anywhere.
This repository collapses them to one card per opportunity, inside a 20-minute nightly
window on one machine, with card ids that survive re-runs.

**The full answer is in [`REPORT.md`](REPORT.md).** This file is how to run it.

---

## Headline results

| | |
|---|---|
| Full-corpus runtime | **41.1 s** of a 1,200 s window (single core) |
| Representation | word 5-grams of boilerplate-stripped, volatility-masked text; Jaccard |
| Separation on 900 adjudicated pairs | **AUC 1.000** (worst `same` 0.511, worst `different` 0.405) |
| Reduced form | MinHash, **K = 1422** derived from a stated accuracy requirement |
| Retrieval | LSH, **237 bands × 6 rows**, candidate recall **1.000** on labelled `same` |
| Merge threshold | **0.735**, derived from the 200:1 cost ratio at the corpus base rate |
| False merges on labelled `different` | **0** |
| Clusters found | 6,050 vs 5,776 true opportunities (4.7% over-segmentation) |
| Skew mitigation | candidate pairs −60.2%, measured quality cost **zero merges lost** |
| Bookmark stability | **0.039%** broken on the final replayed night; content-hash ids would break ~100% |

---

## Layout

```
REPORT.md                 the answer: A(a)–A(c), B(d)–B(e), and the identity constraint
src/
  config.py               every tuned constant, each naming the experiment that derived it
  textnorm.py             A(a)  learned boilerplate, volatility masking, shingling, Jaccard
  minhash.py              A(b)  multiply-shift MinHash signatures
  lsh.py                  A(c)  banding, the S-curve, the knee
  db.py                   B(d)  SQLite schema and the access-path reasoning
  cluster.py              union-find + bookmark-stable opportunity ids
  pipeline.py             the nightly job, stage-by-stage timed
experiments/
  loader.py                     corpus/label loading (Parquet or CSV)
  exp_a_representation.py  A(a)  four representations vs the labels
  exp_b_signature_size.py  A(b)  derive K, then measure whether the argument held
  exp_c_scurve.py          A(c)  S-curve, operating points, cost-asymmetry threshold
  exp_d_access_path.py     B(d)  query plans, rows examined, wall clock, forced alternatives
  exp_e_skew.py            B(e)  distribution, mechanism, growth projection, mitigation + price
  exp_f_identity_stability.py    twelve replayed nights, bookmark survival
results/                  JSON output of every experiment (committed — these are the evidence)
figures/                  the plots REPORT.md refers to
data/                     put the faculty folder here (not committed)
```

## Data

Not committed. Drop the faculty folder in as:

```
data/
  notices/            part-*.parquet  or  part-*.csv
  labelled_pairs.csv
  portal_profiles.md
  _truth/             optional; used for diagnostics only, never to fit a parameter
```

`experiments/loader.py` accepts Parquet or CSV and either folder layout. Override the
location with `SETUBID_DATA=/exam/data`.

## Running

```bash
pip install -r requirements.txt

# the nightly job
python3 -m src.pipeline --fresh --note "nightly"

# the evidence, in the order REPORT.md presents it
python3 experiments/exp_a_representation.py
python3 experiments/exp_b_signature_size.py
python3 experiments/exp_c_scurve.py
python3 experiments/exp_d_access_path.py      # needs setubid.db from the pipeline run
python3 experiments/exp_e_skew.py
python3 experiments/exp_f_identity_stability.py
```

`exp_e` and `exp_f` each rebuild the pipeline several times and take a few minutes; the rest
are under a minute. Everything runs on one core in under 4 GB.

## Design in one paragraph

Pairwise comparison of 12,000 notices is 72 million comparisons, which is the 31-hour job
that got killed. The chain that replaces it: make notices *comparable* by deleting what
re-publication rewrites (boilerplate, money, dates, reference numbers) and keeping word
5-grams — this alone separates the label set perfectly, where raw text does not. Replace each
shingle set with a fixed-width MinHash signature sized from a stated error requirement.
Band the signature so that similar notices collide in a SQLite B-tree and dissimilar ones
usually do not, turning retrieval from 72 million comparisons into 1.2 million. Score those
with vectorised integer comparison, threshold at a point derived from the head of product's
200:1 ratio corrected for the corpus base rate, and close the clusters transitively. Carry
opportunity ids forward by member overlap with an alias table, so bookmarks survive.

## What this submission does not claim

- The reduced form is **larger** than the exact form on this corpus (5.7 KB vs 1.2 KB). It
  earns its place through fixed-width comparison and bandability, not bytes. REPORT.md A(b).
- K = 1422 changes **no decision** on the 900 labels versus K = 64. The argument that
  survives is about tails, not RMSE.
- The WITHOUT ROWID layout beats the rejected alternative by **1.14×**, not 10×. The
  database fits in page cache. REPORT.md B(d).
- The negative tail above 0.43 is **modelled, not measured** — 621 negatives cannot measure
  a 1e-6 rate. The model is stated and is the weakest load-bearing assumption here.
- Bookmark stability is **0.039% broken on the final night, not 0%**. The breakages are cluster splits, and the
  run table records which run caused them.
