"""Load Yelp Open Dataset businesses in Philadelphia into Postgres (decision 0019).

Reads data/yelp/yelp_academic_dataset_business.json, which is extracted by hand from the dataset the owner downloaded
(data/ is gitignored; the dataset and anything derived from it stay on this machine). Only businesses inside the
Philadelphia box are kept. Usage: .venv/bin/python -m streetwalker.ingest.yelp
"""

import json

import psycopg

from streetwalker import db

PATH = db.ROOT / "data" / "yelp" / "yelp_academic_dataset_business.json"
BOX = (-75.29, 39.86, -74.95, 40.14)  # lng_min, lat_min, lng_max, lat_max: all of Philadelphia

FOOD_WORDS = {
    "Restaurants", "Food", "Bars", "Nightlife", "Cafes", "Coffee & Tea", "Bakeries", "Pubs", "Breweries", "Pizza", "Delis",
    "Sandwiches", "Ice Cream & Frozen Yogurt", "Desserts", "Caterers", "Beer Bar", "Wine Bars", "Cocktail Bars", "Sports Bars",
    "Lounges", "Fast Food", "Diners", "Breakfast & Brunch", "Juice Bars & Smoothies", "Bubble Tea", "Food Trucks", "Gastropubs",
}


def is_food(categories: str | None) -> bool:
    return bool(categories) and any(c.strip() in FOOD_WORDS for c in categories.split(","))


def in_box(lng: float, lat: float) -> bool:
    return BOX[0] <= lng <= BOX[2] and BOX[1] <= lat <= BOX[3]


def ingest_yelp(conn: psycopg.Connection) -> int:
    if not PATH.exists():
        raise SystemExit(f"{PATH} not found: extract the business file from the Yelp dataset first (see decision 0019)")
    conn.execute("DELETE FROM yelp_business")  # cascades to yelp_link
    n = 0
    with PATH.open() as f:
        for line in f:
            b = json.loads(line)
            if b["state"] != "PA" or b["latitude"] is None or b["longitude"] is None or not in_box(b["longitude"], b["latitude"]):
                continue
            conn.execute(
                "INSERT INTO yelp_business (business_id, name, address, city, state, postal_code, geom, stars, review_count, is_open, categories, is_food) "
                "VALUES (%s, %s, %s, %s, %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326), %s, %s, %s, %s, %s)",
                (b["business_id"], b["name"], b["address"], b["city"], b["state"], b["postal_code"], b["longitude"], b["latitude"],
                 b["stars"], b["review_count"], bool(b["is_open"]), b["categories"], is_food(b["categories"])),
            )
            n += 1
    return n


def main() -> None:
    with db.connect() as conn:
        db.migrate(conn)
        n = ingest_yelp(conn)
        conn.commit()
        row = conn.execute("SELECT count(*), count(*) FILTER (WHERE is_food), count(*) FILTER (WHERE is_food AND is_open) FROM yelp_business").fetchone()
        print(f"loaded {n} Philadelphia businesses ({row[1]} food or drink, {row[2]} of those open at the snapshot)")


if __name__ == "__main__":
    main()
