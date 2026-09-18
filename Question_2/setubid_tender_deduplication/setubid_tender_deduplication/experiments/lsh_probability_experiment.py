"""
Section A(c). The candidate stage, its S-curve, and where the head of
product's 200:1 enters the settings.

Three things are produced:

 1. P(pair survives to the candidate stage | true similarity s), both as the
    closed form 1-(1-s^r)^b and as an empirical measurement: every adjudicated
    pair is checked against the candidate set the pipeline actually produced.
 2. The chosen operating point (b=237, r=6) marked on that curve, together
    with the two rejected alternatives it was chosen against.
 3. The merge threshold, derived from FALSE_MERGE_COST:FALSE_SPLIT_COST and
    from the *corpus* base rate rather than the label base rate. The label
    file is 31% `same`; the corpus is 0.021% `same`. Using the label base rate
    would understate the cost of a false merge by a factor of ~2,000.

Outputs: results/exp_c_scurve.json, figures/fig_c_scurve.png,
         figures/fig_c_threshold.png
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
import lsh  # noqa: E402
import minhash  # noqa: E402
import pipeline  # noqa: E402
from textnorm import jaccard, normalise, shingles  # noqa: E402

OUT = os.path.join(os.path.dirname(__file__), "..", "results")
FIG = os.path.join(os.path.dirname(__file__), "..", "figures")
DB = os.path.join(os.path.dirname(__file__), "..", "setubid_nocap.db")


def main():
    labels = loader.load_labels()
    df = loader.load_corpus()
    con, rep, art = pipeline.build(DB, fresh=True, bucket_cap=10**9,
                                   note="exp_c: uncapped baseline")

    ids = art["ids"]
    pos = {n: i for i, n in enumerate(ids)}
    sigs, shing = art["sigs"], art["shingles"]
    cand = set(art["pairs"])

    a = labels.notice_id_a.values
    b = labels.notice_id_b.values
    is_same = labels.label.values == "same"
    exact = np.array([jaccard(shing[pos[x]], shing[pos[y]]) for x, y in zip(a, b)])
    est = np.array([(sigs[pos[x]] == sigs[pos[y]]).mean() for x, y in zip(a, b)])
    retrieved = np.array([(min(x, y), max(x, y)) in cand for x, y in zip(a, b)])

    # ---- 1. empirical survival vs theory ---------------------------------
    edges = np.arange(0.0, 1.0001, 0.05)
    emp = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (exact >= lo) & (exact < hi)
        if m.sum() == 0:
            emp.append((float((lo + hi) / 2), 0, np.nan))
        else:
            emp.append((float((lo + hi) / 2), int(m.sum()), float(retrieved[m].mean())))

    s = np.linspace(0.01, 1.0, 400)
    chosen = lsh.p_candidate(s, config.BANDS, config.ROWS_PER_BAND)
    alts = {
        "b=237,r=6 (adopted)": (237, 6),
        "b=79,r=18 (cheaper, rejected)": (79, 18),
        "b=284,r=5 (safer, rejected)": (284, 5),
        "b=177,r=8 (rejected)": (177, 8),
    }

    # ---- 2. work created by each operating point -------------------------
    # measured, not modelled: re-band the real signatures for each alternative
    work = {}
    for name, (bb, rr) in alts.items():
        if bb * rr > config.SIG_K:
            continue
        bh = lsh.band_hashes_matrix(sigs[:, : bb * rr], bb, rr)
        pairs = set()
        for band in range(bb):
            order = np.argsort(bh[:, band], kind="stable")
            col = bh[order, band]
            start = 0
            for i in range(1, len(col) + 1):
                if i == len(col) or col[i] != col[start]:
                    if i - start > 1:
                        grp = sorted(ids[j] for j in order[start:i])
                        for u in range(len(grp)):
                            for v in range(u + 1, len(grp)):
                                pairs.add((grp[u], grp[v]))
                    start = i
        rec = float(np.mean([(min(x, y), max(x, y)) in pairs
                             for x, y in zip(a[is_same], b[is_same])]))
        work[name] = {"bands": bb, "rows": rr, "K_used": bb * rr,
                      "candidate_pairs": len(pairs),
                      "candidate_pairs_per_notice": round(2 * len(pairs) / len(ids), 1),
                      "recall_on_labelled_same": rec,
                      "knee_of_scurve": round(lsh.lsh_threshold(bb, rr), 4)}
        print(name, work[name], flush=True)

    # ---- 3. the threshold -------------------------------------------------
    # Label skew: reweight so that the measured rates are read at the corpus
    # base rate, not at the 31% of the label file.
    n_same, n_diff = int(is_same.sum()), int((~is_same).sum())
    # corpus base rate of `same` among *candidate* pairs, estimated from the
    # pipeline itself: merged pairs / candidate pairs. Deliberately estimated
    # from our own output rather than from the answer key.
    base_rate_candidates = rep["merged_pairs"] / rep["candidate_pairs"]

    # The empirical false-positive rate is zero above 0.4304, but "zero out of
    # 621" is not zero. By the rule of three the 95% upper bound on the rate is
    # 3/621 = 0.00483, which over 3.1M candidate pairs would be ~15,000 false
    # merges per night. The label file is simply too small to measure a rate we
    # need to know to 1e-8, so the tail is *modelled* and the model is stated:
    # exceedances of the `different` population over u=0.25 are fitted with an
    # exponential tail,  P(X>t) = P(X>u) * exp(-(t-u)/beta).
    u = 0.25
    neg = est[~is_same]
    exc = neg[neg > u] - u
    beta = float(exc.mean())
    p_exceed_u = float((neg > u).mean())

    def modelled_fpr(t):
        return p_exceed_u * np.exp(-(np.asarray(t, float) - u) / beta)

    ts = np.round(np.arange(0.30, 0.951, 0.005), 4)
    n_cand = rep["candidate_pairs"]
    rows = []
    for t in ts:
        fpr_emp = float((neg >= t).mean())
        fnr = float((est[is_same] < t).mean())
        fm = float(modelled_fpr(t)) * n_cand * (1 - base_rate_candidates)
        cost = (config.FALSE_MERGE_COST * (1 - base_rate_candidates) * float(modelled_fpr(t))
                + config.FALSE_SPLIT_COST * base_rate_candidates * fnr)
        rows.append((float(t), fpr_emp, fnr, cost, fm))
    rows = np.array(rows)
    # Operating rule: the smallest threshold whose *modelled* expected false
    # merges per nightly run stays under 1-in-30-runs (0.033). Lowering the
    # threshold below that point would buy extra true merges at worse than the
    # 200:1 exchange rate the head of product set.
    ok = rows[rows[:, 4] <= 0.033]
    t_budget = float(ok[:, 0].min()) if len(ok) else float(rows[:, 0].max())

    # PRIMARY RULE -- the marginal exchange rate.
    # Her ratio says a false merge is worth 200 missed merges. So lower the
    # threshold only while one more modelled false merge buys at least 200 more
    # recovered duplicate pairs. Densities: the `same` side is smoothed with a
    # Gaussian kernel over the 279 positives (h=0.02); the `different` side
    # comes from the fitted exponential tail, for which dFPR/dt = -FPR/beta.
    est_same = est[is_same]
    h = 0.02
    total_true_pairs = rep["merged_pairs"] / max(float((est_same >= config.MERGE_THRESHOLD).mean()), 1e-9)

    def dens_same(t):
        z = (np.asarray(t, float)[..., None] - est_same[None, :]) / h
        return np.exp(-0.5 * z ** 2).sum(-1) / (len(est_same) * h * np.sqrt(2 * np.pi))

    d_true_dt = total_true_pairs * dens_same(rows[:, 0])
    d_false_dt = n_cand * (1 - base_rate_candidates) * modelled_fpr(rows[:, 0]) / beta
    exch = d_true_dt / np.maximum(d_false_dt, 1e-12)
    # walk down from the top; stop at the last t whose exchange rate still
    # clears 200
    good = rows[:, 0][exch >= config.FALSE_MERGE_COST]
    t_star = float(good.min()) if len(good) else float(rows[:, 0].max())
    i_star = int(np.argmin(np.abs(rows[:, 0] - t_star)))
    exchange = float(exch[i_star])

    thresh_report = {
        "rule_of_three_95pct_upper_fpr_at_max_observed": 3 / n_diff,
        "false_merges_implied_by_that_bound_per_run": 3 / n_diff * n_cand,
        "tail_model": {"threshold_u": u, "P(X>u)": p_exceed_u, "beta": beta,
                       "n_exceedances": int(len(exc))},
        "modelled_fpr_at_chosen_t": float(modelled_fpr(t_star)),
        "expected_false_merges_per_run_at_chosen_t": float(rows[i_star, 4]),
        "threshold_from_false_merge_budget_rule": t_budget,
        "threshold_from_marginal_exchange_rule": t_star,
        "marginal_exchange_rate_at_chosen_t": exchange,
        "required_exchange_rate": config.FALSE_MERGE_COST,
        "estimated_total_true_duplicate_pairs": float(total_true_pairs),
        "label_base_rate_same": round(n_same / (n_same + n_diff), 4),
        "corpus_base_rate_same_among_candidates": round(base_rate_candidates, 6),
        "effective_cost_ratio_after_base_rate_correction":
            round(config.FALSE_MERGE_COST * (1 - base_rate_candidates)
                  / (config.FALSE_SPLIT_COST * base_rate_candidates), 1),
        "chosen_threshold": t_star,
        "recall_on_labelled_same_at_threshold": float((est[is_same] >= t_star).mean()),
        "false_merges_on_labelled_different_at_threshold": int((est[~is_same] >= t_star).sum()),
        "max_est_among_labelled_different": float(est[~is_same].max()),
        "min_est_among_labelled_same": float(est[is_same].min()),
        "deployed_threshold_in_config": config.MERGE_THRESHOLD,
    }
    print(json.dumps(thresh_report, indent=2))

    # ---- figures ----------------------------------------------------------
    fig, ax = plt.subplots(figsize=(8.5, 5.5))
    for name, (bb, rr) in alts.items():
        if bb * rr > config.SIG_K:
            continue
        style = "-" if "adopted" in name else "--"
        lw = 2.4 if "adopted" in name else 1.2
        ax.plot(s, lsh.p_candidate(s, bb, rr), style, lw=lw, label=name)
    ecent = [e[0] for e in emp if e[1] > 0]
    evals = [e[2] for e in emp if e[1] > 0]
    esz = [e[1] for e in emp if e[1] > 0]
    ax.scatter(ecent, evals, s=[min(160, 12 + 3 * n) for n in esz], c="k", zorder=5,
               label="measured on adjudicated pairs (size = n)")
    ax.axvline(thresh_report["max_est_among_labelled_different"], color="#b03030", ls=":",
               label=f"worst labelled `different` = {thresh_report['max_est_among_labelled_different']:.3f}")
    ax.axvline(thresh_report["min_est_among_labelled_same"], color="#2a6f97", ls=":",
               label=f"worst labelled `same` = {thresh_report['min_est_among_labelled_same']:.3f}")
    ax.plot([lsh.lsh_threshold(config.BANDS, config.ROWS_PER_BAND)],
            [0.5], "r*", ms=16, zorder=6,
            label=f"operating knee s={lsh.lsh_threshold(config.BANDS, config.ROWS_PER_BAND):.3f}")
    ax.set_xlabel("true Jaccard similarity s")
    ax.set_ylabel("P(pair reaches the candidate stage)")
    ax.set_title("A(c) retrieval S-curve: theory, measurement, and the point we chose")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8, loc="center right")
    fig.tight_layout()
    os.makedirs(FIG, exist_ok=True)
    fig.savefig(os.path.join(FIG, "fig_c_scurve.png"), dpi=130)

    fig2, ax2 = plt.subplots(1, 2, figsize=(12, 4.6))
    ax2[0].plot(rows[:, 0], rows[:, 4], lw=1.6)
    ax2[0].axhline(0.033, color="red", ls="--", label="budget: 1 false merge / 30 runs")
    ax2[0].axvline(t_star, color="green", ls=":", label=f"chosen t={t_star:.3f}")
    ax2[0].set_yscale("symlog", linthresh=1e-2)
    ax2[0].set_xlabel("merge threshold"); ax2[0].set_ylabel("expected false merges per run")
    ax2[0].legend(fontsize=8); ax2[0].grid(alpha=0.3)
    ax2[1].plot(rows[:, 0], 1 - rows[:, 2], lw=1.6, color="#2a6f97")
    ax2[1].axvline(t_star, color="green", ls=":")
    ax2[1].set_xlabel("merge threshold"); ax2[1].set_ylabel("recall on labelled `same`")
    ax2[1].grid(alpha=0.3)
    fig2.suptitle("A(c) where 200:1 enters: false-merge budget vs recall")
    fig2.tight_layout()
    fig2.savefig(os.path.join(FIG, "fig_c_threshold.png"), dpi=130)

    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "exp_c_scurve.json"), "w") as f:
        json.dump({"pipeline": rep, "empirical_survival": emp,
                   "operating_points": work, "threshold": thresh_report}, f, indent=2)
    print("written results/exp_c_scurve.json")


if __name__ == "__main__":
    main()
