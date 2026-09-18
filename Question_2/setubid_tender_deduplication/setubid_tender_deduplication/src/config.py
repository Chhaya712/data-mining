"""Frozen deployment configuration.

Every number in this file is derived in an experiment under experiments/ and
is defended in REPORT.md. Nothing here is a default, a round number or a
tutorial value; the derivation is named beside each.
"""

# --- A(a) representation  (exp_a_representation.py) ------------------------
SHINGLE_WIDTH = 5          # word 5-grams
BOILERPLATE_DF = 0.02      # a line in >=2% of notices is boilerplate
MASK_VOLATILE = True       # money / dates / refs / bare numbers -> sentinels

# --- A(b) reduced form  (exp_b_signature_size.py) --------------------------
# Required: 4 sigma of the estimator must fit inside the half-margin between
# the two adjudicated populations (half-margin = 0.0530 measured in exp_a),
# i.e. sigma <= 0.01325 at the worst case J=0.5  ->  K >= 1424.
# K must also factor as BANDS * ROWS_PER_BAND for A(c).
SIG_K = 1422               # = 237 bands x 6 rows
MINHASH_SEED = 20240917    # frozen; changing it invalidates stored signatures

# --- A(c) retrieval  (exp_c_scurve.py) -------------------------------------
ROWS_PER_BAND = 6
BANDS = 237
# Decision threshold on the estimated similarity. Derived from the cost
# asymmetry FALSE_MERGE_COST : FALSE_SPLIT_COST by minimising expected cost
# on labelled_pairs.csv.
FALSE_MERGE_COST = 200.0   # merging two different tenders (bidder sues)
FALSE_SPLIT_COST = 1.0     # showing a duplicate card (bidder grumbles)
MERGE_THRESHOLD = 0.735

# --- B(e) skew mitigation  (exp_e_skew.py) ---------------------------------
BUCKET_CAP = 60            # bands whose bucket exceeds this are not expanded

# --- paths -----------------------------------------------------------------
DB_PATH = "setubid.db"
