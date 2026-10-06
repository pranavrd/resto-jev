# Relevance-check evaluation set (invented)

Measures the check that decides whether a place's passages answer a question (decision 0028), apart from the writer. `src/streetwalker/chat_verifier_eval.py` generates the set and runs a method on it. Everything is invented and shareable: no Yelp data.

**Fresh:** none of its topics, sentences or injection phrasings is in the faithfulness set (decision 0026) or in any prompt (tests check this).

**Twelve topics, split by topic:** six dev, six test, so a method is judged on topics it was never tuned on. Each topic has 16 passages in 9 categories: **direct**, **paraphrase**, **buried** (the answering sentence among neutral ones) and **injection_yes** (answering, plus a planted instruction) should be "yes"; **incidental** (uses the topic's words but does not say this place has it: another place, a missed chance, in passing), **negated** (says it does not), **unrelated**, **buried_no** and **injection_no** should be "no". Labels are by construction. A place is a pair of passages sharing a question (eight per topic: three with nothing, two with one answering and one not, three with two answering), so a check that goes passage by passage and one that takes both in a single call are compared on the same places.

**Injection phrasings:** the dev phrasings are in the file; the test phrasings were written only after the method was frozen (the log says when), in styles the sanitizer was not designed for.

**Not measured here:** what the writer then says (decision 0026), real reviews, or recall of the retrieval. A label can be argued (an "incidental" sentence that implies the answer); the categories and sentences are fixed before any run.
