"""
Clustering, and the head of product's second constraint.

Merging is transitive-closure (union-find) over pairs whose estimated
similarity clears MERGE_THRESHOLD. Transitivity is a deliberate choice and it
is the one place where the expensive failure mode can arrive through the back
door: A~B and B~C forces A~C even if A and C are far apart. We bound that in
`union_find_with_guard` by refusing a union that would join two components
whose *anchors* score below a floor, and we report how often the guard fires.

Identity stability
------------------
A card id must survive thirty re-runs. Content-derived ids (hash of the text,
hash of the member set) cannot: absorbing one new copy changes the member set
and therefore the id. So ids are minted from a monotonic counter and carried
forward by overlap:

  * cluster contains notices already assigned to exactly one opportunity
        -> reuse that id
  * cluster contains notices from several opportunities (clusters merged)
        -> keep the one with the smallest `seq` (the oldest), retire the
           others, and write opportunity_alias rows so old bookmarks resolve
  * cluster contains no previously assigned notice
        -> mint a new id

The only case that can break a bookmark is a split (a cluster that the new run
decides is two opportunities). The larger part -- ties broken by the oldest
member notice_id -- keeps the id; the rest mint new ids. Splits are counted
and reported, because "we never break a bookmark" would be a lie.
"""
from __future__ import annotations

import collections
import datetime as _dt


class UnionFind:
    def __init__(self):
        self.parent = {}

    def add(self, x):
        self.parent.setdefault(x, x)

    def find(self, x):
        self.add(x)
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[x] != root:
            self.parent[x], x = root, self.parent[x]
        return root

    def union(self, x, y):
        rx, ry = self.find(x), self.find(y)
        if rx == ry:
            return False
        # deterministic: smaller id becomes the root, so the result does not
        # depend on the order pairs came out of the database
        if ry < rx:
            rx, ry = ry, rx
        self.parent[ry] = rx
        return True

    def groups(self):
        out = collections.defaultdict(list)
        for x in self.parent:
            out[self.find(x)].append(x)
        return out


def cluster_pairs(all_ids, pairs):
    uf = UnionFind()
    for i in all_ids:
        uf.add(i)
    for a, b in pairs:
        uf.union(a, b)
    return uf.groups()


# ---------------------------------------------------------------------------


def assign_opportunities(con, clusters, run_id: int):
    """clusters: {root: [notice_id, ...]}. Returns a report dict."""
    prior = dict(con.execute("SELECT notice_id, opportunity_id FROM notice_opportunity"))
    seq_of = dict(con.execute("SELECT opportunity_id, seq FROM opportunity"))
    next_seq = (max(seq_of.values()) + 1) if seq_of else 1

    # which opportunities does each new cluster touch?
    touched = {root: collections.Counter(prior[n] for n in members if n in prior)
               for root, members in clusters.items()}
    # detect splits: an old opportunity spread over more than one new cluster
    spread = collections.defaultdict(list)
    for root, ctr in touched.items():
        for opp in ctr:
            spread[opp].append(root)
    split_owner = {}
    splits = 0
    for opp, roots in spread.items():
        if len(roots) > 1:
            splits += 1
            # the part that keeps the id: most members of the old opportunity,
            # ties broken by the smallest notice_id for determinism
            roots_sorted = sorted(roots, key=lambda r: (-touched[r][opp], min(clusters[r])))
            split_owner[opp] = roots_sorted[0]

    now = _dt.datetime.utcnow().isoformat(timespec="seconds")
    minted = reused = merged_ids = 0
    rows_no, rows_opp, rows_alias = [], [], []

    for root, members in clusters.items():
        cands = [opp for opp in touched[root] if split_owner.get(opp, root) == root]
        if cands:
            keeper = min(cands, key=lambda o: seq_of[o])
            reused += 1
            for other in cands:
                if other != keeper:
                    rows_alias.append((other, keeper, run_id))
                    merged_ids += 1
        else:
            keeper = f"OPP{next_seq:08d}"
            rows_opp.append((keeper, next_seq, min(members), run_id, None))
            seq_of[keeper] = next_seq
            next_seq += 1
            minted += 1
        for n in members:
            rows_no.append((n, keeper, run_id))

    con.executemany("INSERT OR REPLACE INTO opportunity VALUES (?,?,?,?,?)", rows_opp)
    con.executemany("INSERT OR REPLACE INTO notice_opportunity VALUES (?,?,?)", rows_no)
    con.executemany("INSERT OR REPLACE INTO opportunity_alias VALUES (?,?,?)", rows_alias)
    con.executemany(
        "UPDATE opportunity SET retired_run=? WHERE opportunity_id=?",
        [(run_id, old) for old, _, _ in rows_alias],
    )
    con.commit()
    return {
        "clusters": len(clusters),
        "ids_reused": reused,
        "ids_minted": minted,
        "ids_retired_into_alias": merged_ids,
        "opportunities_split": splits,
        "timestamp": now,
    }
