"""A constructed test set for aspect scoring, with the truth known by construction (decision 0022).
Usage: .venv/bin/python -m streetwalker.aspect_probe [--save docs/probe/aspect_probe_results.json] [--from FILE]

Every review here is INVENTED, so this is not Yelp Data: the set, the outputs and the results can be committed and shared. It
exists because no human labels will be collected. It is not a substitute for them: the reviews are cleaner than real ones, I wrote
them, and passing says Jev handles clear cases and these specific traps, not that it matches a person on messy text.

Design. Fragments are single-aspect sentences with a known level (0 clearly negative to 4 clearly positive), three phrasings per
aspect and level. They are combined three ways:
  wrapped  one fragment inside an overall-tone sentence that says nothing about any aspect ("Five stars from me!" or "One star
           from me."). Each fragment appears twice, once with a positive wrapper and once with a negative one, so the pair is a
           counterfactual: if Jev reads the aspect and not the mood, the two scores are equal. The gap between them is the halo.
  control  tone sentences only: nothing about any aspect is said, so every aspect should be "not mentioned"
  cross    two fragments about different aspects with opposite polarity (a good one and a bad one): does one aspect's sentiment
           leak into the other's score?
"""

import argparse
import json
import random
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from streetwalker.aspects import ASPECTS, SCORE_TOP, build_questions, parse_aspects

SEED = 20261006
MENTION = 0.5

# fragments[aspect][level] = three phrasings. Each is about its own aspect only.
FRAGMENTS: dict[str, dict[int, list[str]]] = {
    "food": {
        0: ["The burger was inedible, cold in the middle and tasted like cardboard.",
            "My pasta arrived burnt and bland, and the sauce was awful.",
            "Everything we ordered was terrible; the fish smelled off and I couldn't eat it."],
        1: ["The pizza was soggy and underseasoned, though the salad was passable.",
            "Most of the dishes were disappointing, a dry chicken and a bland soup, with only the bread worth eating.",
            "The tacos were greasy and forgettable, not much to like."],
        2: ["The pasta was great but the pizza was soggy.",
            "The food was okay, nothing special and nothing bad.",
            "Some dishes were delicious and others were pretty bland."],
        3: ["The food was good, tasty burgers and fresh fries, though the dessert was a bit dry.",
            "Solid food overall, the pasta was well made; the soup was just average.",
            "I enjoyed the tacos and the guacamole; the rice was a little dry."],
        4: ["The food was absolutely incredible, the best pasta I've ever had.",
            "Every dish was delicious, the burger was perfect and the fries were amazing.",
            "Outstanding food, fresh, flavourful and beautifully cooked."],
    },
    "atmosphere": {
        0: ["The room was filthy and unbearably loud, I couldn't hear anyone at my table.",
            "Dingy, cramped and stuffy; the decor looked like it hadn't been touched in decades.",
            "The music was deafening and the dining room smelled of mildew."],
        1: ["It was quite noisy and the tables were jammed together, though the decor was nice.",
            "A cramped dark room with uncomfortable chairs, not much charm.",
            "The dining room felt tired and a bit gloomy."],
        2: ["The decor was lovely but it was very loud.",
            "A fairly ordinary dining room, nothing remarkable.",
            "Cozy upstairs, but the downstairs was cramped and noisy."],
        3: ["Pleasant dining room with nice lighting, a little crowded on a Friday.",
            "The place has a relaxed, comfortable vibe, though the music was slightly too loud.",
            "Nice decor and comfortable seating, a bit tight between tables."],
        4: ["The restaurant is gorgeous, candlelit, cozy and full of charm.",
            "Beautiful room, wonderful decor and the perfect romantic setting.",
            "I loved the atmosphere, relaxed and stylish with great music at just the right volume."],
    },
    "service": {
        0: ["Our server was rude, ignored us for half an hour and got our order wrong.",
            "The staff were dismissive and we waited over an hour for the check.",
            "Terrible service, the waiter forgot our drinks twice and never apologized."],
        1: ["Service was slow and inattentive, although the host was polite.",
            "Our waiter seemed annoyed and it took ages to get water, with little effort to make up for it.",
            "The staff were disorganized and mostly absent."],
        2: ["The server was friendly but very slow.",
            "Service was fine, nothing to complain about and nothing special.",
            "Our waiter was great, but the host was rude when we arrived."],
        3: ["The staff were friendly and helpful, though we waited a little for the check.",
            "Good service overall, an attentive waiter and only a short wait to be seated.",
            "Our server was kind and efficient, with one small mix-up on a drink order."],
        4: ["The service was outstanding, our waiter was warm, attentive and went out of his way for us.",
            "Staff were wonderful, so friendly and quick, and they remembered our names.",
            "Impeccable service from start to finish, everyone was helpful and kind."],
    },
    "value": {
        0: ["Way overpriced, it was a complete rip-off for what you get.",
            "Absurd prices, we paid a fortune for a basic evening out.",
            "A total waste of money, far too expensive."],
        1: ["A bit overpriced, I expected more for the money.",
            "Prices are on the high side, not great value for what you get.",
            "Somewhat expensive, I felt I paid too much for what it was."],
        2: ["Prices were what you would expect, neither cheap nor expensive.",
            "Some things were worth the price and others weren't.",
            "The prices were about average for the area."],
        3: ["Reasonable prices, I felt I got what I paid for.",
            "Good value for the money, fair prices all round.",
            "Fairly priced, a decent deal for what it is."],
        4: ["An absolute bargain, so cheap for what you get.",
            "Incredible value, you pay so little and get so much.",
            "So affordable, honestly the best deal in town."],
    },
}

# Overall-tone sentences. They say how the writer felt overall (including the star rating) and nothing about food, the room,
# the staff or the price.
WRAPPERS = {
    "pos": ["Five stars from me!", "Would absolutely recommend to everyone.", "I can't wait to come back.", "Overall a really great experience, highly recommended."],
    "neg": ["One star from me.", "I would not recommend this to anyone.", "I will never be back.", "Overall a terrible experience, avoid."],
}

# Words that mark each aspect, used only to check by test that the invented text keeps its aspects apart.
CUES = {
    "food": ("food", "burger", "pasta", "pizza", "taco", "salad", "soup", "fries", "dessert", "dish", "sauce", "fish", "chicken", "bread", "rice", "guacamole", "flavour"),
    "atmosphere": ("room", "decor", "loud", "noisy", "music", "cozy", "crowded", "cramped", "atmosphere", "vibe", "lighting", "seating", "romantic", "restaurant is"),
    "service": ("server", "waiter", "staff", "service", "host", "check", "waited", "forgot", "our order", "ignored"),
    "value": ("price", "priced", "expensive", "cheap", "value", "bargain", "money", "deal", "afford", "rip-off", "fortune", "waste of money", "pay"),
}


# Hand-picked hard cases: sarcasm, negation, backhanded praise, other languages, traps. expect[aspect] is None (not mentioned) or an
# acceptable range of levels (lo, hi). This says WHERE Jev fails, not how often: twenty cases carry no rate.
HARD_CASES: list[dict] = [
    {"note": "sarcasm", "text": "Oh sure, the service was just fantastic if you enjoy being ignored for forty minutes.", "expect": {"service": (0, 1)}},
    {"note": "negation", "text": "The food was not bad at all.", "expect": {"food": (2.5, 4)}},
    {"note": "hedge", "text": "I guess the pasta was fine, though I've had better.", "expect": {"food": (1, 2.5)}},
    {"note": "one phrase, two aspects", "text": "Great food for the price.", "expect": {"food": (3, 4), "value": (3, 4)}},
    {"note": "expensive but worth it", "text": "Expensive, but absolutely worth every penny.", "expect": {"value": (2, 4)}},
    {"note": "low expectations", "text": "For a dive bar, the food was amazing.", "expect": {"food": (3, 4)}},
    {"note": "delivery", "text": "Delivery took an hour and the courier was rude, but the burger itself was great.", "expect": {"service": (0, 1.5), "food": (3, 4)}},
    {"note": "Spanish", "text": "La comida estaba deliciosa pero el servicio fue horrible.", "expect": {"food": (3, 4), "service": (0, 1)}},
    {"note": "price stated without a judgement", "text": "They charge $14 for a cocktail.", "expect": {"value": (0.5, 2.5)}},
    {"note": "nothing about any aspect", "text": "Went on a Tuesday at 6pm with my sister. We took the train there.", "expect": {}},
    {"note": "negative words that are not about the place", "text": "Do not believe the bad reviews, the waitress was an angel!", "expect": {"service": (3, 4)}},
    {"note": "one word, two aspects", "text": "The soup was cold, and the room was freezing too.", "expect": {"food": (0, 1.5), "atmosphere": (0, 1.5)}},
    {"note": "three aspects, mixed", "text": "The price was fair and the pizza was great, but honestly the music was too loud for conversation.", "expect": {"value": (2.5, 4), "food": (3, 4), "atmosphere": (0.5, 2)}},
    {"note": "past versus present", "text": "Used to be amazing five years ago, now the food is mediocre at best.", "expect": {"food": (0.5, 2)}},
    {"note": "counterfactual stars", "text": "I'd have given five stars if the staff had been less slow.", "expect": {"service": (0, 2)}},
    {"note": "someone else's opinion", "text": "My friend loved the food but I found it overly salty.", "expect": {"food": (1, 2.5)}},
    {"note": "praise with a price sting", "text": "Best meal of my life, and the waiter was lovely, although it cost us a fortune.", "expect": {"food": (3.5, 4), "service": (3, 4), "value": (0, 1.5)}},
    {"note": "atmosphere only", "text": "The place was packed and buzzing, a great party atmosphere.", "expect": {"atmosphere": (3, 4)}},
    {"note": "no opinion at all", "text": "The restaurant has a website with a menu and opens at noon.", "expect": {}},
    {"note": "negative value, positive service", "text": "Not worth the money at all, but the staff did their best.", "expect": {"value": (0, 1), "service": (2.5, 4)}},
]


def score_hard(client) -> list[dict]:
    from streetwalker.aspect_run import state_for
    from streetwalker.jev_client import ask

    questions = build_questions()
    out = []
    for case in HARD_CASES:
        r = ask(client, state_for(case["text"]), questions)
        got = {} if r.error else {a["aspect"]: {"mentioned": a["mentioned"], "score": a["score"], "confidence": a["confidence"]} for a in parse_aspects({x.question: x for x in r.answers})}
        out.append({**case, "expect": {a: case["expect"].get(a) for a in ASPECTS}, "jev": got, "error": r.error})
    return out


def judge_hard(case: dict) -> dict[str, bool]:
    """Per aspect: did Jev get it right? Not mentioned must score below 0.5; a range allows half a level of slack."""
    res = {}
    for a in ASPECTS:
        want, got = case["expect"][a], case["jev"].get(a)
        if got is None:
            res[a] = False
        elif want is None:
            res[a] = got["mentioned"] < MENTION
        else:
            res[a] = got["mentioned"] >= MENTION and want[0] - 0.5 <= got["score"] <= want[1] + 0.5
    return res


def report_hard(cases: list[dict]) -> None:
    print("\nHand-picked hard cases (invented). A case passes an aspect if mention is right and the score is in the acceptable range (half a level of slack).")
    right = total = 0
    for c in cases:
        verdict = judge_hard(c)
        right += sum(verdict.values())
        total += len(verdict)
        marks = " ".join(f"{a[:4]}:{'ok' if ok else 'NO'}" for a, ok in verdict.items())
        seen = ", ".join(f"{a[:4]} {c['jev'][a]['score']:.1f}{'' if c['jev'][a]['mentioned'] >= MENTION else '(unmentioned)'}" for a in ASPECTS if a in c["jev"])
        print(f"  {'FAIL ' if not all(verdict.values()) else 'ok   '}{c['note']:42s} {marks}   Jev: {seen}")
    print(f"  {right} of {total} aspect judgements right ({right / total:.0%}); read the failures, not the rate")


def build_probes(seed: int = SEED) -> list[dict]:
    """The probe reviews with their expected answers. expect[aspect] = level 0 to 4, or None for not mentioned."""
    rng = random.Random(seed)
    probes: list[dict] = []
    for aspect in ASPECTS:
        for level in range(SCORE_TOP + 1):
            for k, fragment in enumerate(FRAGMENTS[aspect][level]):
                for tone in ("pos", "neg"):
                    wrapper = WRAPPERS[tone][(k + level + (tone == "neg")) % len(WRAPPERS[tone])]
                    text = f"{wrapper} {fragment}" if (k + level) % 2 == 0 else f"{fragment} {wrapper}"
                    probes.append({"id": f"w:{aspect}:{level}:{k}:{tone}", "kind": "wrapped", "text": text, "tone": tone, "aspect": aspect, "level": level, "fragment": f"{aspect}:{level}:{k}",
                                   "expect": {a: (level if a == aspect else None) for a in ASPECTS}})
    for tone in ("pos", "neg"):
        for i in range(10):
            first, second = rng.sample(WRAPPERS[tone], 2)
            probes.append({"id": f"c:{tone}:{i}", "kind": "control", "text": f"{first} {second}", "tone": tone, "expect": dict.fromkeys(ASPECTS)})
    for i in range(36):
        a, b = rng.sample(ASPECTS, 2)
        la, lb = rng.choice((0, 1)), rng.choice((3, 4))
        if i % 2:
            la, lb = lb, la
        fa, fb = rng.choice(FRAGMENTS[a][la]), rng.choice(FRAGMENTS[b][lb])
        text = f"{fa} {fb}" if i % 4 < 2 else f"{fb} {fa}"
        probes.append({"id": f"x:{i}", "kind": "cross", "text": text, "levels": {a: la, b: lb},
                       "expect": {x: ({a: la, b: lb}.get(x)) for x in ASPECTS}})
    return probes


def score_probes(client, probes: list[dict], workers: int = 6) -> list[dict]:
    from streetwalker.aspect_run import state_for
    from streetwalker.jev_client import ask

    questions = build_questions()

    def one(p: dict) -> dict:
        r = ask(client, state_for(p["text"]), questions)
        if r.error:
            return {**p, "error": r.error}
        got = {a["aspect"]: {"mentioned": a["mentioned"], "score": a["score"], "confidence": a["confidence"]} for a in parse_aspects({x.question: x for x in r.answers})}
        return {**p, "jev": got}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(one, probes))


def _boot_mean_diff(pairs: list[tuple[float, float]], n: int = 2000, seed: int = 0) -> tuple[float, float, float]:
    d = np.array([a - b for a, b in pairs])
    rng = np.random.default_rng(seed)
    boots = [float(rng.choice(d, len(d)).mean()) for _ in range(n)]
    return float(d.mean()), float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))


def evaluate(results: list[dict]) -> dict:
    ok = [r for r in results if "jev" in r]
    out: dict = {"n": len(results), "errors": len(results) - len(ok)}

    # 1. mention: the aspect a fragment is about should be mentioned, the other three should not
    mention: dict[str, dict[str, float]] = {}
    for a in ASPECTS:
        rows = [r for r in ok if r["kind"] in ("wrapped", "cross")]
        pos = [r for r in rows if r["expect"][a] is not None]
        neg = [r for r in rows if r["expect"][a] is None]
        mention[a] = {"recall": float(np.mean([r["jev"][a]["mentioned"] >= MENTION for r in pos])) if pos else float("nan"),
                      "false_mention": float(np.mean([r["jev"][a]["mentioned"] >= MENTION for r in neg])) if neg else float("nan"),
                      "n_pos": len(pos), "n_neg": len(neg)}
    out["mention"] = mention
    ctrl = [r for r in ok if r["kind"] == "control"]
    out["control_false_mention"] = float(np.mean([r["jev"][a]["mentioned"] >= MENTION for r in ctrl for a in ASPECTS])) if ctrl else float("nan")

    # 2. level: for the aspect a review is about, does the score match the known level?
    level: dict = {}
    own = [(r["aspect"], r["level"], r["jev"][r["aspect"]]["score"]) for r in ok if r["kind"] == "wrapped"]
    own += [(a, lv, r["jev"][a]["score"]) for r in ok if r["kind"] == "cross" for a, lv in r["levels"].items()]
    for a in ASPECTS:
        rows = [(lv, s) for aa, lv, s in own if aa == a]
        lv_arr, s_arr = np.array([x[0] for x in rows], float), np.array([x[1] for x in rows], float)
        level[a] = {"n": len(rows), "exact": float((np.rint(s_arr) == lv_arr).mean()), "within1": float((np.abs(s_arr - lv_arr) <= 1).mean()),
                    "mae": float(np.abs(s_arr - lv_arr).mean()), "bias": float((s_arr - lv_arr).mean()),
                    "by_level": {int(L): float(s_arr[lv_arr == L].mean()) for L in range(SCORE_TOP + 1) if (lv_arr == L).any()}}
    out["level"] = level

    # 3. halo: the same fragment with a positive and a negative wrapper
    by_fragment: dict[str, dict[str, float]] = defaultdict(dict)
    for r in ok:
        if r["kind"] == "wrapped":
            by_fragment[r["fragment"]][r["tone"]] = r["jev"][r["aspect"]]["score"]
    halo: dict = {}
    for a in ASPECTS:
        pairs = [(v["pos"], v["neg"]) for f, v in by_fragment.items() if f.startswith(a + ":") and len(v) == 2]
        mean, lo, hi = _boot_mean_diff(pairs)
        halo[a] = {"pairs": len(pairs), "gap": mean, "lo": lo, "hi": hi, "share_over_half_level": float(np.mean([abs(p - n) > 0.5 for p, n in pairs]))}
    allpairs = [(v["pos"], v["neg"]) for v in by_fragment.values() if len(v) == 2]
    mean, lo, hi = _boot_mean_diff(allpairs)
    halo["all"] = {"pairs": len(allpairs), "gap": mean, "lo": lo, "hi": hi, "share_over_half_level": float(np.mean([abs(p - n) > 0.5 for p, n in allpairs]))}
    out["halo"] = halo

    # 4. leakage between aspects in the cross reviews: the score of aspect A against A's own level and the other fragment's level
    xr = [r for r in ok if r["kind"] == "cross"]
    rows = []
    for r in xr:
        (a, la), (b, lb) = r["levels"].items()
        rows += [(r["jev"][a]["score"], la, lb), (r["jev"][b]["score"], lb, la)]
    if len(rows) >= 12:
        y = np.array([x[0] for x in rows])
        X = np.column_stack([np.ones(len(rows)), [x[1] for x in rows], [x[2] for x in rows]])
        coef = np.linalg.lstsq(X, y, rcond=None)[0]
        out["leakage"] = {"n": len(rows), "own_level": float(coef[1]), "other_aspect_level": float(coef[2])}
    return out


def fmt(x: float, spec: str = ".2f") -> str:
    return "n/a" if np.isnan(x) else format(x, spec)


def report(res: dict) -> None:
    print(f"{res['n']} invented reviews, {res['errors']} request errors")
    print("\nMention. For the aspect a sentence is about: how often Jev says it is mentioned (recall). For the other aspects: how often it says so wrongly.")
    for a, m in res["mention"].items():
        print(f"  {a:11s} recall {fmt(m['recall'], '.0%')} (n={m['n_pos']})   false mention {fmt(m['false_mention'], '.0%')} (n={m['n_neg']})")
    print(f"  control reviews (tone only, nothing about any aspect): false mention rate {fmt(res['control_false_mention'], '.1%')}")
    print("\nLevel. Jev's score against the known level (0 to 4) for the aspect each review is about")
    for a, v in res["level"].items():
        print(f"  {a:11s} n={v['n']:3d}  exact {fmt(v['exact'], '.0%')}  within 1 {fmt(v['within1'], '.0%')}  mean abs error {fmt(v['mae'])}  bias {fmt(v['bias'], '+.2f')}   mean score at level 0..4: "
              + " ".join(fmt(v['by_level'].get(L, float('nan'))) for L in range(SCORE_TOP + 1)))
    print("\nHalo. The same aspect sentence with a positive and a negative overall-tone sentence: positive minus negative score (0 = no halo)")
    for a, h in res["halo"].items():
        print(f"  {a:11s} {h['pairs']:3d} pairs  gap {fmt(h['gap'], '+.2f')} levels [{fmt(h['lo'], '+.2f')}, {fmt(h['hi'], '+.2f')}]   pairs differing by more than half a level: {fmt(h['share_over_half_level'], '.0%')}")
    if "leakage" in res:
        lk = res["leakage"]
        print(f"\nLeakage between aspects (cross reviews, n={lk['n']}). Weight on the aspect's own level {fmt(lk['own_level'])}, on the OTHER aspect's level {fmt(lk['other_aspect_level'], '+.2f')} (0 = none)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--save", help="write the raw results (invented text and Jev's answers) to this JSON file")
    ap.add_argument("--from", dest="source", help="evaluate saved results instead of calling Jev")
    ap.add_argument("--hard", help="also run the hand-picked hard cases and save them to this JSON file")
    args = ap.parse_args()
    if args.hard:
        from streetwalker.jev_client import make_client

        hard = score_hard(make_client())
        Path(args.hard).parent.mkdir(parents=True, exist_ok=True)
        Path(args.hard).write_text(json.dumps(hard, indent=1))
        report_hard(hard)
        return
    if args.source:
        results = json.loads(Path(args.source).read_text())
    else:
        from streetwalker.jev_client import make_client

        results = score_probes(make_client(), build_probes())
        if args.save:
            Path(args.save).parent.mkdir(parents=True, exist_ok=True)
            Path(args.save).write_text(json.dumps(results, indent=1))
            print(f"saved {len(results)} results to {args.save}")
    report(evaluate(results))


if __name__ == "__main__":
    main()
