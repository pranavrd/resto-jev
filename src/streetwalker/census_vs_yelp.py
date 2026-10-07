"""The restaurant census against Yelp (decision 0033).   Usage: .venv/bin/python -m streetwalker.census_vs_yelp [--write]

PRIVATE: reads Yelp Data (yelp_business, yelp_link) and writes only to docs/private/census-vs-yelp.md (gitignored). No number or example
derived from Yelp goes anywhere else; the tests use invented businesses.

Decision 0019 linked census places to Yelp businesses and said it did not measure completeness. This asks the other direction: of the
Yelp food and drink businesses that were open inside the three areas at the snapshot (January 2022), how many does the census hold, and
what explains the rest? The evidence needs no human labels and no web lookups: the City's licence table keeps closed and inactive
licences with their dates, so a business that Yelp had open in 2022 and the census does not hold can be checked against it.

For every open Yelp dining business with no link to a place (a "gap"), the first explanation that holds, in this order:

  not dining      its categories say it is a grocery, a hotel or similar (decision 0020 excludes those)
  census miss     a "Food Preparing" licence, the type the census is built from, is active today and carries its name within 60 m, but no place holds that licence: a hole in the census
  other licence   an active food licence of a type the census does not use (retail food: delis, bakeries, markets) carries its name: a gap in the census's scope
  licence ended   a food licence with its name within 60 m has ended (closed, inactive, expired, revoked, or an inactive date)
  link missed     the census has the place (a place holds the licence that carries the Yelp name, or a place within 60 m has a similar name) but the matcher did not link it
  turnover        a place within 25 m, first licensed after the snapshot, has a different name: another business has taken the spot
  unexplained     none of the above: closed without a licence record, never licensed as food, a neighbour only, or a hole in both lists

"Census miss" and "unexplained" are the ones to read by hand. The estimates are bounds, not measurements: Yelp is a 2022 list and the census a 2026 one.
"""

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from psycopg.rows import dict_row

from streetwalker import db
from streetwalker.census import chapman
from streetwalker.yelp_match import is_dining, name_sim

SNAPSHOT = date(2022, 1, 31)  # the Yelp business file's date: a place first licensed later cannot be in it
NEAR_M = 60.0  # the matcher's own limit for a Yelp point to belong to a place
FAR_M = 250.0  # a Yelp point can sit this far from its place when the name is the same (the matcher links up to 200 m on name and address)
TURNOVER_M = 25.0
SAME_NAME = 0.7  # the similarity at which the matcher already treats two names as the same business
SIMILAR_NAME = 0.5
ENDED = {"Closed", "Inactive", "Expired", "Revoked"}
CLASSES = ("not dining", "census miss", "other licence", "licence ended", "link missed", "turnover", "unexplained")
REPORT = Path(__file__).resolve().parents[2] / "docs" / "private" / "census-vs-yelp.md"


@dataclass(frozen=True)
class Gap:
    """A Yelp business open at the snapshot, inside an area, that no place is linked to, with what lies within 60 m of it."""

    id: str
    name: str
    area: str
    review_count: int
    categories: str | None
    places: list[tuple[str, float, bool]] = field(default_factory=list)  # (name the place goes by, metres, first licensed after the snapshot)
    licences: list[tuple[list[str], str | None, bool, bool, bool]] = field(default_factory=list)  # (names, status, has an inactive date, a type the census uses, a place holds it)


def explain(g: Gap) -> str:
    """The first explanation that holds for a gap (see the module docstring)."""
    if not is_dining(g.categories):
        return "not dining"
    matching = [(status, inactive, in_census, held) for names, status, inactive, in_census, held in g.licences if name_sim(g.name, names) >= SAME_NAME]
    active = [(in_census, held) for status, inactive, in_census, held in matching if status == "Active" and not inactive]
    if any(held for _, held in active):
        return "link missed"
    if any(in_census for in_census, _ in active):
        return "census miss"
    if active:
        return "other licence"
    if any(status in ENDED or inactive for status, inactive, _, _ in matching):
        return "licence ended"
    if any(name_sim(g.name, [n]) >= (SIMILAR_NAME if d <= NEAR_M else SAME_NAME) for n, d, _ in g.places):
        return "link missed"
    if any(d <= TURNOVER_M and new for _, d, new in g.places):
        return "turnover"
    return "unexplained"


def bounds(linked: int, gaps: Counter) -> dict:
    """Recall of the census against Yelp's open dining list, from the most pessimistic to the most generous reading.

    low   linked / all: every gap counts against the census, including those where the census has the place and only the link is missing
    mid   the places the census holds (linked, or present and not linked) over the businesses that can still be there: the gaps that a licence record
          or a new business at the spot explains (closed since, or turnover) are taken out of the denominator
    high  as mid, and "unexplained" is also taken as closed; what stays against the census is "other licence" (retail food, outside its scope) only
    """
    total = linked + sum(gaps.values())
    held = linked + gaps["link missed"]  # the census holds these; the matcher only failed to link them
    explained = gaps["licence ended"] + gaps["turnover"]

    def recall(excluded: int) -> float:
        return held / max(total - excluded, 1)

    return {
        "yelp_open_dining": total, "linked": linked, "held": held,
        "low": linked / total if total else 0.0,
        "mid": recall(explained),
        "high": recall(explained + gaps["unexplained"]),
    }


def two_source_estimate(census_at_snapshot: int, yelp_open_dining: int, both: int) -> tuple[float, float, float]:
    """Chapman's capture-recapture estimate of the businesses that were open in the areas at the snapshot, from the census and Yelp. Both lists
    miss the same kinds of business (the small and the new), so the true number is probably higher than this, and it is not a measurement."""
    return chapman(census_at_snapshot, yelp_open_dining, both)


# ---- reading the database -------------------------------------------------------------------------------------------------------------

def gaps_from_db(conn) -> tuple[list[Gap], int, dict]:
    """(the gaps, the number of open dining Yelp businesses in the areas that are linked usably, counts of the census side)."""
    conn.row_factory = dict_row
    rows = conn.execute(
        """
        SELECT b.business_id, b.name, b.categories, b.review_count, a.slug AS area, b.geom, (u.place_id IS NOT NULL) AS linked
        FROM yelp_business b JOIN area a ON ST_Within(b.geom, a.geom)
        LEFT JOIN yelp_link_usable u ON u.business_id = b.business_id
        LEFT JOIN yelp_alias al ON al.business_id = b.business_id
        WHERE b.is_food AND b.is_open AND al.business_id IS NULL
        """
    ).fetchall()
    gaps, linked = [], 0
    for r in rows:
        if r["linked"] and is_dining(r["categories"]):
            linked += 1
            continue
        if r["linked"]:
            continue
        places = conn.execute(
            """
            SELECT p.name, p.licence_name, ST_Distance(p.geom::geography, %(g)s::geography) AS d, (l.initialissuedate > %(snap)s) AS new
            FROM place p LEFT JOIN business_license l ON l.cartodb_id = p.licence_id
            WHERE ST_DWithin(p.geom::geography, %(g)s::geography, %(m)s) ORDER BY d
            """, {"g": r["geom"], "m": FAR_M, "snap": SNAPSHOT}).fetchall()
        lics = conn.execute(
            """
            SELECT business_name, legalname, licensestatus, inactivedate, (licensetype LIKE 'Food Preparing%%') AS in_census,
                   EXISTS (SELECT 1 FROM place p WHERE p.licence_id = cartodb_id) AS held
            FROM business_license WHERE licensetype ILIKE 'Food%%' AND geom IS NOT NULL
              AND ST_DWithin(geom::geography, %(g)s::geography, %(m)s)
            """, {"g": r["geom"], "m": NEAR_M}).fetchall()
        gaps.append(Gap(
            r["business_id"], r["name"], r["area"], r["review_count"] or 0, r["categories"],
            [(n, p["d"], bool(p["new"])) for p in places for n in (p["name"], p["licence_name"]) if n],
            [([n for n in (c["business_name"], c["legalname"]) if n], c["licensestatus"], c["inactivedate"] is not None, c["in_census"], c["held"]) for c in lics],
        ))
    return gaps, linked, {}


def census_side(conn) -> dict:
    """Places by whether they could be on Yelp's snapshot: first licensed before it, first licensed after it, or no licence (OSM only)."""
    conn.row_factory = dict_row
    rows = conn.execute(
        """
        SELECT p.id, p.kind, a.slug AS area, l.initialissuedate AS first, (u.place_id IS NOT NULL) AS on_yelp
        FROM place p JOIN area a ON a.id = p.area_id
        LEFT JOIN business_license l ON l.cartodb_id = p.licence_id
        LEFT JOIN yelp_link_usable u ON u.place_id = p.id
        """
    ).fetchall()
    out = {"before": [0, 0], "after": [0, 0], "unknown": [0, 0]}  # [places, on Yelp]
    for r in rows:
        k = "unknown" if r["first"] is None else "before" if r["first"].date() <= SNAPSHOT else "after"
        out[k][0] += 1
        out[k][1] += r["on_yelp"]
    return out


def render(gaps: list[Gap], linked: int, side: dict) -> str:
    """The private report as markdown."""
    why = Counter(explain(g) for g in gaps)
    by_area: dict[str, Counter] = defaultdict(Counter)
    for g in gaps:
        by_area[g.area][explain(g)] += 1
    areas = sorted(by_area)
    b = bounds(linked, Counter({k: v for k, v in why.items() if k != "not dining"}))
    census_snap = side["before"][0] + side["unknown"][0]
    est = two_source_estimate(census_snap, b["yelp_open_dining"], b["held"])
    out = ["# The census against Yelp (PRIVATE: numbers and examples derived from the Yelp Data)", ""]
    out.append("Gitignored on purpose (`docs/private/`; agreement sections 4E and 5, decision 0001). The method is in `docs/decisions/0033-census-vs-yelp.md`. "
               "Reproduce: `.venv/bin/python -m streetwalker.census_vs_yelp --write`.")
    out.append("")
    out.append(f"Yelp businesses open at the snapshot, inside the areas, dining: **{b['yelp_open_dining']}**. Linked usably to a census place: **{linked}**. "
               f"Gaps: {sum(v for k, v in why.items() if k != 'not dining')} dining, {why['not dining']} not dining.")
    out.append("")
    out.append("| Why a Yelp business has no place | All | " + " | ".join(areas) + " |")
    out.append("|---|---|" + "---|" * len(areas))
    out += [f"| {c} | {why[c]} | " + " | ".join(str(by_area[a][c]) for a in areas) + " |" for c in CLASSES]
    out.append("")
    out.append(f"Recall of the census against Yelp's open dining list: **{b['low']:.0%}** if every gap counts against it, **{b['mid']:.0%}** once the gaps a "
               f"licence record or another business at the spot explains are taken out, **{b['high']:.0%}** if \"unexplained\" is also taken as closed.")
    out.append("")
    out.append(f"Census places by whether they could be on the snapshot (places, on Yelp): first licensed before it {tuple(side['before'])}, after it "
               f"{tuple(side['after'])}, no licence {tuple(side['unknown'])}.")
    out.append(f"Capture-recapture over the {census_snap} places that could be on the snapshot, the {b['yelp_open_dining']} Yelp businesses and the {b['held']} in both: "
               f"about {est[0]:.0f} (95% {est[1]:.0f} to {est[2]:.0f}). Both lists miss the same small and new businesses, so this is not a measurement.")
    out.append("")
    out.append("## Gaps to read by hand (census miss, other licence, link missed and unexplained, most reviewed first)")
    out.append("")
    read = ("census miss", "other licence", "link missed", "unexplained")
    out += [f"- {g.name} ({g.area}, {g.review_count} reviews): {explain(g)}" for g in sorted(gaps, key=lambda g: -g.review_count) if explain(g) in read][:60]
    return "\n".join(out) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help=f"write the private report to {REPORT}")
    args = ap.parse_args()
    with db.connect() as conn:
        gaps, linked, _ = gaps_from_db(conn)
        side = census_side(conn)
    text = render(gaps, linked, side)
    print(text)
    if args.write:
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(text)
        print(f"written to {REPORT}")


if __name__ == "__main__":
    main()
