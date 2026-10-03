"""Run the rule baseline over every building's evidence.  Usage: python -m streetwalker.baseline_area"""

import psycopg

from streetwalker import db
from streetwalker.baseline_rules import RULESETS


def run(conn: psycopg.Connection) -> dict[str, int]:
    rows = conn.execute("SELECT building_id, payload FROM evidence WHERE tier = 0 ORDER BY building_id").fetchall()
    counts = {}
    for version, predict in RULESETS.items():
        out = []
        for bid, payload in rows:
            p = predict(payload)
            out.append((bid, version, p.d1, p.d2, p.d3_food, p.rule))
        conn.execute("DELETE FROM baseline_prediction WHERE baseline = %s", (version,))
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO baseline_prediction (building_id, baseline, d1_class, d2_type, d3_food, rule) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                out,
            )
        counts[version] = len(out)
    return counts


def main() -> None:
    with db.connect() as conn:
        db.migrate(conn)
        for version, n in run(conn).items():
            print(f"{version}: predictions stored for {n} buildings")
        conn.commit()


if __name__ == "__main__":
    main()
