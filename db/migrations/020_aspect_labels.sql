-- Human labels for aspect scoring (decision 0021). PRIVATE: review text is Yelp Data; labels are derived from it.
-- No foreign key from here to yelp_review on purpose: relinking places deletes reviews that are no longer usable, and
-- that must never delete a person's labels. An item whose review has gone simply cannot be shown again.
CREATE TABLE IF NOT EXISTS aspect_label_item (
    item_id   serial PRIMARY KEY,
    review_id text NOT NULL,
    batch     int  NOT NULL,           -- batch 1 is the judging set: nothing may be tuned on it (decision 0021)
    stratum   text NOT NULL,           -- random | value_probe | divergence_probe | repeat
    rank      int  NOT NULL,           -- order shown; the page never shows the stratum
    repeat_of int  REFERENCES aspect_label_item (item_id),   -- a deliberate second showing, to measure consistency
    UNIQUE (batch, rank)
);
CREATE INDEX IF NOT EXISTS aspect_label_item_review_idx ON aspect_label_item (review_id);

CREATE TABLE IF NOT EXISTS aspect_label (
    id         serial PRIMARY KEY,
    item_id    int  NOT NULL REFERENCES aspect_label_item (item_id),
    labels     jsonb NOT NULL,         -- {"food": 3, "atmosphere": null, ...}: level 0 to 4, null = not mentioned
    seconds    double precision,
    undone     boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS aspect_label_item_id_idx ON aspect_label (item_id);
