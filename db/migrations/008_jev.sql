-- One row per batch of Jev calls (a trial, a full run, a re-run with different wording).
CREATE TABLE IF NOT EXISTS jev_run (
    id             serial PRIMARY KEY,
    purpose        text NOT NULL,      -- e.g. trial-1, full-p2
    prompt_version text NOT NULL,      -- version of the questions and state format
    model_version  text NOT NULL,      -- pinned, e.g. jev-1.13.0
    state_format   text NOT NULL,      -- text | json
    n_buildings    int,
    input_tokens   bigint,
    output_tokens  bigint,
    est_cost_usd   double precision,
    started_at     timestamptz NOT NULL DEFAULT now(),
    finished_at    timestamptz
);

-- One row per question per building per run. `probs` holds the full distribution for pick-one
-- questions, or {"yes": p} for yes/no questions.
CREATE TABLE IF NOT EXISTS decision (
    id            bigserial PRIMARY KEY,
    run_id        int    NOT NULL REFERENCES jev_run (id) ON DELETE CASCADE,
    building_id   int    NOT NULL REFERENCES building (id) ON DELETE CASCADE,
    question      text   NOT NULL,     -- d1 | d2 | d3
    answer        text,                -- chosen option, or "true"/"false" for yes/no
    probs         jsonb,
    confidence    double precision,    -- Jev's confidence in the answer (for yes/no: max(p, 1-p))
    tier          int    NOT NULL DEFAULT 0,
    model_version text   NOT NULL,
    input_tokens  int,                 -- per request (shared by the request's questions)
    output_tokens int,
    latency_ms    int,
    error         text,
    created_at    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (run_id, building_id, question)
);
CREATE INDEX IF NOT EXISTS decision_building_idx ON decision (building_id, question);

-- Named evaluation sets, so wording tuned on a trial set can be excluded from final reporting.
CREATE TABLE IF NOT EXISTS eval_set (
    name        text NOT NULL,
    building_id int  NOT NULL REFERENCES building (id) ON DELETE CASCADE,
    stratum     text,
    PRIMARY KEY (name, building_id)
);
