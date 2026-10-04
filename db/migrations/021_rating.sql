-- Provisional restaurant ratings from aspect scores (decision 0021). PRIVATE: derived from Yelp Data.
-- Every row is `provisional` until the aspect scores have been checked against human labels. The CHECK is deliberate: lifting
-- it takes a migration that says why, not a quiet UPDATE.
CREATE TABLE IF NOT EXISTS rating_run (
    id             serial PRIMARY KEY,
    aspect_run_id  int  NOT NULL REFERENCES aspect_run (id),
    weights_version text NOT NULL,
    params         jsonb NOT NULL,
    status         text NOT NULL DEFAULT 'provisional' CHECK (status = 'provisional'),
    created_at     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS restaurant_aspect (
    run_id      int  NOT NULL REFERENCES rating_run (id) ON DELETE CASCADE,
    place_id    int  NOT NULL REFERENCES place (id) ON DELETE CASCADE,
    aspect      text NOT NULL,
    mean        double precision NOT NULL,   -- posterior mean on 0 (clearly negative) to 1 (clearly positive)
    ci_low      double precision NOT NULL,
    ci_high     double precision NOT NULL,
    n_mentions  double precision NOT NULL,   -- sum of mention probabilities, not recency weighted
    n_eff       double precision NOT NULL,   -- effective sample size after mention and recency weights
    status      text NOT NULL DEFAULT 'provisional' CHECK (status = 'provisional'),
    PRIMARY KEY (run_id, place_id, aspect)
);

CREATE TABLE IF NOT EXISTS restaurant_rating (
    run_id      int  NOT NULL REFERENCES rating_run (id) ON DELETE CASCADE,
    place_id    int  NOT NULL REFERENCES place (id) ON DELETE CASCADE,
    composite   double precision NOT NULL,   -- weighted aspect composite on 1 to 5
    ci_low      double precision NOT NULL,
    ci_high     double precision NOT NULL,
    rank        int  NOT NULL,
    rank_low    int  NOT NULL,               -- 90% interval of the rank across posterior draws
    rank_high   int  NOT NULL,
    stars_shrunk double precision NOT NULL,  -- the review stars, shrunk and recency weighted the same way, on 1 to 5
    yelp_stars  real,                        -- Yelp's own business rating, unshrunk
    n_reviews   int  NOT NULL,
    status      text NOT NULL DEFAULT 'provisional' CHECK (status = 'provisional'),
    PRIMARY KEY (run_id, place_id)
);
