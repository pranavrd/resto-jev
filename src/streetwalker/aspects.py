"""Aspect questions for restaurant reviews (decision 0020), versioned like the building questions.

Four aspects, each asked as two questions in one request: is it mentioned (a yes/no), and how the reviewer feels about it
(a five-level Score). Jev judges every level on its own against the text and never sees the numbers, so the levels are
described as situations. Changing any wording means a new ASPECT_PROMPT_VERSION.
"""

from typesafe_sdk import Noul, Score

ASPECT_PROMPT_VERSION = "a1"
ASPECTS = ("food", "atmosphere", "service", "value")
SCORE_TOP = 4  # levels 0 to 4

DEFINITIONS = {
    "food": "the food and drinks themselves: taste, quality, freshness, portion size, the menu",
    "atmosphere": "the place and its mood: decor, noise, music, cleanliness of the room, seating, crowding, the setting",
    "service": "the staff and how the visit was run: friendliness, attentiveness, speed, mistakes, waiting for a table or the check",
    "value": "what the reviewer paid compared with what they got: cheap, fair or overpriced for the quality and the portions",
}

# Level descriptions: situations, from clearly negative (0) to clearly positive (4).
LEVELS = {
    "food": [
        "The reviewer is disappointed or angry about the food or drinks: bad, bland, cold, spoiled or not worth eating",
        "The food is mostly disappointing or only so-so, with at most a small point in its favour",
        "The food gets both praise and criticism, or is described flatly (it was fine, okay, average)",
        "The food is mostly good, with a minor complaint or without enthusiasm",
        "The reviewer is enthusiastic about the food or drinks: delicious, excellent, a highlight",
    ],
    "atmosphere": [
        "The reviewer dislikes the place itself: loud, dirty, cramped, dingy or unpleasant to sit in",
        "The atmosphere is mostly disappointing: too noisy, tired or uncomfortable, with little to like",
        "The atmosphere gets both praise and criticism, or is described flatly (a normal dining room)",
        "The atmosphere is mostly pleasant, with a minor complaint or without enthusiasm",
        "The reviewer loves the place: charming, lovely decor, cosy, a great setting or mood",
    ],
    "service": [
        "The reviewer is unhappy with the staff or the running of the visit: rude, ignored, very slow or wrong orders",
        "The service is mostly disappointing: slow, inattentive or uneven, with little to praise",
        "The service gets both praise and criticism, or is described flatly (the staff were fine)",
        "The service is mostly good, with a minor complaint or without enthusiasm",
        "The reviewer is enthusiastic about the service: friendly, attentive, fast, went out of their way",
    ],
    "value": [
        "The reviewer says it was a rip-off: far too expensive for what they got",
        "The reviewer finds it somewhat overpriced for the quality or portions",
        "The price is described as fair, ordinary or neither good nor bad for what it was",
        "The reviewer finds it reasonably priced or good for the money, without enthusiasm",
        "The reviewer says it was a bargain: great portions or quality for a low price",
    ],
}


def build_questions(version: str = ASPECT_PROMPT_VERSION) -> dict:
    assert version == ASPECT_PROMPT_VERSION, version
    qs: dict = {}
    for a in ASPECTS:
        qs[f"{a}_mentioned"] = Noul(
            instructions=f"Does the review say anything about {DEFINITIONS[a]}?",
            criteria={
                "true": f"The reviewer comments on this, even briefly: {DEFINITIONS[a]}.",
                "false": "The review does not comment on this at all.",
            },
        )
        qs[f"{a}_sentiment"] = Score(
            instructions=f"How does the reviewer feel about {DEFINITIONS[a]}? If the review does not discuss it, pick the middle level.",
            criteria=LEVELS[a],
        )
    return qs


def parse_aspects(answers: dict) -> list[dict]:
    """Per aspect: mentioned probability, score, confidence and the five level probabilities. `answers` maps question name to Answer."""
    out = []
    for a in ASPECTS:
        m, s = answers.get(f"{a}_mentioned"), answers.get(f"{a}_sentiment")
        if m is None or s is None or s.score is None:
            continue
        out.append({"aspect": a, "mentioned": m.probs["yes"], "score": s.score, "confidence": s.confidence, "probs": s.probs})
    return out
