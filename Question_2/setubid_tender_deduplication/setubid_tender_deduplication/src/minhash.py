"""
Section A(b) -- the reduced form.

We keep, per notice, a fixed-width vector of K min-hashes instead of its
shingle set. Pr[min h_i(A) == min h_i(B)] = J(A,B), so the fraction of
agreeing coordinates is an unbiased estimator of Jaccard with variance
J(1-J)/K -- a Binomial(K, J)/K.

K is NOT chosen here. It is derived in experiments/exp_b_signature_size.py
from a stated accuracy requirement and then frozen in src/config.py.

Hash family: multiply-shift, h_i(x) = ((a_i*x + b_i) mod 2^64) >> 32 with a_i
odd. It is 2-universal, which is what the MinHash argument needs, and it is
one 64-bit multiply per coordinate -- no modulus by a prime, which matters
because we evaluate K * |shingles| of them per notice.
"""
from __future__ import annotations

import hashlib

import numpy as np

MASK64 = np.uint64(0xFFFFFFFFFFFFFFFF)
SHIFT = np.uint64(32)


def shingle_hashes(shingle_set) -> np.ndarray:
    """Stable 64-bit hash of each shingle string. blake2b (not Python's
    randomised hash) so that a signature computed tonight is bit-identical to
    one computed next month -- the bookmark-stability requirement starts here."""
    if not shingle_set:
        return np.zeros(1, dtype=np.uint64)
    out = np.empty(len(shingle_set), dtype=np.uint64)
    for i, s in enumerate(sorted(shingle_set)):
        out[i] = int.from_bytes(hashlib.blake2b(s.encode("utf-8"), digest_size=8).digest(), "big")
    return out


def make_params(k: int, seed: int = 20240917):
    """Frozen permutation parameters. The seed is part of the deployed
    configuration: changing it invalidates every stored signature."""
    rng = np.random.default_rng(seed)
    a = rng.integers(1, 2**63, size=k, dtype=np.uint64) | np.uint64(1)  # odd
    b = rng.integers(0, 2**63, size=k, dtype=np.uint64)
    return a, b


def signature(shingle_hash: np.ndarray, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """K-vector of 32-bit min-hashes for one notice."""
    # (K,1) * (1,m) -> (K,m); uint64 arithmetic wraps mod 2^64 by construction
    h = (a[:, None] * shingle_hash[None, :] + b[:, None]) >> SHIFT
    return h.min(axis=1).astype(np.uint32)


def signatures(list_of_shingle_hashes, a, b, progress=None) -> np.ndarray:
    k = len(a)
    out = np.empty((len(list_of_shingle_hashes), k), dtype=np.uint32)
    for i, sh in enumerate(list_of_shingle_hashes):
        out[i] = signature(sh, a, b)
        if progress and i % progress == 0:
            print(f"  signed {i}", flush=True)
    return out


def estimate(sig_a: np.ndarray, sig_b: np.ndarray) -> float:
    return float((sig_a == sig_b).mean())


def estimate_many(sig_matrix: np.ndarray, left: np.ndarray, right: np.ndarray) -> np.ndarray:
    """Vectorised estimate for many pairs given index arrays."""
    return (sig_matrix[left] == sig_matrix[right]).mean(axis=1)
