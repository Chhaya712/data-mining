# SetuBid deduplication — Question 2

**Corpus:** 12,000 notices, 260 portals, 8 part files.
**Labels:** `labelled_pairs.csv`, 900 adjudicated pairs — **279 `same`, 621 `different`**, i.e. 31% positive.
**Budget:** one machine, 20 minutes a night, forever.
**Measured end-to-end runtime on the full corpus: 41.1 s** (single core, SQLite on disk).

Every number below was produced by a script in `experiments/` against the data in `data/`.
Raw outputs are in `results/*.json`; figures in `figures/`. Nothing here is quoted from a
reference — where a textbook value would have been the easy answer, the corpus was measured
instead, and where the measurement disagreed with the argument that preceded it, the
disagreement is reported rather than smoothed over.

---

## 0. The label file is skewed, and the skew changes the arithmetic

The label file is 31% `same`. The corpus is not. There are 12,000 notices, so
71,994,000 possible pairs, and the pipeline finds roughly 13,000–15,000 genuine duplicate
pairs among them — a base rate of about **0.02%**. Among the pairs that actually reach the
scoring stage (candidates, not all pairs) the rate is **0.47%** (measured:
13,215 merged / 3,134,175 candidates).

This matters because a false-positive rate measured on the label file is read at 31% prior
and then applied at 0.47% prior. A threshold that looks safe on the labels — "no false
merges in 621 negatives" — is being asked to hold over three million candidate pairs a
night. The correction appears explicitly in A(c); it is the difference between a cost ratio
of 200 and an effective ratio of **42,271** once base rates are folded in.

The labels are used for exactly three things: choosing the representation (A(a)), measuring
estimator error (A(b)), and fitting the negative tail and measuring recall (A(c), B(e)).
They are never used to fit a cluster.

`data/_truth/` ships with the faculty folder. It is read in exactly one place — to describe
the anatomy of the worst bucket in B(e), where 900 pairs cannot describe a corpus-wide
phenomenon — and never to choose a parameter. `experiments/loader.py` marks it
`# Diagnostic only`.

---

# Section A

## A(a) What "similar" means, mechanically

**Representation.** A notice becomes the **set of word 5-grams** of its normalised
title-plus-body. **Score = Jaccard** of those sets, `|A∩B| / |A∪B|`.

Two decisions are embedded in that sentence.

### D1 — granularity: word 5-grams

### D2 — signal and noise: strip learned boilerplate, mask volatile literals

Money, dates, reference numbers and bare numbers are replaced by the sentinels
`<money> <date> <ref> <num>`. The scraping notes say the same estimated cost appears as
`Rs. 4,50,00,000/-`, `Rs. 450.00 lakh`, `INR 4.500 Cr`, `45000000` and
`RUPEES 4,50,00,000 ONLY`; the same date appears in seven formats; and every portal invents
its own reference number with no cross-walk. A literal that is *rewritten by the act of
re-publication* cannot be evidence of identity — it only manufactures disagreement between
two copies of one tender. So the sentence shape survives and the volatile filling does not.

Boilerplate is **learned, not hard-coded**. `portal_profiles.md` names two ~1,400-character
preamble blocks, but hard-coding them breaks the first time a seventh aggregator appears.
Instead boilerplate is defined operationally: *a line occurring in at least 2% of all
notices carries no evidence about which opportunity a notice describes.* On this corpus that
rule finds **318 lines** — the two preambles, the disclaimer footers, and the generic clause
bank (`conditional bids shall be summarily rejected`, appearing in 27% of notices, and so on).
The rule is portal-agnostic and self-maintaining.

### The evidence

All 900 adjudicated pairs, exact Jaccard, four representations
(`results/exp_a_representation.json`, `figures/fig_a_separation.png`):

| representation | AUC | mean `same` | mean `different` | worst `same` | worst `different` | margin |
|---|---|---|---|---|---|---|
| RAW, word 3-gram | 0.9207 | 0.645 | 0.254 | 0.196 | 0.531 | **−0.335** (overlap) |
| RAW, word 5-gram | 0.9575 | 0.622 | 0.177 | 0.179 | 0.445 | **−0.266** (overlap) |
| CLEAN, word 3-gram | **1.0000** | 0.880 | 0.295 | 0.552 | 0.458 | +0.094 |
| **CLEAN, word 5-gram (adopted)** | **1.0000** | 0.867 | 0.227 | **0.511** | **0.405** | **+0.106** |

A labelled `same` pair and a labelled `different` pair, scored under all four
(the two hardest cases in the file):

| pair | portals | RAW-w3 | RAW-w5 | CLEAN-w3 | **CLEAN-w5** |
|---|---|---|---|---|---|
| `N000576` / `N000577` — labelled **same** | P005, P046 | 0.196 | 0.179 | 0.690 | **0.654** |
| `N006774` / `N009531` — labelled **different** | P006, P004 | 0.494 | 0.389 | 0.454 | **0.405** |
| `N003845` / `N003847` — labelled **same** (typical) | P111, P002 | 0.621 | 0.605 | 0.987 | **0.988** |

Read the first two rows together. Under RAW, the hardest true duplicate scores **0.179** and
the hardest true non-duplicate scores **0.494** — *the wrong way round*. No threshold exists
that classifies both correctly; any RAW system must either merge a pair that would get us
sued or miss a pair it was built to catch. Under CLEAN-w5 they are 0.654 and 0.405, and
every threshold in (0.405, 0.511) classifies all 900 pairs correctly.

Why the reversal: `N000576` is a P005 notice, so about 1,400 characters of its body are the
aggregator preamble and its reference number and money figures are P005's conventions.
`N000577` is the same tender on P046 with none of that. RAW compares one document that is
mostly legal furniture against one that is not. CLEAN deletes the furniture from both and
compares the tender.

**D1, defended.** w3 and w5 both achieve AUC 1.0, so granularity is decided on which side of
the margin it widens. w5 pushes the worst `different` pair down from 0.458 to **0.405**; w3
pushes the worst `same` pair up from 0.511 to 0.552. Those are not equivalent gains. The
head of product priced a false merge at 200 missed merges, so headroom on the *negative*
side is worth 200× headroom on the positive side. w5 buys 0.053 of negative headroom; w3
buys 0.041 of positive headroom. **w5 adopted.**

**What D1 cost:** the worst true duplicate sits 0.041 closer to the boundary than it would
under w3, and 5-grams are a larger vocabulary (156 vs 143 shingles per notice after
cleaning), so the estimator in A(b) has slightly fewer distinct items to draw minima from.

**What D2 cost — measured, not asserted.** Masking helps both populations, and it helps the
negatives too, which is the cost:

- `different` pairs rise by **+0.050** on average when masking is turned on. Masking deletes
  the one piece of evidence that most cheaply distinguishes two similar-looking road
  contracts: their money figures and their closing dates. Every `different` pair gets 0.050
  closer to being merged, and 0.050 is half our entire safety margin.
- `same` pairs rise by **+0.245**, and the number of true duplicates scoring below 0.5 falls
  from **89 to 0**.

So the trade is: give up 0.050 of margin on the expensive side to recover 89 of 279 true
duplicates. We took it, and A(c) then spends the remaining margin deliberately rather than
accidentally.

One specific risk was checked rather than assumed. **Corrigenda are published as new
notices** with a new closing date, and 2,548 of the 12,000 notices are corrigenda; 144 of
the 279 labelled `same` pairs involve one. Masking dates is what lets those pairs cross the
threshold — under RAW they are penalised for the one field that is *supposed* to differ.
Conversely, masking money means two genuinely different lots of the same framework contract
are harder to tell apart. That is the residual risk in D2, and it is why the worst
`different` pair sits at 0.405 rather than lower.

---

## A(b) The reduced form, and its size

Per notice we keep a **K-coordinate MinHash signature** instead of its shingle set. For a
random permutation, `Pr[min h(A) = min h(B)] = J(A,B)`, so the fraction of agreeing
coordinates is unbiased for Jaccard with variance `J(1−J)/K`.

### The size was fixed before implementation, from a requirement

1. A(a) measured the margin between the two adjudicated populations:
   worst `different` = 0.4052, worst `same` = 0.5111. **Half-margin = 0.0530.**
2. **Requirement:** the estimator must not, by itself, carry a pair across that margin. A
   4σ excursion must still fit inside the half-margin:
   `4·√(J(1−J)/K) ≤ 0.0530` at the worst case `J = 0.5` ⟹ `σ ≤ 0.01325` ⟹ **K ≥ 1424**.
3. **Constraint from A(c):** K must factor as `bands × rows`, and rows = 6 there. The
   smallest admissible K is **237 × 6 = 1422**, giving 4σ = 0.0530 — exactly at the bound.

4σ rather than 2σ because the tail, not the typical case, is what costs money: at 0.47%
positives among three million candidate pairs a night, a once-in-twenty-pairs excursion is
not a rare event, it is a nightly occurrence.

Hash family: multiply-shift, `h(x) = ((a·x + b) mod 2^64) >> 32`, with shingles hashed by
blake2b rather than Python's randomised `hash()` — a signature computed tonight must be
bit-identical to one computed next month, and the bookmark requirement starts there.

### Closing the loop (`results/exp_b_signature_size.json`, `figures/fig_b_error.png`)

Exact Jaccard was computed for all 900 labelled pairs and 5,000 random corpus pairs and
compared against the estimate:

| K | realised RMSE | predicted σ | realised/predicted | max abs error | false merges | false splits | MB @ 12k |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 64 | 0.0376 | 0.0475 | 0.79 | **0.1134** | 0 | 6 | 3.1 |
| 256 | 0.0192 | 0.0238 | 0.81 | 0.0743 | 0 | 5 | 12.3 |
| 1024 | 0.0105 | 0.0119 | 0.88 | 0.0342 | 0 | 5 | 49.2 |
| **1422 (adopted)** | **0.0094** | **0.0101** | **0.93** | **0.0378** | **0** | **5** | **68.3** |
| 4096 | 0.0051 | 0.0059 | 0.87 | 0.0170 | 0 | 6 | 196.6 |

**Where it behaved as predicted.** RMSE falls as `K^(−1/2)` across six doublings, and at the
adopted K the realised RMSE (0.0094) is within 7% of the predicted σ (0.0101). Stratified by
true similarity, the realised sd tracks `√(J(1−J)/K)`: largest in the 0.35–0.7 band
(0.0106–0.0109) and collapsing to 0.0057 above J = 0.9, which is the shape the variance
formula demands.

**Where it did not — three honest failures.**

1. **A small positive bias at low similarity.** In the J < 0.35 strata the mean signed error
   is **+0.0053**, not zero, and it vanishes above J = 0.7 (+0.0007). The estimator is
   unbiased in theory. The cause is that we keep 32-bit minima: with ~2.8 million distinct
   shingles in play, distinct shingles occasionally hash to the same 32-bit minimum, which
   can only ever *inflate* apparent agreement, and inflation is proportionally largest where
   true agreement is smallest. It biases toward merging, which is the expensive direction.
   It is 0.005 against a margin of 0.106, so it is absorbed; a 64-bit signature would remove
   it at double the storage.
2. **Realised sd is consistently *below* predicted** (ratio 0.79–0.93 at every K). The
   variance formula assumes K independent permutations over an unbounded universe; our
   notices have only ~156 shingles each, so distinct coordinates frequently select the same
   shingle and the K draws are not independent. The estimator is better than the formula
   promised — but the promise was the basis of the sizing argument, so the argument was
   conservative, not correct.
3. **The sizing argument did not change any decision on this label set.** At K = 64 the
   outcome is identical: 0 false merges, 6 false splits. A submission that stopped at "it
   works" could have shipped K = 64 and saved 65 MB. What survives scrutiny is the tail
   argument, not the RMSE argument: at K = 64 the **largest single observed error is 0.113**,
   more than twice the half-margin — one pair *did* move far enough to flip, and it happened
   in 900 samples. At K = 1422 the largest observed error is 0.038, inside the 0.053 budget.
   Over 3 million candidate pairs a night, "the worst of 900" is the statistic that matters.

**An honesty note on the premise.** The question frames the reduced form as a space saving.
On this corpus it is not one. After boilerplate stripping, a notice has ~156 shingles, about
1.2 KB as 64-bit hashes; the signature is 1,422 × 4 bytes = **5.7 KB**. The reduced form is
*4.7× larger than the exact form it replaces.* It earns its place for two other reasons: it
is fixed-width, so a candidate list of three million pairs is scored as one vectorised
integer comparison in 4.5 s rather than three million set intersections; and it is bandable,
which is the whole of A(c). Exact Jaccard has no S-curve. We report this because our own
sizing argument was framed in bytes and the bytes went the wrong way.

---

## A(c) Sublinear retrieval, and the price of the risk

### The structure

The 1,422 coordinates are cut into **237 bands of 6 rows**. Two notices are candidates if
any one band matches exactly. Since each coordinate agrees with probability `s`,

    P(candidate | s) = 1 − (1 − s^6)^237

Nothing else in the retrieval path reads text, so **this function is the recall ceiling of
the entire system**: a pair that never becomes a candidate can never be merged, at any
threshold.

### The curve, measured as well as derived

`figures/fig_c_scurve.png` plots the closed form with the **measured** survival of the
adjudicated pairs overlaid (each point is a 0.05-wide similarity bin; point size = bin
count), the chosen operating knee marked at s = 0.402, and the two label extremes as
vertical rules.

The tension was made explicit by re-banding the *real* signatures under four layouts and
counting the candidate lists each actually produces (`results/exp_c_scurve.json`):

| layout | knee | candidate pairs | per notice | recall on labelled `same` |
|---|---:|---:|---:|---:|
| b=79, r=18 | 0.785 | 12,124 | 2.0 | **0.810** |
| b=177, r=8 | 0.524 | 272,730 | 45.5 | 0.996 |
| **b=237, r=6 (adopted)** | **0.402** | **3,134,175** | **522** | **1.000** |
| b=284, r=5 | 0.323 | 11,795,395 | 1,966 | 1.000 |

b=79/r=18 is 258× cheaper and loses **19% of all true duplicates before any threshold is
ever applied** — an unrecoverable loss, invisible to any later tuning. b=284/r=5 buys
nothing over the adopted point (recall already 1.000) for 3.8× the work. b=177/r=8 is the
genuine competitor: it costs 11× less and loses one true pair in 279. It was rejected
because that single loss is at the *ceiling*, and B(e) shows the adopted point's extra cost
can be removed by other means at zero measured quality cost — so the cheap layout would have
bought a permanent recall loss to solve a problem that had a free solution.

### Where the 200:1 enters the settings

**Step 1 — the honest admission.** At the deployed threshold the empirical false-positive
rate on the labels is 0/621. Zero out of 621 is not zero: by the rule of three the 95% upper
bound on the rate is **3/621 = 0.00483**, which over 3.13M candidate pairs permits
**15,141 false merges per night**. The label file cannot measure a rate we need to know to
1e-8. The tail must therefore be *modelled*, and the model is stated rather than hidden:
exceedances of the `different` population over u = 0.25 (213 of them) are fitted with an
exponential tail, `P(X>t) = 0.343 · exp(−(t−0.25)/0.0384)`.

**Step 2 — the rule.** Her ratio says one false merge costs 200 missed merges. That is a
*marginal exchange rate*, so it is applied marginally: **lower the threshold only while one
more expected false merge buys at least 200 more recovered duplicate pairs.** The positive
density is a Gaussian kernel estimate (h = 0.02) over the 279 positives scaled to the
estimated 15,083 true duplicate pairs in the corpus; the negative density comes from the
fitted tail, for which `dFPR/dt = −FPR/β`.

**Result: t\* = 0.735.** At that point the marginal exchange rate is **245 recovered pairs
per additional false merge** — just above her 200. One step lower and it falls below, so
0.735 is where her number stops paying.

| quantity at t = 0.735 | value |
|---|---|
| recall on labelled `same` (pair level) | 0.896 |
| false merges on labelled `different` | 0 |
| modelled FPR | 1.1e-6 |
| modelled expected false merges per night | 3.4 |
| marginal exchange rate | 245 : 1 (required 200 : 1) |

**The cross-check that disagrees, reported.** A second rule — "hold expected false merges
under one per thirty runs" — gives t = 0.915 and costs 59% of pair-level recall. The two
rules disagree because the first prices errors against each other and the second prices them
against an absolute budget she never specified. We adopted the marginal rule because it is
the one derived from the number she actually gave. If she would rather state an absolute
budget, `FALSE_MERGE_COST` in `src/config.py` is the single line to change, and
`exp_c_scurve.py` re-derives the threshold from it.

**Where the base rate entered.** Expected cost per candidate pair is
`200 · P(different) · FPR + 1 · P(same) · FNR`. With `P(same) = 0.0047` among candidates
rather than the 0.31 of the label file, the false-merge term is weighted **42,271×** the
false-split term, not 200×. Had we read the rates straight off the label file we would have
set the threshold about 0.1 too low.

**What the 0.896 pair-level recall actually costs the product.** Less than it looks:
clustering is transitive, so a pair A–C that scores 0.71 is still merged if A–B and B–C both
clear. The corpus-level outcome at t = 0.735 is **6,050 clusters against 5,776 true
opportunities** — a 4.7% over-segmentation, which is the "bidder grumbles" failure, and
**zero** of the expensive failure on the label set.

Transitivity is also the back door through which the expensive error could arrive: A~B and
B~C forces A~C. It is measured, not assumed — 6,050 clusters versus 5,776 true opportunities
means the chain is running *short*, not long, so no runaway merging is occurring at this
threshold.

---

# Section B

## B(d) A home and an access path

### Schema (`src/db.py`, full DDL)

```
notice(notice_id PK, portal_id, published_at, title, estimated_value,
       closing_date, shingle_count, content_key)
signature(notice_id PK → notice, k, sig BLOB)                       WITHOUT ROWID
band_bucket(band_no, band_hash, notice_id, PK(band_no,band_hash,notice_id))
                                                                     WITHOUT ROWID
bucket_stat(band_no, band_hash, members, suppressed, PK(band_no,band_hash))
pair_score(a, b, est, PK(a,b))                                       WITHOUT ROWID
opportunity(opportunity_id PK, seq, anchor_notice, created_run, retired_run)
notice_opportunity(notice_id PK, opportunity_id → opportunity, assigned_run)
opportunity_alias(old_id PK, new_id, merged_run)                     WITHOUT ROWID
run(run_id PK, started_at, finished_at, notices, candidates, merges, seconds, note)
meta(key PK, value)
```

`band_bucket` is the structure A(c) consults: 237 × 12,000 = **2,844,000 rows**. Signatures
are BLOBs in `signature`, so a run that dies at minute 12 restarts from the database rather
than from the part files, and the application can query a bidder's card without the nightly
job being alive. No part of the lookup path lives in a Python dict.

### The access method, and why

`band_bucket` is declared **WITHOUT ROWID with primary key (band_no, band_hash, notice_id)**.
The reasoning is about how rows are physically located:

- In SQLite a WITHOUT ROWID table **is** a B-tree keyed on the primary key — the row lives
  in the index leaf. A bucket probe is one descent to the leftmost matching leaf followed by
  a sequential read of **physically adjacent** entries: one bucket occupies contiguous bytes
  on the same page or two. The payload we want (`notice_id`) is part of the key, so the
  index is **covering** and no second structure is ever touched.
- **Rejected: an ordinary rowid table with a secondary index on (band_no, band_hash).**
  This descends the index B-tree to find rowids, then performs **one further descent of the
  table B-tree per matching row** to fetch `notice_id`. That second descent is paid once per
  *returned* row — and a bucket probe is precisely the query shape that returns many rows,
  so the penalty scales with exactly the thing B(e) shows is already skewed.
- **Rejected: no index (full scan).** Included as a floor.
- **Rejected: a hash index.** SQLite offers none, which alone settles it here, but it is
  worth naming why it would lose even where available: it locates a single key in O(1) and
  cannot do anything else. Our bucket keys are 63-bit blake2b digests with no locality, but
  the *maintenance* path does range work — `GROUP BY band_no, band_hash` to build
  `bucket_stat`, and the ordered sweep the pipeline uses instead of 2.8M point probes. On a
  B-tree that sweep is one in-order traversal; on a hash index it is a full rehash-and-sort.

### The measurements (`results/exp_d_access_path.json`)

Identical rows, identical 12,000-probe workload. Rows examined are **counted, not inferred**:
a user-defined SQL function `probe()` is registered and placed in the WHERE clause, so SQLite
calls it once per row reaching that term.

| layout | planner's path | probes | rows examined / probe | rows returned | wall clock | µs/probe |
|---|---|---:|---:|---:|---:|---:|
| **A — WITHOUT ROWID PK (adopted)** | `SEARCH band_bucket USING PRIMARY KEY (band_no=? AND band_hash=?)` | 12,000 | **4.2** | 50,250 | **0.076 s** | **6.3** |
| B — rowid + secondary index | `SEARCH band_bucket_rowid USING INDEX ix_bbr (band_no=? AND band_hash=?)` | 12,000 | 4.2 | 50,250 | 0.087 s | 7.2 |
| C — index forced off (`NOT INDEXED`) | `SCAN band_bucket_rowid` | 60 | **2,844,000** | 113 | 38.7 s | 645,180 |

C extrapolates to **7,742 s for one 12,000-probe sweep — 6.5× the entire nightly window for
a single pass**, against 0.076 s for A. That is the difference between a design and the
31-hour job that was killed.

A versus B is the more interesting comparison, and the honest reading is that **A wins by
only 1.14×** here. Two reasons, both stated rather than glossed: the 350 MB database fits in
the page cache, so B's second descent is a memory hop rather than a seek; and the median
bucket holds 4.2 rows, so there is little per-row cost to multiply. Re-running both against
the **2,000 heaviest buckets** (41 rows each) moves the gap to **1.16×** — the right
direction, still small. The structural argument stands and the cache is doing the work; we
are not going to claim a 10× from a 1.14× measurement.

Storage: 2,844,000 band rows, 85,654 pages × 4,096 B = **350 MB**.

---

## B(e) Where the design betrays us

### Finding it: look at the distribution, not the total

Total candidate work is comfortable — 3.13M pairs, 51.7 s. The distribution is not
(`figures/fig_e_skew.png`, `results/exp_e_skew.json`):

| per-notice candidate work | uncapped |
|---|---:|
| median | 483 |
| p90 | 885 |
| p99 | 1,285 |
| max | **1,931** |
| share of work from heaviest 1% of notices | 2.7% |
| share from heaviest 10% | 20.4% |

**The per-notice skew is mild, and that is itself a result.** The obvious culprit —
`portal_profiles.md` warns that "everything on P001 looks like everything else on P001" —
was already neutralised by the learned-boilerplate rule in A(a). Nodal notices average 530
candidate slots against 518 for everyone else: a 2% difference where the notes predicted a
catastrophe. A(a) paid for B(e) in advance.

**The surviving skew is at bucket level, and it is severe:**

| bucket distribution | uncapped |
|---|---:|
| buckets total | 1,766,017 |
| singleton buckets | 1,282,055 |
| largest bucket | **507 members** |
| share of all emitted pairs from buckets > 60 members | **41.5%** |
| share from buckets > 200 members | 17.6% |

A few hundred buckets out of 1.77 million emit **41% of the night's work**.

### Why, mechanically

The largest bucket holds **507 notices spanning 267 distinct true opportunities** — they are
not duplicates of anything, their titles are unrelated (a fire station in Parbhani, a water
supply scheme at Cooch, a bridge at Bharuch, a bus terminal at Nalgonda). They collide
because of an interaction between the corpus and *our own A(a) decision*:

1. These notices are template-generated. After masking, sentences like
   `the contractor shall execute <num> units of ... in reach <num> between chainage
   <num>+<num> and <num>+<num> of the alignment at X` are **character-identical across
   unrelated tenders**. Measured: the six most frequent 5-grams
   (`shall execute <num> units of`, `chainage <num> <num> and <num>`, …) occur in **100% of
   the corpus**, and **74% of an average notice's shingles occur in more than 1% of the
   corpus**.
2. Boilerplate stripping shrank notices to a median of **154 shingles** (p1 = 110). MinHash
   takes a minimum over that small set. When 74% of the set is shared template text, the
   minimum for any given coordinate is *probably* drawn from the shared part.
3. A band is 6 consecutive coordinates. If all 6 minima happen to fall in the shared
   template region, the band hash is identical for every notice sharing that template —
   regardless of what the tender is actually about. With 237 bands and ~110 shingles in the
   short notices, that event stops being rare.
4. A bucket of size *m* emits *m(m−1)/2* pairs. One bucket of 507 emits **128,271** pairs.
   Bucket occupancy driven by a template grows **linearly with corpus size**, so its pair
   emission grows **quadratically** — the same quadratic the whole design exists to escape,
   reintroduced through a few hundred buckets.

So the mechanism is: A(a)'s cleaning made notices short and template-dominated, which is
exactly the condition under which A(c)'s banding degenerates. The two good decisions
interact badly, and neither is visible as a problem on its own.

### What it costs against the 20-minute budget

Today it costs 10.6 s of 1,200 — irrelevant. The board asked for 20 minutes **forever**, and
the corpus grows 4,000/week. Projecting with the tail 41.5% of pairs scaling quadratically
and the rest linearly:

| | notices | candidate pairs | projected seconds | within 20 min? |
|---|---:|---:|---:|---|
| today | 12,000 | 3.1M | 52 | yes |
| +26 weeks | 116,000 | 139M | 1,108 | barely |
| **+52 weeks** | **220,000** | **470M** | **3,281** | **no — 2.7× over** |
| +104 weeks | 428,000 | 1.7bn | 10,972 | no |
| +156 weeks | 636,000 | 3.7bn | 23,124 | no — 6.4 hours |

**The design breaches the budget in about 52 weeks**, and the breach is caused almost
entirely by a few hundred buckets. Without the tail, growth is linear and the window holds
for years.

### The mitigation, and its measured price

**Rule: a band whose bucket exceeds 60 members is not expanded into pairs** (`BUCKET_CAP`).
It is not deleted — the row stays in `band_bucket`, and `bucket_stat.suppressed` records the
decision, so the choice is auditable and reversible without a rebuild. The justification is
the Bayesian one: a band that 507 notices agree on has told us almost nothing about any
particular pair, whereas a band shared by 3 notices is strong evidence. We are discarding
the least informative evidence first. 264 of 1,766,017 buckets are suppressed.

Crucially, a true duplicate pair typically agrees on **many** bands (at s = 0.87 the expected
number of matching bands is ~103 of 237), so suppressing a handful of over-subscribed ones
rarely removes a pair's *only* route to candidacy.

| | before | after | change |
|---|---:|---:|---|
| candidate pairs | 3,134,175 | **1,247,615** | −60.2% |
| retrieve + score stages | 18.0 s | **8.1 s** | −55% |
| total runtime | 51.7 s | **41.1 s** | −20.5% |
| max per-notice work | 1,931 | **608** | −68% |
| p99 per-notice work | 1,285 | 428 | −67% |
| share of work from heaviest 1% | 2.7% | 2.2% | flatter |

**The price, measured on the labelled pairs — as required:**

| quality metric | before | after |
|---|---:|---:|
| candidate recall on labelled `same` | 1.000 | **1.000** |
| merge recall on labelled `same` | 0.896 | **0.896** |
| false merges on labelled `different` | 0 | **0** |
| merged pairs, whole corpus | 13,215 | **13,215** |
| clusters, whole corpus | 6,050 | **6,050** |

**The measured price is zero** — on 900 labelled pairs and on all 13,215 corpus-wide merge
decisions, of which **0 were lost**. 1.89 million candidate pairs were removed and not one
of them was a pair the system would have merged.

That result is suspiciously clean, so here is the caveat rather than a victory lap. "Zero
lost merges" is measured at the 60-member cap on a 12,000-notice corpus. As the corpus grows,
bucket occupancy grows, and a *fixed* cap of 60 will eventually start suppressing buckets
that contain real duplicate families — a large opportunity cluster is itself a legitimately
large bucket. The cap should be re-derived, not inherited: `exp_e_skew.py` re-runs the whole
before/after comparison including the quality columns, and it should be run whenever the
corpus doubles. A mitigation whose price is zero today is not a mitigation whose price is
zero forever, and the script that measures the price is the deliverable, not the number 60.

**An alternative considered and rejected:** prune high-document-frequency shingles (IDF-style)
so template text never enters the signature. It attacks the mechanism at its root rather than
its symptom. It was rejected because it changes the *definition* of similarity established in
A(a), which would invalidate the margin measurement the K in A(b) and the threshold in A(c)
are both derived from. It is the right next change, and it requires re-running A(a) through
A(c), not a patch to B(e).

---

## The second non-negotiable: bookmarks that survive thirty re-runs

### Why the obvious designs fail

- **Hash of the notice text** — dies when the nodal copy is absorbed, since the cluster's
  content changes.
- **Hash of the member set** — dies on *every* absorption, by construction. This is the
  control measured below.
- **Smallest member `notice_id`** — dies whenever an *older* copy is scraped late, and
  `portal_profiles.md` warns that nodal agencies re-publish weeks later, so `published_at`
  ordering does not identify the first copy.

### The design (`src/cluster.py`)

Ids are minted from a monotonic counter and **carried forward by member overlap**:

- cluster overlaps exactly one existing opportunity → **reuse that id**;
- cluster overlaps several (two clusters merged) → keep the one with the smallest `seq`
  (oldest), retire the others, write `opportunity_alias(old_id → new_id)` rows;
- cluster overlaps none → **mint a new id**.

`resolve_bookmark()` walks the alias chain, so a card bookmarked in March still resolves
after the opportunity it named was absorbed in September. Union-find is order-independent
(smaller root always wins), so the same corpus yields the same clusters regardless of the
order pairs leave the database — a re-run is reproducible, not merely similar.

The one case that genuinely can break a bookmark is a **split**: a run decides one
opportunity is two. The larger part keeps the id, ties broken by oldest member; the rest
mint new ids. Splits are counted and reported, because "we never break a bookmark" would be
a lie.

### Measured: eight replayed nights (`experiments/exp_f_identity_stability.py`)

Night 1 sees the oldest 5,000 notices; each later night adds 1,000 more — roughly twice the
real arrival rate of 4,000/week, so the test is harsher than production. A bookmark is taken
on every opportunity existing after night 1, each with a witness notice. A bookmark counts as
broken only if `resolve(bookmarked_id)` no longer contains its witness.

| night | notices | clusters | ids reused | ids minted | ids retired to alias | splits | bookmarks broken |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 5,000 | — | — | — | — | — | (baseline, 2,574 taken) |
| 7 | 11,000 | 5,640 | 5,110 | 530 | 12 | 0 | 4 (0.155%) |
| **8** | **12,000** | **6,050** | **5,596** | **454** | **44** | **19** | **1 (0.039%)** |

Full table in `results/exp_f_identity_stability.json`, plot in `figures/fig_f_stability.png`.

**Result: on the final night, 1 of 2,574 bookmarks was broken — 0.039%.** Across all eight
nights the worst single night was 0.466%, and 43 break-events occurred in total.

Two things in that table are worth reading carefully.

**The count is not monotonic** — nights show 10, then 4, then 1. A bookmark can break and
then *heal*: a cluster splits when a marginal link falls below threshold, and re-merges a
night or two later when a further copy arrives and restores the link. This is the system
behaving correctly under growth, but it means "bookmarks broken" is a property of a given
night, not a debt that accumulates. The alias table is what makes healing possible — the
retired id is still pointing somewhere.

**The control.** Over the eight nights the pipeline **reused an existing id 28,817 times**.
An id derived from cluster content — a hash of the member set — would have been rewritten on
every one of those occasions, because each one is a cluster whose membership changed. That is
the difference between 0.039% and effectively 100%, and it is the entire justification for
the counter-plus-alias design over the obvious one.

**The 19 splits on night 8 are the honest residue.** They produced 1 broken bookmark because
in 18 of 19 cases the witness notice stayed with the part that kept the id. The `run` table
records which run performed each split, so affected cards can be identified from the database
rather than discovered by a bidder.

---

## Cost summary against the 20-minute window

| stage | seconds | what dominates |
|---|---:|---|
| read | 0.4 | 8 part files |
| normalise + shingle | 13.0 | pure Python string work — the obvious place to optimise next |
| sign (MinHash, K=1422) | 8.9 | numpy, 12,000 × 1,422 × ~156 |
| index into SQLite | 10.7 | 2,844,000 band rows + 12,000 signature BLOBs |
| retrieve candidates | 3.6 | one ordered B-tree sweep, capped |
| score 1.25M pairs | 4.5 | vectorised uint32 comparison |
| cluster + assign ids | 0.4 | union-find + alias maintenance |
| **total** | **41.1 s** | **3.4% of the 1,200 s window** |

Nightly reality is cheaper still: only new arrivals need normalising and signing
(~570/night), since signatures persist in the database. The 41.1 s figure is a **full
rebuild from scratch** — the expensive case, measured, not the incremental one.

---

## What I would do next, and what I am least sure of

1. **The exponential tail model in A(c) is the weakest load-bearing assumption in the
   submission.** It is fitted to 213 exceedances and then evaluated at 1e-6. A Pareto or
   Gumbel tail would give a different threshold, and I have no principled reason to prefer
   the exponential beyond its fit to the bulk. More adjudicated negatives above 0.35 would
   be worth more than any further engineering.
2. **IDF shingle pruning** (see B(e)) attacks the collision mechanism at its root.
3. **64-bit minima** would remove the +0.005 low-similarity bias, which currently biases
   toward the expensive error.
4. **The bucket cap must be re-derived as the corpus grows**, not inherited.
5. `estimated_value` and `closing_date` are stored but unused as features. Masking money in
   the text and then ignoring the parsed column is leaving evidence on the table — a
   parsed-value agreement check could recover margin on the negative side, which is where
   margin is worth 200×.
