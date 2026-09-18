"""
Section B(e). Where the design betrays us.

Total candidate work is fine (3.1M pairs, ~50 s). The distribution is not.
This script:

  1. measures candidate work per notice and per bucket, and attributes the
     tail to portals using portal_profiles.md;
  2. explains the mechanism and projects it against the 20-minute budget as
     the corpus grows at 4,000 notices/week;
  3. applies a mitigation (cap the bucket size that a band is allowed to
     expand) and re-measures runtime, distribution AND the retrieval quality
     that the cap cost, on labelled_pairs.csv.

Outputs: results/exp_e_skew.json, figures/fig_e_skew.png
"""
import collections
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import config  # noqa: E402
import db as dbmod  # noqa: E402
import loader  # noqa: E402
import pipeline  # noqa: E402

OUT = os.path.join(os.path.dirname(__file__), "..", "results")
FIG = os.path.join(os.path.dirname(__file__), "..", "figures")
NODAL = {"P001", "P002", "P003", "P004", "P005", "P006"}


def per_notice_work(pairs):
    c = collections.Counter()
    for a, b in pairs:
        c[a] += 1
        c[b] += 1
    return c


def describe(counter, ids):
    v = np.array([counter.get(i, 0) for i in ids], dtype=float)
    v.sort()
    tot = v.sum()
    out = {"total_candidate_slots": int(tot), "mean": float(v.mean()),
           "median": float(np.median(v)), "p90": float(np.percentile(v, 90)),
           "p99": float(np.percentile(v, 99)), "max": float(v.max())}
    for frac in (0.01, 0.05, 0.10):
        k = int(len(v) * frac)
        out[f"share_of_work_from_top_{int(frac*100)}pct_of_notices"] = float(v[-k:].sum() / tot)
    return out


def main():
    labels = loader.load_labels()
    df = loader.load_corpus()
    portal = dict(zip(df.notice_id, df.portal_id))

    # ---------- BEFORE ------------------------------------------------------
    con, rep_before, art = pipeline.build(
        os.path.join(os.path.dirname(__file__), "..", "setubid_nocap.db"),
        fresh=True, bucket_cap=10**9, note="exp_e: before mitigation")
    ids = art["ids"]
    work_before = per_notice_work(art["pairs"])
    dist_before = describe(work_before, ids)

    buckets = con.execute("SELECT members, COUNT(*) FROM bucket_stat GROUP BY members").fetchall()
    bsz = np.repeat([b[0] for b in buckets], [b[1] for b in buckets])
    bucket_stats = {
        "buckets_total": int(len(bsz)),
        "buckets_with_1_member": int((bsz == 1).sum()),
        "largest_bucket": int(bsz.max()),
        "pairs_emitted_total": int((bsz * (bsz - 1) // 2).sum()),
        "share_of_pairs_from_buckets_over_60":
            float((bsz[bsz > 60] * (bsz[bsz > 60] - 1) // 2).sum()
                  / (bsz * (bsz - 1) // 2).sum()),
        "share_of_pairs_from_buckets_over_200":
            float((bsz[bsz > 200] * (bsz[bsz > 200] - 1) // 2).sum()
                  / (bsz * (bsz - 1) // 2).sum()),
    }

    # attribution: who is in the expensive tail?
    v = np.array([work_before.get(i, 0) for i in ids])
    order = np.argsort(-v)
    top1 = [ids[i] for i in order[: len(ids) // 100]]
    attribution = {
        "corpus_share_nodal": float(np.mean([portal[i] in NODAL for i in ids])),
        "top1pct_share_nodal": float(np.mean([portal[i] in NODAL for i in top1])),
        "top1pct_portal_counts": collections.Counter(portal[i] for i in top1).most_common(10),
        "mean_work_by_portal_class": {
            "nodal": float(np.mean([work_before.get(i, 0) for i in ids if portal[i] in NODAL])),
            "other": float(np.mean([work_before.get(i, 0) for i in ids if portal[i] not in NODAL])),
        },
        "shingle_count_top1pct": float(np.mean(
            [len(art["shingles"][ids.index(i)]) for i in top1[:200]])),
        "shingle_count_corpus": float(np.mean([len(s) for s in art["shingles"]])),
    }

    # ---------- why: the mechanism, measured -------------------------------
    import collections as _c
    sdf = _c.Counter()
    for s_ in art["shingles"]:
        sdf.update(s_)
    n = len(ids)
    common = {g for g, c in sdf.items() if c / n > 0.01}
    frac_common = float(np.mean([np.mean([g in common for g in s_])
                                 for s_ in art["shingles"][:3000]]))
    sizes = np.array([len(s_) for s_ in art["shingles"]])
    big = con.execute(
        "SELECT band_no, band_hash, members FROM bucket_stat ORDER BY members DESC LIMIT 1"
    ).fetchone()
    mem = [r[0] for r in con.execute(
        "SELECT notice_id FROM band_bucket WHERE band_no=? AND band_hash=?", (big[0], big[1]))]
    truth = loader.load_truth_clusters()
    distinct = (truth.set_index("notice_id").loc[mem].cluster_id.nunique()
                if truth is not None else None)
    mechanism = {
        "top_shingles_by_document_frequency":
            [(g, round(c / n, 3)) for g, c in sdf.most_common(6)],
        "mean_fraction_of_a_notice_shingles_that_are_corpus_common_gt1pct": frac_common,
        "shingles_per_notice_p1_p50_p99": [float(x) for x in np.percentile(sizes, [1, 50, 99])],
        "largest_bucket": {"band_no": big[0], "members": big[2],
                           "distinct_true_opportunities_inside": distinct,
                           "portal_mix": _c.Counter(portal[i] for i in mem).most_common(6)},
    }

    # ---------- growth projection ------------------------------------------
    # pair emission inside one bucket is quadratic in its membership, and
    # membership grows linearly with corpus size for a bucket whose occupancy
    # is driven by a template rather than by a real duplicate.
    n0 = len(ids)
    proj = []
    for weeks in (0, 26, 52, 104, 156):
        n = n0 + 4000 * weeks
        scale = n / n0
        # tail buckets scale quadratically, the rest linearly
        tail_share = bucket_stats["share_of_pairs_from_buckets_over_60"]
        pairs = rep_before["candidate_pairs"] * (tail_share * scale ** 2 + (1 - tail_share) * scale)
        secs = (rep_before["stages"]["2_normalise"] + rep_before["stages"]["3_sign"]) * scale \
            + rep_before["stages"]["4_index"] * scale \
            + (rep_before["stages"]["5_retrieve"] + rep_before["stages"]["6_score"]) \
            * pairs / rep_before["candidate_pairs"]
        proj.append({"weeks": weeks, "notices": int(n), "projected_candidate_pairs": int(pairs),
                     "projected_seconds": round(secs, 1), "over_budget": secs > 1200})
    breach = next((p for p in proj if p["over_budget"]), None)

    # ---------- AFTER -------------------------------------------------------
    con2, rep_after, art2 = pipeline.build(
        os.path.join(os.path.dirname(__file__), "..", "setubid_capped.db"),
        fresh=True, bucket_cap=config.BUCKET_CAP, note="exp_e: after mitigation")
    work_after = per_notice_work(art2["pairs"])
    dist_after = describe(work_after, ids)

    # ---------- what the mitigation cost, measured on the labels ------------
    def quality(art_, rep_):
        cand = set(art_["pairs"])
        pos = {n: i for i, n in enumerate(art_["ids"])}
        sigs = art_["sigs"]
        a, b = labels.notice_id_a.values, labels.notice_id_b.values
        same = labels.label.values == "same"
        retr = np.array([(min(x, y), max(x, y)) in cand for x, y in zip(a, b)])
        est = np.array([(sigs[pos[x]] == sigs[pos[y]]).mean() for x, y in zip(a, b)])
        merged = retr & (est >= config.MERGE_THRESHOLD)
        return {
            "candidate_recall_on_labelled_same": float(retr[same].mean()),
            "merge_recall_on_labelled_same": float(merged[same].mean()),
            "false_merges_on_labelled_different": int(merged[~same].sum()),
            "candidate_pairs": rep_["candidate_pairs"],
            "merged_pairs": rep_["merged_pairs"],
            "clusters": rep_["clusters"],
            "seconds_total": rep_["seconds_total"],
        }

    q_before, q_after = quality(art, rep_before), quality(art2, rep_after)

    # corpus-level effect of the cap, independent of the 900 labels
    lost = set(art["pairs"]) - set(art2["pairs"])
    kept_merges_before = {(x, y) for (x, y), e in zip(art["pairs"], art["est"])
                          if e >= config.MERGE_THRESHOLD}
    kept_merges_after = {(x, y) for (x, y), e in zip(art2["pairs"], art2["est"])
                         if e >= config.MERGE_THRESHOLD}
    corpus_cost = {
        "candidate_pairs_removed": len(lost),
        "merge_decisions_lost": len(kept_merges_before - kept_merges_after),
        "merge_decisions_lost_pct": round(
            100 * len(kept_merges_before - kept_merges_after) / max(len(kept_merges_before), 1), 3),
        "clusters_before": rep_before["clusters"], "clusters_after": rep_after["clusters"],
    }

    result = {
        "before": {"run": rep_before, "per_notice_work": dist_before,
                   "buckets": bucket_stats, "attribution": attribution,
                   "mechanism": mechanism,
                   "quality": q_before},
        "growth_projection_uncapped": proj,
        "first_breach_of_20min_budget": breach,
        "mitigation": {"rule": f"a band whose bucket has more than {config.BUCKET_CAP} "
                               f"members is not expanded into pairs",
                       "bucket_cap": config.BUCKET_CAP},
        "after": {"run": rep_after, "per_notice_work": dist_after, "quality": q_after},
        "price_of_mitigation": corpus_cost,
    }
    print(json.dumps(result, indent=2, default=str))

    # ---------- figure ------------------------------------------------------
    fig, ax = plt.subplots(1, 3, figsize=(15, 4.4))
    vb = np.sort(np.array([work_before.get(i, 0) for i in ids]))[::-1]
    va = np.sort(np.array([work_after.get(i, 0) for i in ids]))[::-1]
    ax[0].plot(np.arange(1, len(vb) + 1), vb, label="before cap")
    ax[0].plot(np.arange(1, len(va) + 1), va, label="after cap")
    ax[0].set_xscale("log"); ax[0].set_yscale("symlog")
    ax[0].set_xlabel("notice rank"); ax[0].set_ylabel("candidate pairs touching this notice")
    ax[0].set_title("work per notice is not uniform"); ax[0].legend(); ax[0].grid(alpha=0.3)

    cum = np.cumsum(vb) / vb.sum()
    ax[1].plot(np.arange(1, len(vb) + 1) / len(vb) * 100, cum * 100)
    ax[1].set_xlabel("% of notices (heaviest first)"); ax[1].set_ylabel("% of candidate work")
    ax[1].axvline(1, color="red", ls=":"); ax[1].grid(alpha=0.3)
    ax[1].set_title(f"top 1% of notices = "
                    f"{dist_before['share_of_work_from_top_1pct_of_notices']*100:.1f}% of work")

    ax[2].plot([p["notices"] for p in proj], [p["projected_seconds"] for p in proj], "o-",
               label="uncapped projection")
    ax[2].axhline(1200, color="red", ls="--", label="20-minute window")
    ax[2].scatter([len(ids)], [rep_after["seconds_total"]], c="green", zorder=5,
                  label="measured, capped")
    ax[2].set_xlabel("corpus size (notices)"); ax[2].set_ylabel("nightly seconds")
    ax[2].set_yscale("log"); ax[2].legend(fontsize=8); ax[2].grid(alpha=0.3)
    ax[2].set_title("growth at 4,000 notices/week")
    fig.tight_layout()
    os.makedirs(FIG, exist_ok=True)
    fig.savefig(os.path.join(FIG, "fig_e_skew.png"), dpi=130)

    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "exp_e_skew.json"), "w") as f:
        json.dump(result, f, indent=2, default=str)
    print("written results/exp_e_skew.json")


if __name__ == "__main__":
    main()
