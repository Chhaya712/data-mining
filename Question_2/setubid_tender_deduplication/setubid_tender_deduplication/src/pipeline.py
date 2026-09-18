"""
End-to-end nightly pipeline. Run:  python3 -m src.pipeline --fresh

Stages, each timed separately so the 20-minute budget can be attributed:
  1 read        Parquet/CSV -> memory
  2 normalise   A(a): strip boilerplate, mask volatiles, 5-gram shingles
  3 sign        A(b): K=1422 MinHash
  4 index       B(d): write notice / signature / band_bucket into SQLite
  5 retrieve    A(c): expand buckets into candidate pairs (with B(e) cap)
  6 score       estimate similarity from signatures, keep pairs >= threshold
  7 identify    union-find + bookmark-stable opportunity ids
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "experiments"))

import cluster as clustermod  # noqa: E402
import config  # noqa: E402
import db as dbmod  # noqa: E402
import loader  # noqa: E402
import lsh  # noqa: E402
import minhash  # noqa: E402
from textnorm import learn_boilerplate, normalise, shingles  # noqa: E402


class Timer:
    def __init__(self):
        self.t = {}
        self._s = None
        self._n = None

    def start(self, name):
        self._s, self._n = time.perf_counter(), name

    def stop(self):
        self.t[self._n] = self.t.get(self._n, 0.0) + time.perf_counter() - self._s
        print(f"  [{self._n}] {self.t[self._n]:.1f}s", flush=True)


def build(db_path=None, fresh=True, bucket_cap=None, note="", first_n=None):
    db_path = db_path or config.DB_PATH
    cap = config.BUCKET_CAP if bucket_cap is None else bucket_cap
    T = Timer()
    t0 = time.perf_counter()

    T.start("1_read")
    df = loader.load_corpus()
    if first_n is not None:
        # simulate a corpus as it stood on an earlier night: notices arrive in
        # published_at order
        df = df.sort_values(["published_at", "notice_id"]).head(first_n).reset_index(drop=True)
    T.stop()

    T.start("2_normalise")
    boiler = learn_boilerplate(df.body.tolist(), config.BOILERPLATE_DF)
    norm, shing, ckey = [], [], []
    for title, body in zip(df.title, df.body):
        t = normalise(title, body, boiler, config.MASK_VOLATILE)
        s = shingles(t, config.SHINGLE_WIDTH)
        norm.append(t)
        shing.append(s)
        ckey.append(hashlib.blake2b(t.encode(), digest_size=16).hexdigest())
    T.stop()

    T.start("3_sign")
    a, b = minhash.make_params(config.SIG_K, config.MINHASH_SEED)
    sigs = np.empty((len(df), config.SIG_K), dtype=np.uint32)
    for i, s in enumerate(shing):
        sigs[i] = minhash.signature(minhash.shingle_hashes(s), a, b)
    T.stop()

    T.start("4_index")
    con = dbmod.init(db_path, fresh=fresh)
    ids = df.notice_id.tolist()
    con.executemany(
        "INSERT OR REPLACE INTO notice VALUES (?,?,?,?,?,?,?,?)",
        [(ids[i], df.portal_id.iloc[i], str(df.published_at.iloc[i]), df.title.iloc[i],
          float(df.estimated_value.iloc[i]) if df.estimated_value.iloc[i] == df.estimated_value.iloc[i] else None,
          str(df.closing_date.iloc[i]), len(shing[i]), ckey[i]) for i in range(len(df))],
    )
    con.executemany(
        "INSERT OR REPLACE INTO signature VALUES (?,?,?)",
        [(ids[i], config.SIG_K, sigs[i].tobytes()) for i in range(len(df))],
    )
    bh = lsh.band_hashes_matrix(sigs, config.BANDS, config.ROWS_PER_BAND)
    rows = [(int(bn), int(bh[i, bn]), ids[i]) for i in range(len(df)) for bn in range(config.BANDS)]
    con.executemany("INSERT OR REPLACE INTO band_bucket VALUES (?,?,?)", rows)
    con.execute("DELETE FROM bucket_stat")
    con.execute(
        "INSERT INTO bucket_stat(band_no,band_hash,members) "
        "SELECT band_no,band_hash,COUNT(*) FROM band_bucket GROUP BY band_no,band_hash"
    )
    con.execute("UPDATE bucket_stat SET suppressed=1 WHERE members > ?", (cap,))
    con.commit()
    T.stop()

    T.start("5_retrieve")
    pairs = set()
    suppressed_buckets = 0
    cur = con.execute(
        "SELECT bb.band_no, bb.band_hash, GROUP_CONCAT(bb.notice_id) "
        "FROM band_bucket bb JOIN bucket_stat bs "
        "  ON bs.band_no=bb.band_no AND bs.band_hash=bb.band_hash "
        "WHERE bs.members > 1 AND bs.suppressed = 0 "
        "GROUP BY bb.band_no, bb.band_hash"
    )
    for _, _, members in cur:
        m = sorted(members.split(","))
        for i in range(len(m)):
            for j in range(i + 1, len(m)):
                pairs.add((m[i], m[j]))
    suppressed_buckets = con.execute(
        "SELECT COUNT(*) FROM bucket_stat WHERE suppressed=1").fetchone()[0]
    pairs = sorted(pairs)
    T.stop()
    print(f"  candidate pairs: {len(pairs):,}  (suppressed buckets: {suppressed_buckets:,})")

    T.start("6_score")
    pos = {n: i for i, n in enumerate(ids)}
    left = np.fromiter((pos[p[0]] for p in pairs), dtype=np.int64, count=len(pairs))
    right = np.fromiter((pos[p[1]] for p in pairs), dtype=np.int64, count=len(pairs))
    est = np.empty(len(pairs), dtype=np.float32)
    CH = 20000
    for s in range(0, len(pairs), CH):
        e = min(s + CH, len(pairs))
        est[s:e] = (sigs[left[s:e]] == sigs[right[s:e]]).mean(axis=1)
    keep = est >= config.MERGE_THRESHOLD
    con.execute("DELETE FROM pair_score")
    con.executemany(
        "INSERT OR REPLACE INTO pair_score VALUES (?,?,?)",
        [(pairs[i][0], pairs[i][1], float(est[i])) for i in np.flatnonzero(keep)],
    )
    con.commit()
    T.stop()
    print(f"  pairs above threshold {config.MERGE_THRESHOLD}: {int(keep.sum()):,}")

    T.start("7_identify")
    run_id = con.execute(
        "INSERT INTO run(started_at,notices,candidates,merges,note) VALUES (?,?,?,?,?)",
        (_dt.datetime.utcnow().isoformat(timespec="seconds"), len(df), len(pairs),
         int(keep.sum()), note),
    ).lastrowid
    merged = [(pairs[i][0], pairs[i][1]) for i in np.flatnonzero(keep)]
    groups = clustermod.cluster_pairs(ids, merged)
    report = clustermod.assign_opportunities(con, groups, run_id)
    total = time.perf_counter() - t0
    con.execute("UPDATE run SET finished_at=?, seconds=? WHERE run_id=?",
                (_dt.datetime.utcnow().isoformat(timespec="seconds"), total, run_id))
    con.execute("INSERT OR REPLACE INTO meta VALUES ('config',?)",
                (json.dumps({k: v for k, v in vars(config).items() if k.isupper()}),))
    con.commit()
    T.stop()

    report.update({"seconds_total": round(total, 1), "stages": {k: round(v, 1) for k, v in T.t.items()},
                   "candidate_pairs": len(pairs), "merged_pairs": int(keep.sum()),
                   "bucket_cap": cap, "suppressed_buckets": suppressed_buckets,
                   "run_id": run_id})
    print(json.dumps(report, indent=2))
    return con, report, {"sigs": sigs, "ids": ids, "shingles": shing,
                         "pairs": pairs, "est": est, "boiler": boiler}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--db", default=config.DB_PATH)
    ap.add_argument("--bucket-cap", type=int, default=None)
    ap.add_argument("--note", default="")
    args = ap.parse_args()
    con, rep, _ = build(args.db, args.fresh, args.bucket_cap, args.note)
    out = os.path.join(os.path.dirname(__file__), "..", "results", "pipeline_run.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as f:
        json.dump(rep, f, indent=2)
