"""
Section A(c) -- sublinear retrieval by banding.

The K-coordinate signature is cut into `bands` consecutive blocks of
`rows_per_band` coordinates. Two notices are candidates if any one block is
identical. Because each coordinate agrees with probability s (the true
Jaccard), a block agrees with probability s^r and

    P(candidate | s) = 1 - (1 - s^r)^b

which is the S-curve plotted in exp_c. Nothing else in the retrieval path
looks at the text, so this function *is* the recall ceiling of the whole
system: a pair that never becomes a candidate can never be merged.
"""
from __future__ import annotations

import hashlib

import numpy as np


def band_hashes(sig: np.ndarray, bands: int, rows: int) -> list[int]:
    """One 63-bit key per band. blake2b over the raw bytes of the block, so
    the key is stable across processes, machines and Python versions."""
    assert sig.shape[0] == bands * rows
    out = []
    blocks = sig.reshape(bands, rows)
    for i in range(bands):
        digest = hashlib.blake2b(blocks[i].tobytes(), digest_size=8).digest()
        out.append(int.from_bytes(digest, "big") >> 1)  # >>1 keeps it in SQLite INTEGER
    return out


def band_hashes_matrix(sigs: np.ndarray, bands: int, rows: int) -> np.ndarray:
    """(n, bands) int64 matrix of band keys for a whole signature matrix."""
    n = sigs.shape[0]
    out = np.empty((n, bands), dtype=np.int64)
    for i in range(n):
        out[i] = band_hashes(sigs[i], bands, rows)
    return out


def p_candidate(s, bands: int, rows: int):
    s = np.asarray(s, dtype=float)
    return 1.0 - (1.0 - s ** rows) ** bands


def lsh_threshold(bands: int, rows: int) -> float:
    """The inflection ('knee') of the S-curve, where P is about 1/2."""
    return (1.0 / bands) ** (1.0 / rows)
