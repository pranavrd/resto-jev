-- Aspect scoring of Yelp reviews with Jev (decision 0020). PRIVATE: derived from Yelp Data (agreement 4A, 4E, 5).
CREATE TABLE IF NOT EXISTS aspect_run (
    id             serial PRIMARY KEY,
    purpose        text NOT NULL,
    prompt_version text NOT NULL,
    model_version  text NOT NULL,
    n_reviews      int,
    input_tokens   bigint,
    output_tokens  bigint,
    est_cost_usd   double precision,
    started_at     timestamptz NOT NULL DEFAULT now(),
    finished_at    timestamptz
);

-- One row per review per run: the request itself (tokens, time, error).
CREATE TABLE IF NOT EXISTS aspect_request (
    run_id        int  NOT NULL REFERENCES aspect_run (id) ON DELETE CASCADE,
    review_id     text NOT NULL REFERENCES yelp_review (review_id) ON DELETE CASCADE,
    input_tokens  int,
    output_tokens int,
    latency_ms    int,
    error         text,
    PRIMARY KEY (run_id, review_id)
);

-- One row per review, aspect and run. `mentioned` is Jev's probability that the review says anything about the aspect;
-- `score` is its position on the 0 (clearly negative) to 4 (clearly positive) scale and is only meaningful when mentioned.
CREATE TABLE IF NOT EXISTS aspect_score (
    run_id     int  NOT NULL REFERENCES aspect_run (id) ON DELETE CASCADE,
    review_id  text NOT NULL REFERENCES yelp_review (review_id) ON DELETE CASCADE,
    aspect     text NOT NULL,           -- food | atmosphere | service | value
    mentioned  double precision NOT NULL,
    score      double precision NOT NULL,
    confidence double precision NOT NULL,
    probs      jsonb NOT NULL,          -- probability of each of the five levels
    PRIMARY KEY (run_id, review_id, aspect)
);
CREATE INDEX IF NOT EXISTS aspect_score_review_idx ON aspect_score (review_id);
