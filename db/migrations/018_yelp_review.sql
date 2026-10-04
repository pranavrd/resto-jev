-- Yelp reviews for the businesses linked to census places (decision 0020). PRIVATE: Yelp Data (agreement 4A, 4E, 5).
-- user_id is deliberately not stored: nothing here needs to identify a reviewer.
CREATE TABLE IF NOT EXISTS yelp_review (
    review_id   text PRIMARY KEY,
    business_id text NOT NULL REFERENCES yelp_business (business_id) ON DELETE CASCADE,
    stars       smallint NOT NULL,
    date        date NOT NULL,
    text        text NOT NULL,
    useful      int NOT NULL DEFAULT 0,
    funny       int NOT NULL DEFAULT 0,
    cool        int NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS yelp_review_business_idx ON yelp_review (business_id);

-- Reviews per place: through the usable link and any duplicate listing of the same business.
CREATE OR REPLACE VIEW place_review AS
SELECT l.place_id, r.*
FROM yelp_review r
JOIN (SELECT place_id, business_id FROM yelp_link_usable UNION ALL SELECT place_id, business_id FROM yelp_alias) l USING (business_id);
