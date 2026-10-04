"""Classify licensed places by kind with Jev.   Usage: python -m streetwalker.census_kind

Validation: places that OSM also maps carry an OSM kind, a proxy label (fast food versus restaurant is genuinely fuzzy).
The same prompt then fills in the kind of licensed places that OSM does not map. Needs census_area to have run.
"""

from collections import Counter

from streetwalker import db
from streetwalker.jev_client import ask, make_client
from streetwalker.jev_questions import PLACE_KINDS, build_place_questions

SOFT = {"fast food": "restaurant"}  # strict and merged agreement are both reported


def state(name: str | None, address: str | None, licence_type: str | None) -> str:
    seats = "30 or more seats" if licence_type and "30+" in licence_type else "fewer than 30 seats"
    return f"Business name: {name or 'unknown'}.\nStreet address: {address or 'unknown'}.\nCity food licence: Food Preparing and Serving ({seats})."


def main() -> None:
    with db.connect() as conn:
        db.migrate(conn)
        rows = conn.execute(
            "SELECT id, licence_name, address, licence_type, kind, sources FROM place WHERE licence_id IS NOT NULL ORDER BY id"
        ).fetchall()
        client, questions = make_client(), build_place_questions()
        results = {}
        for pid, name, addr, ltype, _kind, _sources in rows:
            r = ask(client, state(name, addr, ltype), questions)
            if r.answers:
                a = r.answers[0]
                results[pid] = (a.answer, a.confidence, a.probs)
        for pid, (kind, conf, _p) in results.items():
            conn.execute("UPDATE place SET kind_jev = %s, kind_jev_conf = %s WHERE id = %s", (kind, conf, pid))
        # final kind: OSM's when the place is mapped, otherwise Jev's
        conn.execute("UPDATE place SET kind_source = CASE WHEN 'osm' = ANY(sources) THEN 'osm' ELSE 'jev' END WHERE licence_id IS NOT NULL OR osm_id IS NOT NULL")
        conn.execute("UPDATE place SET kind = kind_jev WHERE kind_source = 'jev' AND kind_jev IS NOT NULL")
        conn.commit()

        both = [(r, results[r[0]]) for r in rows if "osm" in r[5] and r[0] in results]
        strict = sum(res[0] == r[4] for r, res in both)
        soft = sum(SOFT.get(res[0], res[0]) == SOFT.get(r[4], r[4]) for r, res in both)
        print(f"{len(rows)} licensed places classified; {len(both)} also have an OSM kind")
        print(f"agreement with the OSM kind: strict {strict}/{len(both)} ({strict / len(both):.0%}), fast food merged into restaurant {soft}/{len(both)} ({soft / len(both):.0%})")
        cm = Counter((r[4], res[0]) for r, res in both)
        print("  OSM kind -> Jev kind:", ", ".join(f"{a}->{b} {n}" for (a, b), n in cm.most_common(14)))
        wrong = [(r[1], r[4], res[0], round(res[1], 2)) for r, res in both if SOFT.get(res[0], res[0]) != SOFT.get(r[4], r[4])]
        print("  disagreements (name, OSM, Jev, conf):", wrong[:8])
        only = Counter(results[r[0]][0] for r in rows if "osm" not in r[5] and r[0] in results)
        print("kinds of licence-only places by Jev:", dict(only.most_common()))
        conf = [res[1] for _, res in both]
        ok = [SOFT.get(res[0], res[0]) == SOFT.get(r[4], r[4]) for r, res in both]
        hi = [c >= 0.9 for c in conf]
        print(f"confidence >= 0.9 on {sum(hi)}/{len(hi)}; agreement among those {sum(o for o, h in zip(ok, hi, strict=True) if h) / max(sum(hi), 1):.0%}")
        _ = PLACE_KINDS


if __name__ == "__main__":
    main()
