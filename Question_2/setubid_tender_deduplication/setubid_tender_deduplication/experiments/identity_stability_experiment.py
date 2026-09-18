"""
The second non-negotiable constraint: a bookmarked card id must still point at
the same opportunity after the pipeline has been re-run many times over a
corpus that keeps absorbing new copies.

Method: replay the corpus as eight successive nights. Night 1 sees the oldest
5,000 notices; each later night adds 1,000 more -- about twice the real arrival
rate of 4,000/week, so the test is harsher than production. After night 1 we take a bookmark on every
opportunity then in existence, recording (bookmarked_id, a witness notice that
belonged to it). After every subsequent night we check, for each bookmark:

    resolve(bookmarked_id)  ==  the opportunity the witness notice is in now ?

`resolve` walks opportunity_alias, so an id that was retired because its
cluster was absorbed into an older one still answers correctly. A bookmark
counts as broken only if it resolves to an opportunity that no longer contains
its witness.

Outputs: results/exp_f_identity_stability.json, figures/fig_f_stability.png
"""
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import config  # noqa: E402
import db as dbmod  # noqa: E402
import pipeline  # noqa: E402

OUT = os.path.join(os.path.dirname(__file__), "..", "results")
FIG = os.path.join(os.path.dirname(__file__), "..", "figures")
DB = os.path.join(os.path.dirname(__file__), "..", "setubid_nightly.db")

NIGHTS = 8
START = 5000
STEP = 1000


def main():
    history = []
    bookmarks = {}
    for night in range(1, NIGHTS + 1):
        n = min(START + STEP * (night - 1), 12000)
        con, rep, _ = pipeline.build(DB, fresh=(night == 1),
                                     bucket_cap=config.BUCKET_CAP,
                                     note=f"night {night}", first_n=n)
        cur = dict(con.execute("SELECT notice_id, opportunity_id FROM notice_opportunity"))
        if night == 1:
            # one bookmark per opportunity, witnessed by its lowest notice_id
            wit = {}
            for nid, opp in cur.items():
                if opp not in wit or nid < wit[opp]:
                    wit[opp] = nid
            bookmarks = {opp: w for opp, w in wit.items()}
            broken = 0
        else:
            broken = 0
            for booked_id, witness in bookmarks.items():
                resolved = dbmod.resolve_bookmark(con, booked_id)
                if cur.get(witness) != resolved:
                    broken += 1
        history.append({
            "night": night, "notices": n,
            "clusters": rep["clusters"], "ids_minted": rep["ids_minted"],
            "ids_reused": rep["ids_reused"],
            "ids_retired_into_alias": rep["ids_retired_into_alias"],
            "opportunities_split": rep["opportunities_split"],
            "bookmarks_tracked": len(bookmarks),
            "bookmarks_broken": broken,
            "bookmarks_broken_pct": round(100 * broken / max(len(bookmarks), 1), 3),
            "seconds": rep["seconds_total"],
        })
        print(json.dumps(history[-1]), flush=True)
        con.close()
        os.makedirs(OUT, exist_ok=True)
        with open(os.path.join(OUT, "exp_f_identity_stability.json"), "w") as f:
            json.dump({"nights": history, "partial": night < NIGHTS}, f, indent=2)

    # a control: what a content-derived id would have done. An id defined as a
    # hash of the member set changes whenever the set changes, so every cluster
    # that absorbed a copy would have broken its bookmark.
    control_broken = sum(h["ids_reused"] for h in history[1:])
    summary = {
        "nights": history,
        "bookmarks_tracked": history[0]["bookmarks_tracked"],
        "bookmarks_broken_total": sum(h["bookmarks_broken"] for h in history),
        "worst_night_broken_pct": max(h["bookmarks_broken_pct"] for h in history),
        "control_content_hash_id_would_have_rewritten": control_broken,
        "max_night_seconds": max(h["seconds"] for h in history),
        "budget_seconds": 1200,
    }
    print(json.dumps(summary, indent=2))

    fig, ax = plt.subplots(1, 2, figsize=(11, 4.2))
    ax[0].plot([h["night"] for h in history], [h["bookmarks_broken"] for h in history], "o-")
    ax[0].set_xlabel("night"); ax[0].set_ylabel("broken bookmarks")
    ax[0].set_title(f"of {summary['bookmarks_tracked']} bookmarks taken on night 1")
    ax[0].grid(alpha=0.3); ax[0].set_ylim(bottom=-0.5)
    ax[1].plot([h["notices"] for h in history], [h["seconds"] for h in history], "o-")
    ax[1].axhline(1200, color="red", ls="--", label="20-minute window")
    ax[1].set_xlabel("corpus size"); ax[1].set_ylabel("nightly seconds")
    ax[1].legend(); ax[1].grid(alpha=0.3)
    fig.suptitle("Identity stability and cost across eight replayed nights")
    fig.tight_layout()
    os.makedirs(FIG, exist_ok=True)
    fig.savefig(os.path.join(FIG, "fig_f_stability.png"), dpi=130)

    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "exp_f_identity_stability.json"), "w") as f:
        json.dump(summary, f, indent=2)


if __name__ == "__main__":
    main()
