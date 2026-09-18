"""Shared corpus loader. Reads whatever the faculty folder actually contains:
Parquet part files if pyarrow is available, CSV part files otherwise."""
import functools
import glob
import os

import pandas as pd

DATA = os.environ.get(
    "SETUBID_DATA", os.path.join(os.path.dirname(__file__), "..", "data")
)


def _parts():
    pats = [
        os.path.join(DATA, "notices", "*.parquet"),
        os.path.join(DATA, "notices", "*.csv"),
        os.path.join(DATA, "*.parquet"),
        os.path.join(DATA, "part-*.csv"),
    ]
    for p in pats:
        hits = sorted(glob.glob(p))
        if hits:
            return hits
    raise FileNotFoundError(f"no notice files under {DATA}")


@functools.lru_cache(maxsize=1)
def load_corpus() -> pd.DataFrame:
    files = _parts()
    if files[0].endswith(".parquet"):
        df = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    else:
        df = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    return df


@functools.lru_cache(maxsize=1)
def load_labels() -> pd.DataFrame:
    for cand in ("labelled_pairs.csv", "labelled_paies.csv"):
        p = os.path.join(DATA, cand)
        if os.path.exists(p):
            return pd.read_csv(p)
    raise FileNotFoundError("labelled_pairs.csv not found")


@functools.lru_cache(maxsize=1)
def load_truth_clusters():
    """Diagnostic only -- NEVER used to fit a threshold. Used in exp_e to
    describe the corpus-wide candidate distribution, which cannot be described
    from 900 labelled pairs alone. Returns None if the folder is absent."""
    for p in (os.path.join(DATA, "_truth", "clusters.csv"),
              os.path.join(DATA, "clusters.csv")):
        if os.path.exists(p):
            return pd.read_csv(p)
    return None
