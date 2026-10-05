-- Dense embeddings of Yelp review text for the TableMap retrieval layer (decision 0024). PRIVATE: derived from Yelp Data.
-- `model` names the embedding model and its digest ('nomic-embed-text@0a109f422b47'): vectors from different models are not comparable.
-- No vector index on purpose: retrieval filters by place first and then scans exactly, and the table is small (one row per review).
CREATE TABLE IF NOT EXISTS review_embedding (
    review_id text NOT NULL REFERENCES yelp_review (review_id) ON DELETE CASCADE,
    model     text NOT NULL,
    embedding vector(768) NOT NULL,
    PRIMARY KEY (review_id, model)
);
