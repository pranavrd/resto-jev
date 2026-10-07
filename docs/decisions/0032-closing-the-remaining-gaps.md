# 0032: Closing the gaps left by 0028 to 0031

- **Status:** Accepted. Five changes ship; three candidates that failed their own pre-registered criteria are **options, not defaults**; one change that I made the default for part of a day was put back after a live check (see "A mistake found by clicking").
- **Date:** 2026-10-06
- **Code:** `chat.py` (lowest-first plans, progress and cancellation, planner lexicons p2/p3/p4, rewrite r1/r2/r3 and `stands_alone`, the this-place check k1/k2/k3), `tablemap.py` (`lowest_first`), `tablemap_api.py` (`POST /tablemap/chat/stream`, `strict`), `chat_eval.py`, `chat_followup_eval.py`, `chat_verifier_eval.py`; `web/src/chat/` (stream reader, progress, saved conversation, strict toggle); sets `plan_questions_v4`, `v5`, `v6`, `followups_v2`, `v3`, verifier batch 2; runs and logs in `docs/chat-eval/`
- Everything evaluated here is invented and shareable. Real-review answers seen while clicking through the view are not stored anywhere.

## What was open, and what happened to each

| Gap (from decisions 0025 to 0031) | Result |
|---|---|
| "Worst" and "lowest" questions are refused (no ascending ranks) | **Done.** Lowest-first by code for food, service, atmosphere, value or overall (see below). |
| Cancel stops the browser's wait, not the server's work | **Done.** |
| No streaming | **Partly.** Progress streams; the answer text does not. |
| A conversation is lost on reload | **Done, in the browser only.** |
| A message that only adds a condition ("and good service as well") is not seen as a follow-up | **Done**, and the cause was not the one decision 0031 gave. A second defect found on the way (complete questions turned into follow-ups) is fixed too. |
| Planner misses ("terrific staff", "Broad Street Line", "the three best bars") | **Fixed in p3/p4 and covered by tests, but the held-out criteria were not met, so the default stays p2.** |
| The check accepts a passage that only mentions the topic | **A candidate (k2) removes most of it; it failed its recall criterion, so it is an option** ("strict matching"), not the default. |
| CI had never run on GitHub | **Done.** The first push ran it and both jobs (`python`, `web`) passed ([run 37550809861](https://github.com/pranavrd/resto-jev/actions/runs/37550809861)). The repository is public; the history was scanned first. |

## Ascending sorts: the lowest provisional scores first

A question with "worst", "lowest", "poorest", "bottom" or "least friendly/rated" is planned as before (the model decides whether it is in scope; rules read kind, area and rail), and then **code** turns it into a ranking from the low end: by the one aspect it names (`food`, `service`, `atmosphere`, `value`; "friendly" counts as service), or by the composite score when it names none. The model never sets the direction. Places need at least 10 reviews (the same floor as the best-first rank), and unrated places still go last. Every such answer carries a line saying it is an AI scorer's reading and **not a verdict on the place**, and the structured response has `lowest_first: true` so a view cannot present it as anything else.

Refused, with the reason: the "worst" of a dish or any other topic (a match with review text has no low end: "worst pizza"), and a question that names two things at once ("worst food and service"). The old refusal is kept for planner p1, and `STREETWALKER_LOWEST=0` brings it back for everything, for an owner who would rather not name low-scoring businesses at all. The retrieval gained `lowest_first` (and `GET /tablemap/search?rank_by=service&lowest_first=true`); asking for it without a score to rank by is a 422.

**Checked by clicking** against the real data: "Which restaurants in Rittenhouse have the worst service?" listed five restaurants with their rating words, under the line above. **A design call to know about:** this does put named businesses on a list of lowest AI-scored places. The scores are provisional and unvalidated against people (decision 0021); the line says so, the places need 10 reviews, and the switch exists. I did not add more than that.

## Progress and a real cancel

`POST /tablemap/chat/stream` returns the same answer as `/chat` as newline-delimited JSON: `stage` events while it works (reading a follow-up, planning, "Searching" with what is searched, the places found, "Checking place 2 of 5", writing), then one `answer` event (exactly the `/chat` JSON, tested equal) or one `error` event with the status `/chat` would have used. The answer is still delivered whole at the end; the progress is what streams.

**Cancel now stops the work.** The model call is streamed from Ollama, and the code checks a flag between tokens and between steps. If the client goes away, the server sets the flag, leaves the model connection (which ends the generation on the Ollama side), and runs no further step. Tests: a stub server that speaks Ollama's protocol sees the hang-up within the test's limit; a real uvicorn server on a local port sees a client disconnect reach a fake model that never finishes; mutating the cancel line makes that test fail. **Live:** clicking Cancel in the browser put "the client left, so the answer was cancelled before it finished" in the server log. **What cancel cannot do:** interrupt a step that is only reading its prompt or loading a model (the next token or step boundary is where it stops).

## The conversation, saved in the browser

The finished turns (at most 20) and the answer-style and strict choices are kept in `localStorage`, and a reload brings them back. **New chat clears them** (checked by clicking: the stored key is gone). It holds review quotes, so it stays on this machine like the rest; the server stores nothing. The loader ignores anything corrupt, foreign or hand-edited, and a blocked or full store does not break the page (tests).

## Add-a-condition follow-ups, and a mistake found by clicking

**The cause decision 0031 gave was wrong.** For "and good service as well" and "not too loud though" the model's raw reply was `followup: true` with a correct standalone question. The code guard `kept_the_words` threw it away because the user's message contained "well" and "though", which it counted as content words the rewrite had dropped. r2 exempts such connectives, labels the last turn "Latest turn" and says so in the prompt. On a fresh set (`followups_v2`, 16 dev + 16 test, with two- and three-turn chains) r1 scored 14/16 and r2 16/16 on test.

**The pre-registered criterion for that (at least +3 over r1) was not met (+2) and was badly set**: r1 scored 14, so +3 was impossible. I adopted r2 anyway, as a judgement that overrode the written rule, and said so in the log.

**Then a live check showed r2 was harmful.** In the browser, after a cafe turn, the suggested question "Where can I sit outside for a drink?" was understood as "Bars in Rittenhouse with good service where I can sit outside for a drink": a complete question merged with the last turn. The controls of sets v1 and v2 (three or four per half, mostly on a different subject from the last turn) could not have shown it. I put r2 back and built a set for exactly this: `followups_v3`, 48 conversations, per half **12 complete questions that follow an earlier turn and must come back unchanged**, and 12 genuine follow-ups. Measured on it, **r1, the rewrite of decision 0031, rewrote 6 of 24 complete questions (a quarter)**; so did r2. Decision 0031's "controls 4/4" was a weak test and its multi-turn result is overstated for complete questions.

**r3** is r1's prompt unchanged, plus the connective exemption, plus a **completeness guard in code** (`stands_alone`): a message of four or more words that does not open like a continuation ("and", "only", "what about", "same"), has no reference or continuation word ("those", "it", "one", "too", "instead", "as well", "the second") and names no place from the earlier turns is answered as typed, with no model call. It was developed on the dev half and judged once on the test half, criterion written first:

| `followups_v3`, test half (24) | r1 | r2 | **r3** |
|---|---|---|---|
| Complete questions returned unchanged (of 12) | 10 | 9 | **12** |
| Genuine follow-ups fully correct (of 12) | 9 | 8 | **10** |
| Follow-up flag acceptable (of 24) | 20 | 20 | **23** |

Criterion (r3 becomes the default only if at least 11 of 12 complete questions are unchanged, its genuine follow-ups are right on at least as many as r1's, and its flag is right on at least as many): **met on all three. r3 is the default** (`STREETWALKER_REWRITE=r1|r2` switches back). Live in the browser, the question that failed above is now searched as typed, with no "Understood as" line. Through the real model (not the browser), after a cafe turn, "and with a good atmosphere as well" becomes "Quiet cafes in Rittenhouse with good service and a good atmosphere" and "not too loud though" becomes "Quiet cafes in Rittenhouse with good service that are not too loud".

**Not fixed:** a reference to the whole set ("either of them", "any of them") often makes the model list the places instead of keeping the search (0/3 on dev for r3, 3/3 on test: noise around a weakness); three-word follow-ups ("not too expensive", "make it cheaper") are not recognised; the guard blocks one genuine follow-up of 36 across the sets ("show me the best").

**An overlap found while writing these tests, disclosed here:** the rule text of the r1 and r2 prompts quotes the phrase "in Rittenhouse instead", and one v1 *test* message (decision 0031) is exactly that, so 1 of its 16 held-out conversations was in the prompt. Without it, 0031's held-out result is 13 of 15 against 7 of 15 for the bare message (+6 against the +5 bar), so its conclusion stands. The r2 prompt also uses "Bakeries in Rittenhouse" as an example history, which is the history of one v1 and one v2 test conversation (the message under test is different, and r1, which lacks the example, got the v2 one right as well). A test now records both overlaps and fails on any new one.

## Planner p3 and p4: wider word lists, criteria not met, default unchanged

p3 widens the guard lexicon in ordinary English (quality adjectives, nouns for the people who work in a place, kinds of place, number words, Philadelphia's transit lines, hyphenated compounds), reads "reasonably priced"-type phrases, strips quality, kind, area and number words from the model's topic, and tells the model that a question naming a transit line is in scope. p4 adds rules for what p3 got wrong on its held-out set: a digit before a kind ("3 good pizzerias"), "St" for Street and a street name before a stop, and the -est and -er forms of adjectives it knows. **p2 stays available and unchanged**: 1,023 plans from 341 questions (all the planner and follow-up sets) are identical before p3 and after p4.

| Held-out set (24 invented questions each, written after the freeze) | p2 | p3 | p4 |
|---|---|---|---|
| v5 | 17 | **20** | |
| v6 | 20 | | **22** |

Criteria written before each read: **p3 at least +5 over p2 on v5 (got +3); p4 at least +4 on v6 (got +2). Neither met, so the default stays p2** (`STREETWALKER_PLANNER=p3|p4` is the owner's switch). The planner was never worse than p2 on any question of either set (5 questions right where p2 was wrong, 0 the other way; an exact one-sided sign test over those 5 gives p = 0.03). That pooled test was not written beforehand, so it is not offered as a reason to adopt: the bars were mine, they were reachable, and they were missed. v4 was written knowing the categories and then contributed words to the lists, so it is development data only (p3: 24/24 and 23/24 there, which is not an estimate). Each fresh set found a few more words (a digit count, "St", "nicest"; then "barista"): **word lists are never finished.**

## The this-place check (k2): strict matching as an option

On a new batch of twelve topics (`chat_verifier_eval`, batch 2: four incidental passages per topic and a place made only of them), the check of decision 0027 (k1) accepted 9 of 54 and 10 of 54 places whose only passages merely mention the topic (another place, hearsay, a wish, the words in another sense, the reviewer's own circumstances). k2 asks a second question of every passage k1 accepted, "does the passage say THIS place itself has it?", with six invented worked examples.

| | dev2 k1 | dev2 k2 | test2 k1 | test2 k2 |
|---|---|---|---|---|
| Place false positives (of 54) | 9 | **3** | 10 | **3** |
| Passage recall | 85% | 85% | 81% | **75%** |
| Calls per place | 2.0 | 3.0 | 2.0 | 3.0 |

The pre-registered criterion had three parts. (a) False positives down by at least a third: **met** (10 to 3). (c) No more false positives on planted-instruction passages: **met**. **(b) Passage recall within 5 points of the baseline: 6.3 points lost on test2, not met**, by three passages of 48. So **k1 stays the default.** k2 is offered per question as **strict matching** (`"strict": true` on the endpoint; a button in the chat view, off by default, with a note on any answer that used it). The honest price is on the table above: fewer wrong places, and a right place missed more often (25 of 30 against 28 of 30 on test2). Because a wrong place is shown with a quote that gives it away and a missed place is invisible, I would lean to turning it on; the written rule says not to, so the owner decides. A third variant (k3, only the stricter question) had the best recall and the lowest cost on dev2 and was never read on test2 because the rule picked k2.

## What was verified, and what was not

Verified: 440 Python tests (against the real local database; two skipped), 64 web tests, type check and production build, ruff; every number in this record recomputed from committed run files by `tests/test_published_numbers.py`; and, by clicking in the browser against the real API and local model: the progress text, the lowest-first answer, a reload that kept the conversation, New chat clearing it, the strict toggle and its note, Cancel and the server log line, the follow-up that adds a condition, and the complete question that r2 had merged.

Not verified: any of this on a model other than `qwen2.5:7b`; the planner and rewrite on anyone's wording but one author's; lowest-first quality against people; and the strict check against real reviews (the sets are invented).

## Limits

- All sets are small (16 to 54 items per half) and written by one author; intervals are wide, and the discipline (criteria first, read once) is the only protection against over-reading them.
- Three of the changes in this record missed their own bars, and one criterion was set so that it could not be met. They are reported as missed, not re-read as met; the defaults follow the written rules, except r2, which I adopted against them and withdrew.
- Progress streams but the answer does not, and the "writing" step of the summary style is still the longest wait.
- The saved conversation is per browser; it is not shared between machines and nothing on the server knows about it.
