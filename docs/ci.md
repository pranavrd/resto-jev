# Continuous integration

`.github/workflows/ci.yml` runs on every push to `main` and on pull requests (decision 0030). It uses **invented fixtures, scripted models and committed run files only**: no Yelp data, no secrets, no model server.

## What runs

| Job | Steps |
|---|---|
| `python` | check that nothing under `data/`, `docs/private/` or `.env` is tracked; start Postgres from `db/Dockerfile` (PostGIS, pgvector, pg_trgm); install the package; `ruff check .`; apply every migration to the empty database; `pytest -q -rs` |
| `web` | `npm ci`, `npx tsc --noEmit`, `npx vitest run`, `npm run build` |

`pytest` is where the evals run. On the empty CI database that is several hundred tests (the ones that need the real database skip):

- **Unit tests** of the walk, frontage, evidence, features, cascade, rating, census, search, transit and API code.
- **Retrieval evals** (`tests/test_tablemap.py`): five invented places and eleven invented reviews inside one rolled-back transaction; the lexical eval (exact match on nine queries), the known synonym misses recorded as tests, filters, aspect thresholds, ranking rules, the default app staying free of Yelp fields, injection strings only ever travelling as bound parameters.
- **Chat tests** (`tests/test_chat.py`): the planner guards, quote verification, the writer versions and the check, with scripted models.
- **Instrument tests** (`test_chat_faithfulness.py`, `test_chat_verifier_eval.py`): the generators and checkers of the evaluation sets, including that no sentence or prompt example is reused between sets.
- **Published numbers** (`tests/test_published_numbers.py`): the figures in decisions 0025 to 0029 are recomputed from the committed run files with the current scorers and checkers. If a change moves a published number, this fails, and the change is either reverted or the record is updated on purpose.

## What does not run in CI

- **Anything that needs Ollama** (the embedding model or `qwen2.5:7b`): tests marked `needs_ollama` skip, and the model evals themselves (`chat_eval`, `chat_faithfulness`, `chat_verifier_eval` without `--rescore`) are run locally.
- **Tests that need the real database** (the place API with transit context, the building review and aspect labelling pages, a rating run): they skip on the empty CI database. That is 23 skips; run them locally against the real DB.
- **Real-review behaviour** of the chat and the retrieval: only the owner's machine has the data, and no figure from it is checked in.

## Running the model evals locally

```bash
.venv/bin/python -m pytest -q                                                 # includes the DB tests against the real database
STREETWALKER_MODEL_TESTS=1 .venv/bin/python -m pytest tests/test_chat.py -q   # adds the slow real-model smoke test
.venv/bin/python -m streetwalker.chat_eval --set v3 --split test --planner p2 # planner on a question set (read-once rules: docs/chat-eval)
.venv/bin/python -m streetwalker.chat_faithfulness --split dev --writer w3    # writer faithfulness
.venv/bin/python -m streetwalker.chat_verifier_eval --split dev --method per_passage
```

Each of these has its own read-once rule for held-out splits (see `docs/chat-eval/`). A change to a prompt or a rule needs a fresh invented set before it can be judged.

## Status of this workflow

**Its first run on GitHub (2026-10-06, push of commit 77a1939 to `main`, [run 37550809861](https://github.com/pranavrd/resto-jev/actions/runs/37550809861)) passed: both the `python` and the `web` job, on `ubuntu-latest`.** That includes building the Postgres image from `db/Dockerfile`, applying every migration to the empty database, lint, and the whole test suite. The step logs need a login to read, so the number of tests that ran there is not recorded here; locally, from a brand-new virtual environment against an empty database, the suite before decision 0032 gave 340 passed and 23 skipped, and the local suite is now 440 passed and 2 skipped against the real database (the database tests skip on the empty CI one).

The repository is public. What that means for what may be in it: nothing under `data/`, `docs/private/` or `.env` (the first step of the `python` job fails if any is tracked), no secrets (the history was scanned before the first push), and only invented data in the committed evaluation sets and runs.
