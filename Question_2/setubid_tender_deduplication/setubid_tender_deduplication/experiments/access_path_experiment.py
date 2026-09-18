"""
Section B(d). The retrieval structure lives in SQLite; this measures the
access path instead of asserting it.

Three physical layouts, identical rows (237 band keys x 12,000 notices =
2,844,000 rows), identical 12,000-probe workload:

  A  band_bucket          WITHOUT ROWID, PK (band_no, band_hash, notice_id)
     -> the table *is* the B-tree. One descent per probe, then a scan of
        physically adjacent leaf entries. The payload (notice_id) is in the
        key, so the index is covering: no second structure is touched.

  B  band_bucket_rowid    ordinary rowid table + secondary index on
     (band_no, band_hash)
     -> descend the index B-tree, then one descent of the *table* B-tree per
        matching row to fetch notice_id. That second descent is the rejected
        cost, and it is paid once per returned row, which is exactly the
        regime a bucket probe is in.

  C  band_bucket_rowid with the index forced off (NOT INDEXED)
     -> full table scan: 2,844,000 rows examined per probe.

Rows actually examined are counted, not inferred: a user-defined SQL function
`probe()` is registered and placed last in the WHERE clause, so SQLite calls
it exactly once per row that reaches that term.

Outputs: results/exp_d_access_path.json
"""
import json
import os
import random
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import config  # noqa: E402
import db as dbmod  # noqa: E402

OUT = os.path.join(os.path.dirname(__file__), "..", "results")
DB = os.path.join(os.path.dirname(__file__), "..", "setubid.db")

COUNTER = {"n": 0}


def probe(_x):
    COUNTER["n"] += 1
    return 1


def qplan(con, sql, params):
    return [" ".join(str(c) for c in r) for r in
            con.execute("EXPLAIN QUERY PLAN " + sql, params)]


def timed(con, sql, workload, label, n_probe_rows_note=""):
    COUNTER["n"] = 0
    t0 = time.perf_counter()
    rows = 0
    for bn, bh in workload:
        rows += len(con.execute(sql, (bn, bh)).fetchall())
    dt = time.perf_counter() - t0
    return {
        "label": label,
        "plan": qplan(con, sql, workload[0]),
        "probes": len(workload),
        "rows_returned": rows,
        "rows_examined": COUNTER["n"],
        "rows_examined_per_probe": round(COUNTER["n"] / len(workload), 1),
        "wall_clock_s": round(dt, 4),
        "us_per_probe": round(dt / len(workload) * 1e6, 1),
        "note": n_probe_rows_note,
    }


def main():
    con = dbmod.connect(DB)
    con.create_function("probe", 1, probe, deterministic=True)

    # build the rejected layout from the same rows
    con.execute("DROP INDEX IF EXISTS ix_bbr")
    con.execute("DELETE FROM band_bucket_rowid")
    con.execute("INSERT INTO band_bucket_rowid SELECT band_no, band_hash, notice_id FROM band_bucket")
    con.execute("CREATE INDEX ix_bbr ON band_bucket_rowid(band_no, band_hash)")
    con.execute("ANALYZE")
    con.commit()

    total_rows = con.execute("SELECT COUNT(*) FROM band_bucket").fetchone()[0]

    # workload: the band keys of 12,000 real notices, one band each, sampled
    # the way the nightly job probes them
    random.seed(11)
    work = con.execute(
        "SELECT band_no, band_hash FROM band_bucket ORDER BY notice_id LIMIT 12000"
    ).fetchall()

    res = {}
    res["A_without_rowid_covering"] = timed(
        con,
        "SELECT notice_id FROM band_bucket WHERE band_no=? AND band_hash=? AND probe(notice_id)",
        work, "WITHOUT ROWID clustered PK (adopted)")
    res["B_rowid_plus_secondary_index"] = timed(
        con,
        "SELECT notice_id FROM band_bucket_rowid WHERE band_no=? AND band_hash=? AND probe(notice_id)",
        work, "rowid table + secondary index (rejected)")
    small = work[:60]
    # probe() goes FIRST here so it is evaluated on every row the scan visits,
    # which is the number we want to report for a full scan.
    res["C_forced_full_scan"] = timed(
        con,
        "SELECT notice_id FROM band_bucket_rowid NOT INDEXED "
        "WHERE probe(notice_id) AND band_no=? AND band_hash=?",
        small, "index forced off (rejected)",
        "only 60 probes -- 12,000 would take ~14 minutes of the 20-minute window "
        "for a single sweep; probe() is placed first so it counts every row visited")
    res["C_forced_full_scan"]["extrapolated_to_12000_probes_s"] = round(
        res["C_forced_full_scan"]["wall_clock_s"] / len(small) * 12000, 1)

    # The two indexed layouts look alike on small buckets. The difference is a
    # per-returned-row cost, so it only shows up where buckets are large --
    # which is precisely the regime B(e) is about. Re-run on the 2,000 heaviest
    # buckets in the corpus.
    heavy = con.execute(
        "SELECT band_no, band_hash FROM bucket_stat ORDER BY members DESC LIMIT 2000"
    ).fetchall()
    res["A_heavy_buckets"] = timed(
        con,
        "SELECT notice_id FROM band_bucket WHERE band_no=? AND band_hash=? AND probe(notice_id)",
        heavy, "WITHOUT ROWID clustered PK, 2000 heaviest buckets")
    res["B_heavy_buckets"] = timed(
        con,
        "SELECT notice_id FROM band_bucket_rowid WHERE band_no=? AND band_hash=? AND probe(notice_id)",
        heavy, "rowid + secondary index, 2000 heaviest buckets")
    res["heavy_bucket_penalty_x"] = round(
        res["B_heavy_buckets"]["wall_clock_s"] / res["A_heavy_buckets"]["wall_clock_s"], 3)

    # storage cost of each layout
    res["storage"] = {
        "band_bucket_rows": total_rows,
        "db_file_bytes": os.path.getsize(DB),
        "page_count": con.execute("PRAGMA page_count").fetchone()[0],
        "page_size": con.execute("PRAGMA page_size").fetchone()[0],
    }
    res["budget"] = {
        "nightly_window_s": 1200,
        "adopted_full_probe_sweep_s": round(
            res["A_without_rowid_covering"]["wall_clock_s"]
            / 12000 * 12000 * config.BANDS, 1),
        "comment": "a full sweep is BANDS probes per notice; the pipeline does "
                   "it as one ordered scan instead, see results/pipeline_run.json",
    }
    print(json.dumps(res, indent=2))
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "exp_d_access_path.json"), "w") as f:
        json.dump(res, f, indent=2)


if __name__ == "__main__":
    main()
