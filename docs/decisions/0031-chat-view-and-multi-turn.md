# 0031: A chat view in the web app, and multi-turn follow-ups

- **Status:** Accepted. Both are opt-in (the chat router needs `STREETWALKER_TABLEMAP=1`).
- **Date:** 2026-10-05
- **Code:** `chat.py` (`rewrite_question`, `history_block`, `Turn`, the richer `Answer`), `tablemap_api.py` (`history` on `POST /tablemap/chat`), `chat_followup_eval.py`; `web/src/chat/` (`chat.ts`, `ChatApp.tsx`, tests), the `#/chat` view in `web/src/Shell.tsx`; set `docs/chat-eval/followups_v1.json`, log and runs
- The follow-up set is invented and shareable. Real-review answers shown in the view are not stored anywhere.

## Multi-turn

**Design.** The server keeps no conversation. The client sends the earlier turns (each exactly the `turn` field of an earlier response: the standalone question, what was searched, the places shown; at most ten accepted, the last three used). For a message with history, a model call decides whether it is a follow-up and, if so, writes one standalone question that keeps every word the user wrote and adds only what is needed from context. Everything after that is the single-turn pipeline unchanged: planner p2 and its guards, the check, the writer, the quote checks, the provisional caveat. The answer says so when it rewrote: "Understood as: ...", then "Searched for: ...".

**Code guards on the rewrite.** A rewrite is discarded, and the message answered as typed, when the model says it is not a follow-up, repeats the message, runs past 300 characters, or drops a content word of the user's message (a five-letter prefix match; filler and reference words such as "the second one" may be replaced by a name). The history is clipped, stripped of angle brackets and labelled as data to ignore as instructions. The refusal for "worst" and "lowest" questions looks at both the message and the rewrite.

**Judged on a fresh set,** `followups_v1.json`: 32 invented one-turn conversations (16 dev, 16 test) written before the rewrite existed, with controls that are not follow-ups and must come back unchanged. The baseline is the same planner on the bare message.

| | Rewrite + plan | Without history |
|---|---|---|
| dev, first draft | 12/16 (plan right 13) | 9/16 |
| dev, after rules and examples in the prompt (**tuned on dev, not an estimate**) | 14/16 (plan right 15) | 9/16 |
| **test, read once, criterion written first** | **plan right 14/16, flag acceptable 15/16, controls 4/4** | **7/16** |

Criterion: at least 5 of 16 better than the baseline (+7), the flag acceptable on at least 14 (15), all four controls unchanged (4/4). All met. **Limits:** 16 conversations, one author, one turn of history in every case (longer chains and a conversation that changes subject several times are not tested); and a message that only adds a condition ("and good service as well", "not too loud though") was not recognised as a follow-up in both halves. A follow-up costs one more model call (about 4 to 5 seconds).

## The web view (`#/chat`)

A chat page in the existing app, behind the same switcher. It shows:

- **Always on top: a provisional banner** (the ratings are AI-scored, not validated against people, reviews end in January 2022, private and local).
- **Per answer:** the "Understood as" line for a rewritten follow-up; "Searched for: ..."; place cards with name, kind and area, a model-written summary labelled **"Model-written, not checked"**, verbatim quotes labelled with their month, and the provisional rating words; a plain notice when nothing is to be shown; the places the check did not accept, by name; how many quotes were dropped as not verbatim; "listed alphabetically: not a ranking" when it is true; and the server's caveat at the foot of every answer.
- **Controls:** a Summaries or Quotes-only toggle (decision 0028; the choice survives "New chat"), Send (and Enter; Shift+Enter for a new line), Cancel while waiting (with a running timer, since answers take 10 to 60 s), Try again after a failure, New chat, and four suggested questions on the empty page.
- **Safe by construction:** all text from the server is rendered by React as text, never as HTML (review text is untrusted); a render test feeds `<script>` and `<img onerror>` through the names, summaries and quotes.

**Checked by clicking** in the browser against the real API and the local model: a suggestion button, a typed follow-up sent with the Send button ("what about in Roxborough?" became "Quiet cafes in Roxborough with good service" and was searched as such), Enter to send, the Quotes-only toggle (cards with verbatim quotes), New chat, Cancel, the failure path with the API stopped, and Try again after restarting it. **The click test found a bug:** with the API down, the dev proxy's gateway error was shown as "the model gave an unusable answer"; the server always sends a detail with its own 502 and 503, so a gateway error without one now reads "Cannot reach the API". Unit tests cover the request and history building, the error text, and the render.

## Limits

- **Cancel stops the browser's wait, not the server's work:** the request keeps running until the model finishes.
- **No streaming:** the answer appears when it is complete; the first question after a cold start took about 50 s.
- **A conversation lives in the page:** reloading loses it. Nothing is stored on the server or in the browser.
- **The check's mistakes show.** In Quotes-only mode a place accepted for the wrong reason shows the quote that gives it away. That is deliberate (decision 0028).
- **The view is only for the owner's machine:** the API is unauthenticated and the router is opt-in. The static page itself contains no Yelp data.
