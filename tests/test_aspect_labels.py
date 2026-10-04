"""Sampling tests on invented reviews: Yelp data never enters the repository."""

from collections import Counter

from streetwalker.aspect_labels import (
    MIN_CHARS,
    N_REPEAT,
    PER_STAR,
    PLACE_CAP,
    REPEAT_GAP,
    divergent,
    sample_batch,
)


def make(n_places=60, per_place=60):
    """Reviews with spread-out stars; some mention value, some have an aspect that disagrees with the stars."""
    out = []
    for p in range(n_places):
        for k in range(per_place):
            stars = 1 + (p + k) % 5
            value_m = 0.9 if k % 4 == 0 else 0.05
            food = (0.97, 3.9 if stars >= 4 else 0.5)
            service = (0.9, 1.0 if (stars >= 4 and k % 7 == 0) else (3.0 if (stars <= 2 and k % 6 == 0) else 2.5 + (stars - 3) * 0.5))
            out.append({"review_id": f"r{p}_{k}", "place_id": p, "stars": stars, "chars": 200 if k % 10 else 30,
                        "aspects": {"food": food, "service": service, "value": (value_m, 1.5), "atmosphere": (0.1, 2.0)}})
    return out


def test_divergence_means_an_aspect_that_contradicts_the_stars():
    base = {"review_id": "x", "place_id": 1, "chars": 200}
    assert divergent({**base, "stars": 5, "aspects": {"service": (0.9, 1.0)}})  # glowing review, negative service
    assert divergent({**base, "stars": 1, "aspects": {"food": (0.9, 3.0)}})  # angry review, positive food
    assert not divergent({**base, "stars": 5, "aspects": {"service": (0.9, 3.5)}})
    assert not divergent({**base, "stars": 5, "aspects": {"service": (0.2, 0.5)}})  # not mentioned, so no disagreement to speak of
    assert not divergent({**base, "stars": 3, "aspects": {"service": (0.9, 0.5)}})  # a middling review can hold a bad aspect


def test_batch_has_the_planned_parts_and_is_deterministic():
    cands = make()
    one, two = sample_batch(cands, 7), sample_batch(cands, 7)
    assert one == two and sample_batch(cands, 8) != one
    by = Counter(i["stratum"] for i in one)
    assert by["random"] == PER_STAR * 5 and by["value_probe"] == 25 and by["divergence_probe"] == 20 and by["repeat"] == N_REPEAT


def test_random_part_is_balanced_by_stars_and_probes_pick_what_they_claim():
    cands = make()
    info = {c["review_id"]: c for c in cands}
    items = sample_batch(cands, 7)
    rand = [info[i["review_id"]] for i in items if i["stratum"] == "random"]
    assert Counter(c["stars"] for c in rand) == {s: PER_STAR for s in range(1, 6)}
    assert all(info[i["review_id"]]["aspects"]["value"][0] >= 0.5 for i in items if i["stratum"] == "value_probe")
    assert all(divergent(info[i["review_id"]]) for i in items if i["stratum"] == "divergence_probe")
    assert all(c["chars"] >= MIN_CHARS for c in (info[i["review_id"]] for i in items))


def test_no_place_is_over_represented_and_originals_are_unique():
    cands = make()
    info = {c["review_id"]: c for c in cands}
    items = sample_batch(cands, 7)
    originals = [i["review_id"] for i in items if i["stratum"] != "repeat"]
    assert len(originals) == len(set(originals))
    assert max(Counter(info[r]["place_id"] for r in originals).values()) <= PLACE_CAP
    assert len({info[r]["place_id"] for r in originals}) >= 50  # spread over most of the places


def test_repeats_come_later_than_their_originals_and_point_at_them():
    items = sample_batch(make(), 7)
    for k, it in enumerate(items):
        if it["stratum"] == "repeat":
            o = it["repeat_of"]
            assert items[o]["review_id"] == it["review_id"] and items[o]["stratum"] == "random"
            assert k - o >= REPEAT_GAP  # never recalled straight after the original
    assert sum(it["stratum"] == "repeat" for it in items) == N_REPEAT


def test_a_small_pool_degrades_gracefully():
    items = sample_batch(make(n_places=2, per_place=30), 7)
    assert items and all(i["stratum"] in ("random", "value_probe", "divergence_probe", "repeat") for i in items)
