"""Eval: how accurate is frontage assignment when a building has no address?

Takes buildings whose street was resolved from their address, hides the address, re-runs the
assignment, and checks whether the same street comes back. The address-resolved street is treated as
the label, which is a good-but-imperfect proxy: wrong or stale addresses count against the rules.
Compares plain nearest-segment with the shipped fallback (nearest, preferring non-service roads).
Run: .venv/bin/python scripts/eval_frontage_fallback.py
"""

from dataclasses import replace

from streetwalker import db
from streetwalker.frontage import assign_all
from streetwalker.frontage_area import load_inputs


def main() -> None:
    print(f"{'area':14s} {'n':>5s} {'plain nearest':>14s} {'shipped fallback':>17s}  (same street as the address says)")
    with db.connect() as conn:
        for area_id, slug in conn.execute("SELECT id, slug FROM area ORDER BY id").fetchall():
            _, edges, _, buildings = load_inputs(conn, area_id)
            with_addr = assign_all(buildings, edges)
            labelled = [i for i, f in enumerate(with_addr) if f.method == "address"]
            hidden = assign_all([replace(buildings[i], addr_street=None) for i in labelled], edges)
            plain = fallback = 0
            for i, h in zip(labelled, hidden, strict=True):
                truth = with_addr[i]
                plain += truth.nearest_same
                same = h.edge_idx == truth.edge_idx or bool(edges[h.edge_idx].keys & edges[truth.edge_idx].keys)
                fallback += same
            n = len(labelled)
            print(f"{slug:14s} {n:5d} {100 * plain / n:13.1f}% {100 * fallback / n:16.1f}%")


if __name__ == "__main__":
    main()
