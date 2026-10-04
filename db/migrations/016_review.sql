-- Tier 3 human review queue (decision 0018). Labels are blind: the page never shows ground truth or a prediction.
CREATE TABLE IF NOT EXISTS review_item (
    set_name    text NOT NULL,              -- verify (random, image-covered: checks the ground truth) | gate (escalated by the cascade)
    building_id int  NOT NULL REFERENCES building (id) ON DELETE CASCADE,
    rank        int  NOT NULL,
    PRIMARY KEY (set_name, building_id)
);

CREATE TABLE IF NOT EXISTS human_label (
    id             serial PRIMARY KEY,
    building_id    int  NOT NULL REFERENCES building (id) ON DELETE CASCADE,
    set_name       text NOT NULL,
    label          text NOT NULL,           -- a D1 class, or cant_tell
    seconds        double precision,        -- time from showing the item to the label
    evidence_shown boolean NOT NULL DEFAULT false,
    undone         boolean NOT NULL DEFAULT false,
    created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS human_label_building_idx ON human_label (building_id);
