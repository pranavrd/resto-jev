"""Aspect questions and Score parsing. Invented review text only: Yelp data never enters the repository."""

from types import SimpleNamespace

from streetwalker.aspects import (
    ASPECT_PROMPT_VERSION,
    ASPECTS,
    LEVELS,
    SCORE_TOP,
    build_questions,
    parse_aspects,
)
from streetwalker.jev_client import parse


def test_every_aspect_has_a_mentioned_question_and_a_five_level_score():
    qs = build_questions()
    assert ASPECT_PROMPT_VERSION == "a1"
    assert set(qs) == {f"{a}_{kind}" for a in ASPECTS for kind in ("mentioned", "sentiment")}
    for a in ASPECTS:
        assert len(LEVELS[a]) == SCORE_TOP + 1 == 5
        assert len(set(LEVELS[a])) == 5  # five distinct descriptions: Jev judges each level only by its words


def test_levels_describe_situations_not_numbers():
    for a in ASPECTS:
        for level in LEVELS[a]:
            assert not any(ch.isdigit() for ch in level) and len(level.split()) >= 6


def test_questions_are_one_dimensional_and_name_their_aspect():
    qs = build_questions()
    assert "food and drinks" in qs["food_mentioned"].instructions
    assert "overpriced" in qs["value_sentiment"].criteria[1]
    assert all(q.instructions for q in qs.values())


def test_score_answers_are_parsed_with_level_probabilities():
    resp = SimpleNamespace(answers={
        "food_mentioned": SimpleNamespace(type="noul", noul=0.97),
        "food_sentiment": SimpleNamespace(type="score", score=3.4, confidence=0.7, probabilities={0: 0.0, 1: 0.0, 2: 0.1, 3: 0.4, 4: 0.5}),
    })
    mentioned, sentiment = parse(resp)
    assert mentioned.probs == {"yes": 0.97}
    assert sentiment.score == 3.4 and sentiment.confidence == 0.7 and sentiment.probs["4"] == 0.5


def test_parse_aspects_pairs_the_two_questions_and_skips_incomplete_aspects():
    def noul(p):
        return SimpleNamespace(question="", probs={"yes": p}, score=None, confidence=max(p, 1 - p))

    def score(s):
        return SimpleNamespace(question="", probs={str(i): 0.2 for i in range(5)}, score=s, confidence=0.5)

    out = parse_aspects({"food_mentioned": noul(0.9), "food_sentiment": score(3.2), "service_mentioned": noul(0.1)})
    assert [o["aspect"] for o in out] == ["food"]  # service has no sentiment answer, the others have nothing
    assert out[0]["mentioned"] == 0.9 and out[0]["score"] == 3.2 and len(out[0]["probs"]) == 5
