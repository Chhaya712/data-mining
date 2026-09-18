"""
Section A(a). Four representations, one corpus, one label file.

  D1 (granularity)  : word 3-gram   vs word 5-gram
  D2 (signal/noise) : RAW (keep everything) vs CLEAN (strip boilerplate, mask
                      money / dates / reference numbers / bare numbers)

For each of the 2x2 configurations we compute exact Jaccard on every one of the
900 adjudicated pairs and report how well the score separates `same` from
`different`. We also print one named `same` pair and one named `different` pair
so the separation can be inspected by hand rather than trusted.

Outputs: results/exp_a_representation.json, figures/fig_a_separation.png
"""
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from textnorm import jaccard, learn_boilerplate, normalise, shingles  # noqa: E402
import loader  # noqa: E402

OUT = os.path.join(os.path.dirname(__file__), "..", "results")
FIG = os.path.join(os.path.dirname(__file__), "..", "figures")


def auc(pos, neg):
    """Probability a random same-pair scores above a random different-pair."""
    pos, neg = np.asarray(pos), np.asarray(neg)
    allv = np.concatenate([pos, neg])
    ranks = pd.Series(allv).rank().to_numpy()
    rp = ranks[: len(pos)].sum()
    return (rp - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))


def best_threshold(pos, neg, cost_ratio):
    """Threshold minimising cost_ratio * (false merges) + 1 * (missed merges)."""
    cands = np.unique(np.round(np.concatenate([pos, neg]), 4))
    best, bt = None, None
    for t in cands:
        fp = int((np.asarray(neg) >= t).sum())
        fn = int((np.asarray(pos) < t).sum())
        c = cost_ratio * fp + fn
        if best is None or c < best:
            best, bt = c, float(t)
    return bt, best


def main():
    df = loader.load_corpus()
    labels = loader.load_labels()
    print(f"corpus={len(df)} labelled_pairs={len(labels)}")

    # label skew -- the question tells us to find it before using the labels
    skew = labels.label.value_counts().to_dict()
    print("label skew:", skew)

    body_by_id = dict(zip(df.notice_id, df.body))
    title_by_id = dict(zip(df.notice_id, df.title))

    boiler = learn_boilerplate(df.body.tolist(), df_threshold=0.02)
    print(f"boilerplate lines learned (df>=2%): {len(boiler)}")

    ids = sorted(set(labels.notice_id_a) | set(labels.notice_id_b))
    results = {}
    curves = {}
    for mask_clean in (False, True):
        for width in (3, 5):
            name = f"{'CLEAN' if mask_clean else 'RAW'}-w{width}"
            sh = {}
            for nid in ids:
                txt = normalise(
                    title_by_id[nid],
                    body_by_id[nid],
                    boiler if mask_clean else None,
                    mask=mask_clean,
                )
                sh[nid] = shingles(txt, width)
            scores = np.array(
                [jaccard(sh[a], sh[b]) for a, b in zip(labels.notice_id_a, labels.notice_id_b)]
            )
            pos = scores[labels.label.values == "same"]
            neg = scores[labels.label.values == "different"]
            t200, c200 = best_threshold(pos, neg, 200)
            results[name] = {
                "same_mean": float(pos.mean()),
                "same_p05": float(np.percentile(pos, 5)),
                "same_min": float(pos.min()),
                "diff_mean": float(neg.mean()),
                "diff_p95": float(np.percentile(neg, 95)),
                "diff_max": float(neg.max()),
                "gap_p05same_minus_p95diff": float(np.percentile(pos, 5) - np.percentile(neg, 95)),
                "auc": float(auc(pos, neg)),
                "best_threshold_at_cost200": t200,
                "cost_at_that_threshold": c200,
                "recall_at_that_threshold": float((pos >= t200).mean()),
                "false_merges_at_that_threshold": int((neg >= t200).sum()),
                "mean_shingles_per_notice": float(np.mean([len(sh[i]) for i in ids])),
            }
            curves[name] = {"pos": pos.tolist(), "neg": neg.tolist()}
            print(name, json.dumps(results[name], indent=None))

    # --- the two hand-inspectable pairs the question asks for -----------------
    same_pairs = labels[labels.label == "same"]
    diff_pairs = labels[labels.label == "different"]

    def score_all(a, b):
        out = {}
        for mask_clean in (False, True):
            for width in (3, 5):
                n1 = normalise(title_by_id[a], body_by_id[a], boiler if mask_clean else None, mask_clean)
                n2 = normalise(title_by_id[b], body_by_id[b], boiler if mask_clean else None, mask_clean)
                out[f"{'CLEAN' if mask_clean else 'RAW'}-w{width}"] = round(
                    jaccard(shingles(n1, width), shingles(n2, width)), 4
                )
        return out

    # pick the hardest examples: the same-pair that RAW-w5 scores lowest, and
    # the different-pair that CLEAN-w5 scores highest.
    raw5 = np.array(curves["RAW-w5"]["pos"])
    hard_same = same_pairs.iloc[int(raw5.argmin())]
    clean5neg = np.array(curves["CLEAN-w5"]["neg"])
    hard_diff = diff_pairs.iloc[int(clean5neg.argmax())]
    worked = {
        "hard_same_pair": {
            "a": hard_same.notice_id_a, "b": hard_same.notice_id_b,
            "portals": [
                df.loc[df.notice_id == hard_same.notice_id_a, "portal_id"].iloc[0],
                df.loc[df.notice_id == hard_same.notice_id_b, "portal_id"].iloc[0],
            ],
            "scores": score_all(hard_same.notice_id_a, hard_same.notice_id_b),
        },
        "hard_different_pair": {
            "a": hard_diff.notice_id_a, "b": hard_diff.notice_id_b,
            "portals": [
                df.loc[df.notice_id == hard_diff.notice_id_a, "portal_id"].iloc[0],
                df.loc[df.notice_id == hard_diff.notice_id_b, "portal_id"].iloc[0],
            ],
            "scores": score_all(hard_diff.notice_id_a, hard_diff.notice_id_b),
        },
    }
    # a median same-pair too, so the reader sees a typical case not only a hard one
    med_idx = int(np.argsort(raw5)[len(raw5) // 2])
    med_same = same_pairs.iloc[med_idx]
    worked["typical_same_pair"] = {
        "a": med_same.notice_id_a, "b": med_same.notice_id_b,
        "portals": [
            df.loc[df.notice_id == med_same.notice_id_a, "portal_id"].iloc[0],
            df.loc[df.notice_id == med_same.notice_id_b, "portal_id"].iloc[0],
        ],
        "scores": score_all(med_same.notice_id_a, med_same.notice_id_b),
    }
    print(json.dumps(worked, indent=2))

    # --- cost of the CLEAN adoption -----------------------------------------
    # masking destroys money/date/ref evidence; measure how many `different`
    # pairs are pushed up by it.
    raw_neg = np.array(curves["RAW-w5"]["neg"])
    cl_neg = np.array(curves["CLEAN-w5"]["neg"])
    raw_pos = np.array(curves["RAW-w5"]["pos"])
    cl_pos = np.array(curves["CLEAN-w5"]["pos"])
    adoption_cost = {
        "different_pairs_score_rise_mean": float((cl_neg - raw_neg).mean()),
        "different_pairs_above_0.5_raw": int((raw_neg >= 0.5).sum()),
        "different_pairs_above_0.5_clean": int((cl_neg >= 0.5).sum()),
        "same_pairs_score_rise_mean": float((cl_pos - raw_pos).mean()),
        "same_pairs_below_0.5_raw": int((raw_pos < 0.5).sum()),
        "same_pairs_below_0.5_clean": int((cl_pos < 0.5).sum()),
    }
    print("adoption cost:", json.dumps(adoption_cost, indent=2))

    # --- figure --------------------------------------------------------------
    fig, axes = plt.subplots(2, 2, figsize=(11, 7), sharex=True)
    for ax, name in zip(axes.ravel(), ["RAW-w3", "RAW-w5", "CLEAN-w3", "CLEAN-w5"]):
        ax.hist(curves[name]["neg"], bins=40, range=(0, 1), alpha=0.65,
                label="labelled different", color="#b03030")
        ax.hist(curves[name]["pos"], bins=40, range=(0, 1), alpha=0.65,
                label="labelled same", color="#2a6f97")
        ax.set_title(f"{name}   AUC={results[name]['auc']:.4f}")
        ax.set_yscale("log")
        ax.set_xlabel("exact Jaccard")
    axes[0][0].legend()
    fig.suptitle("A(a) separation of adjudicated pairs under four representations")
    fig.tight_layout()
    os.makedirs(FIG, exist_ok=True)
    fig.savefig(os.path.join(FIG, "fig_a_separation.png"), dpi=130)

    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "exp_a_representation.json"), "w") as f:
        json.dump(
            {"label_skew": skew, "n_boilerplate_lines": len(boiler),
             "configs": results, "worked_pairs": worked,
             "adoption_cost_of_CLEAN": adoption_cost},
            f, indent=2,
        )
    print("written results/exp_a_representation.json")


if __name__ == "__main__":
    main()
