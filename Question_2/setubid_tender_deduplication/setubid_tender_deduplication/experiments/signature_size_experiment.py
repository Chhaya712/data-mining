"""
Section A(b). Fix K from a requirement, then measure whether the estimator did
what the requirement assumed.

The argument (stated before implementing, see REPORT.md B.1):

  1. exp_a measured the empirical margin between the two adjudicated
     populations under the adopted representation: max(different)=0.4052,
     min(same)=0.5111, so any threshold in that interval separates the label
     set perfectly, and the half-margin is (0.5111-0.4052)/2 = 0.0530.
  2. The estimate must not, by itself, carry a pair across that margin. We
     require a 4-sigma excursion to still fit inside the half-margin:
        4 * sqrt(J(1-J)/K) <= 0.0530  at the worst case J=0.5
        => sqrt(0.25/K) <= 0.01325  =>  K >= 1424.
  3. K must factor as BANDS x ROWS_PER_BAND for the band index in A(c).
     ROWS_PER_BAND=6 is fixed there; the smallest admissible K is
     237*6 = 1422, which gives 4 sigma = 0.0530 -- exactly at the bound.

Then the loop is closed: exact Jaccard is computed for all 900 labelled pairs
and for 5,000 random corpus pairs, the realised |estimate - exact| is compared
against the predicted sd, and the K-sweep shows where a smaller K would have
started to cost decisions.

Outputs: results/exp_b_signature_size.json, figures/fig_b_error.png
"""
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import config  # noqa: E402
import loader  # noqa: E402
import minhash  # noqa: E402
from textnorm import jaccard, learn_boilerplate, normalise, shingles  # noqa: E402

OUT = os.path.join(os.path.dirname(__file__), "..", "results")
FIG = os.path.join(os.path.dirname(__file__), "..", "figures")


def main():
    df = loader.load_corpus()
    labels = loader.load_labels()
    boiler = learn_boilerplate(df.body.tolist(), config.BOILERPLATE_DF)

    idx = {n: i for i, n in enumerate(df.notice_id)}
    rng = np.random.default_rng(7)
    rand_pairs = rng.integers(0, len(df), size=(5000, 2))
    rand_pairs = rand_pairs[rand_pairs[:, 0] != rand_pairs[:, 1]]

    need = set(labels.notice_id_a) | set(labels.notice_id_b)
    need |= {df.notice_id.iloc[i] for p in rand_pairs for i in p}

    sh, sh_hash = {}, {}
    for nid in need:
        row = df.iloc[idx[nid]]
        s = shingles(normalise(row.title, row.body, boiler, config.MASK_VOLATILE),
                     config.SHINGLE_WIDTH)
        sh[nid] = s
        sh_hash[nid] = minhash.shingle_hashes(s)

    kmax = 4096
    a, b = minhash.make_params(kmax, config.MINHASH_SEED)
    sigs = {nid: minhash.signature(sh_hash[nid], a, b) for nid in need}

    lab_pairs = list(zip(labels.notice_id_a, labels.notice_id_b))
    rnd_pairs = [(df.notice_id.iloc[i], df.notice_id.iloc[j]) for i, j in rand_pairs]
    exact_lab = np.array([jaccard(sh[x], sh[y]) for x, y in lab_pairs])
    exact_rnd = np.array([jaccard(sh[x], sh[y]) for x, y in rnd_pairs])
    is_same = (labels.label.values == "same")

    ks = [64, 128, 256, 512, 1024, 1422, 2048, 4096]
    sweep = {}
    for k in ks:
        est_l = np.array([(sigs[x][:k] == sigs[y][:k]).mean() for x, y in lab_pairs])
        est_r = np.array([(sigs[x][:k] == sigs[y][:k]).mean() for x, y in rnd_pairs])
        err_l = est_l - exact_lab
        err_r = est_r - exact_rnd
        pred_sd_l = np.sqrt(exact_lab * (1 - exact_lab) / k)
        # decisions made on the estimate vs decisions made on exact truth
        t = config.MERGE_THRESHOLD
        fm = int(((est_l >= t) & (~is_same)).sum())
        fs = int(((est_l < t) & (is_same)).sum())
        sweep[k] = {
            "mean_signed_error_labelled": float(err_l.mean()),
            "rmse_labelled": float(np.sqrt((err_l ** 2).mean())),
            "predicted_mean_sd_labelled": float(pred_sd_l.mean()),
            "ratio_realised_to_predicted": float(np.sqrt((err_l ** 2).mean()) / pred_sd_l.mean()),
            "max_abs_error_labelled": float(np.abs(err_l).max()),
            "rmse_random_pairs": float(np.sqrt((err_r ** 2).mean())),
            "false_merges_at_thr": fm,
            "false_splits_at_thr": fs,
            "expected_cost": config.FALSE_MERGE_COST * fm + config.FALSE_SPLIT_COST * fs,
            "bytes_per_notice": k * 4,
            "corpus_MB_at_12k": round(k * 4 * 12000 / 1e6, 1),
        }
        print(k, json.dumps(sweep[k]))

    k = config.SIG_K
    est = np.array([(sigs[x][:k] == sigs[y][:k]).mean() for x, y in lab_pairs])
    err = est - exact_lab
    # stratify the error by true similarity -- the variance is J(1-J)/K, so it
    # must be largest near J=0.5 and collapse near J=1. Does it?
    bins = [(0.0, 0.2), (0.2, 0.35), (0.35, 0.5), (0.5, 0.7), (0.7, 0.9), (0.9, 1.0)]
    strat = {}
    for lo, hi in bins:
        m = (exact_lab >= lo) & (exact_lab < hi)
        if m.sum() < 3:
            continue
        strat[f"{lo}-{hi}"] = {
            "n": int(m.sum()),
            "realised_sd": float(err[m].std(ddof=1)),
            "predicted_sd": float(np.sqrt((exact_lab[m] * (1 - exact_lab[m]) / k)).mean()),
            "mean_signed_error": float(err[m].mean()),
        }
    print(json.dumps(strat, indent=2))

    # figure
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.6))
    ax[0].scatter(exact_lab, est, s=8, c=np.where(is_same, "#2a6f97", "#b03030"), alpha=0.6)
    ax[0].plot([0, 1], [0, 1], "k--", lw=1)
    ax[0].axhline(config.MERGE_THRESHOLD, color="green", lw=1, ls=":")
    ax[0].axvline(config.MERGE_THRESHOLD, color="green", lw=1, ls=":")
    ax[0].set_xlabel("exact Jaccard"); ax[0].set_ylabel(f"MinHash estimate (K={k})")
    ax[0].set_title("estimate vs exact, 900 adjudicated pairs")

    kk = np.array(ks)
    ax[1].plot(kk, [sweep[x]["rmse_labelled"] for x in ks], "o-", label="realised RMSE")
    ax[1].plot(kk, [sweep[x]["predicted_mean_sd_labelled"] for x in ks], "s--",
               label="predicted sd  sqrt(J(1-J)/K)")
    ax[1].axvline(k, color="green", ls=":", label=f"adopted K={k}")
    ax[1].axhline(0.0530 / 4, color="grey", ls="-.", label="requirement sigma<=0.01325")
    ax[1].set_xscale("log"); ax[1].set_yscale("log")
    ax[1].set_xlabel("K"); ax[1].set_ylabel("error")
    ax[1].legend(fontsize=8); ax[1].set_title("A(b) sizing: requirement vs realisation")
    fig.tight_layout()
    os.makedirs(FIG, exist_ok=True)
    fig.savefig(os.path.join(FIG, "fig_b_error.png"), dpi=130)

    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "exp_b_signature_size.json"), "w") as f:
        json.dump({"requirement": {"half_margin": 0.0530, "sigmas_required": 4,
                                   "sigma_bound": 0.01325, "K_floor": 1424,
                                   "K_adopted": k, "rows_per_band": config.ROWS_PER_BAND,
                                   "bands": config.BANDS},
                   "sweep": sweep, "stratified_error_at_adopted_K": strat},
                  f, indent=2)
    print("written results/exp_b_signature_size.json")


if __name__ == "__main__":
    main()
