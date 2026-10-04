-- Yelp Open Dataset, Philadelphia businesses only, plus links to `place` (decision 0019).
-- PRIVATE: this is Yelp Data and derived data (agreement section 5). Local database only; never export, never commit.
CREATE TABLE IF NOT EXISTS yelp_business (
    business_id  text PRIMARY KEY,
    name         text NOT NULL,
    address      text,
    city         text,
    state        text,
    postal_code  text,
    geom         geometry(Point, 4326) NOT NULL,
    stars        real,
    review_count int,
    is_open      boolean,              -- as of the dataset snapshot (January 2022), not today
    categories   text,
    is_food      boolean NOT NULL
);
CREATE INDEX IF NOT EXISTS yelp_business_geom_idx ON yelp_business USING gist (geom);

CREATE TABLE IF NOT EXISTS yelp_link (
    place_id    int PRIMARY KEY REFERENCES place (id) ON DELETE CASCADE,
    business_id text NOT NULL REFERENCES yelp_business (business_id) ON DELETE CASCADE,
    score       double precision NOT NULL,
    basis       text NOT NULL,
    name_sim    double precision NOT NULL,
    dist_m      double precision NOT NULL,
    confidence  text NOT NULL,         -- high | medium | low
    UNIQUE (business_id)
);

-- Yelp sometimes lists one business twice (same name, same address). The extra listings of a linked business, so a
-- place's reviews are not split between them.
CREATE TABLE IF NOT EXISTS yelp_alias (
    place_id    int  NOT NULL REFERENCES place (id) ON DELETE CASCADE,
    business_id text NOT NULL REFERENCES yelp_business (business_id) ON DELETE CASCADE,
    PRIMARY KEY (place_id, business_id),
    UNIQUE (business_id)
);

-- Downstream code (reviews, ratings, the chat) reads this view, never yelp_link: low-confidence links are mostly the
-- same storefront with a different business, and would attach the wrong reviews.
CREATE OR REPLACE VIEW yelp_link_usable AS SELECT * FROM yelp_link WHERE confidence IN ('high', 'medium');
