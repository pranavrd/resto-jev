"""Escalation cascade (decision 0018): Tier 0 answers everything, a gate picks who to escalate, later tiers resolve.

This module is the gate and the accounting. The pure functions take plain rows, so they are testable without a
database; `load_rows` and `main` bring in the stored predictions.

  Tier 0  stack-gbm over the evidence features and Jev's answers (decision 0011): calibrated D1 probabilities
  gate    escalate when the Tier 0 confidence is below tau
  Tier 1  street imagery, where an image exists (coverage limits what it can ever resolve)
  Tier 2  local LLM over the evidence text (experiment in scripts/tier2_local_llm.py)
  Tier 3  human review queue (review.py)

Protocol: gates and thresholds are chosen on train out-of-fold predictions only; dev validates them; the test split
is read once with --final and logged in docs/test-set-log.md.
Usage: .venv/bin/python -m streetwalker.cascade [--final]
"""

import argparse
import datetime as dt
import math
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from sklearn.metrics import roc_auc_score

from streetwalker import db
from streetwalker.bootstrap import grouped_bootstrap
from streetwalker.groundtruth import D1_CLASSES
from streetwalker.metrics import binary

COMM = frozenset({"commercial", "mixed-use"})
RATES = (0.05, 0.10, 0.15, 0.20, 0.30, 0.40)
INFORMATIVE_LEVELS = frozenset({"shop window or storefront", "entrance door with steps", "garage door", "plain wall"})
ACCEPT_BARS = (0.80, 0.90, 0.95)  # Tier 1 answers on its own only above its own confidence
TARGET_ACCURACIES = (0.90, 0.95, 0.97)  # accuracy wanted among the buildings Tier 0 keeps
OPERATING_TAU = 0.77  # the 95%-accuracy threshold chosen on train, rounded; Tier 1 and Tier 2 ran on this band
MIN_KEPT = 50  # a threshold must keep at least this many buildings, or its accuracy is noise
LOG = db.ROOT / "docs" / "test-set-log.md"


@dataclass(frozen=True)
class Row:
    building_id: int
    area: str
    split: str
    group: str  # street group, for the bootstrap
    truth: str  # D1 ground truth
    food: bool  # D3 ground truth
    probs: dict[str, float]  # stack-gbm D1 probabilities (the 7 classes only)
    food_prob: float
    jev_probs: dict[str, float]
    jev_conf: float
    lr_conf: float
    has_photo: bool  # some Mapillary image was picked for this building
    has_pano: bool  # a panorama pick exists, so a crop aimed at the building can be cut (decision 0013)
    t1: dict[str, float] | None = None  # Tier 1: Jev's D1 probabilities given the image caption (only where Tier 1 ran)
    t1_source: str | None = None
    t2: str | None = None  # Tier 2: the local LLM's D1 answer (only where Tier 2 ran, None when its reply named no class)
    t2_ran: bool = False
    t1_level: str | None = None  # what the caption says is at street level
    t1_sign: str | None = None  # the building's own sign text, when the caption read one
    status: str = "agree"  # ground-truth label status: agree | land_use_only | disputed (decision 0007)

    @property
    def t1_informative(self) -> bool:
        """The caption says something about the building: it read a sign, or saw a storefront, door, garage or wall.
        'not visible' and unparseable captions say nothing (and absence of a sign is not evidence of no business)."""
        return bool(self.t1_sign) or self.t1_level in INFORMATIVE_LEVELS

    @property
    def pred(self) -> str:
        return max(D1_CLASSES, key=lambda c: (self.probs[c], c))

    @property
    def conf(self) -> float:
        return self.probs[self.pred]

    @property
    def margin(self) -> float:
        top = sorted(self.probs[c] for c in D1_CLASSES)[-2:]
        return top[1] - top[0]

    @property
    def jev_pred(self) -> str:
        return max(D1_CLASSES, key=lambda c: (self.jev_probs[c], c))

    @property
    def correct(self) -> bool:
        return self.pred == self.truth

    @property
    def t1_pred(self) -> str | None:
        return max(D1_CLASSES, key=lambda c: (self.t1[c], c)) if self.t1 else None

    @property
    def t1_conf(self) -> float:
        return max(self.t1[c] for c in D1_CLASSES) if self.t1 else 0.0

    @property
    def mean_pred(self) -> str | None:
        """Untuned combination: the class with the highest mean of the Tier 0 and Tier 1 probabilities."""
        return max(D1_CLASSES, key=lambda c: ((self.probs[c] + self.t1[c]) / 2, c)) if self.t1 else None


# A gate scores each building; the highest scores are escalated first.
GATES: dict[str, Callable[[Row], float]] = {
    "stack-gbm confidence": lambda r: 1 - r.conf,
    "stack-gbm margin": lambda r: 1 - r.margin,
    "stack-lr confidence": lambda r: 1 - r.lr_conf,
    "Jev confidence": lambda r: 1 - r.jev_conf,
    "Jev and stack-gbm disagree": lambda r: float(r.jev_pred != r.pred) + (1 - r.conf) / 2,
}


def order_by(rows: Sequence[Row], gate: Callable[[Row], float]) -> list[Row]:
    """Most escalation-worthy first. Ties break on building id so the order is reproducible."""
    return sorted(rows, key=lambda r: (-gate(r), r.building_id))


def error_capture(rows: Sequence[Row], gate: Callable[[Row], float], rates: Sequence[float] = RATES) -> dict:
    """AUROC of the gate at ranking Tier 0's errors first, and the share of errors inside each escalation budget."""
    errors = [not r.correct for r in rows]
    scores = [gate(r) for r in rows]
    n_err = sum(errors)
    auroc = roc_auc_score(errors, scores) if 0 < n_err < len(rows) else float("nan")
    ordered = order_by(rows, gate)
    out = {"auroc": auroc, "errors": n_err, "n": len(rows), "capture": {}, "precision": {}}
    for rate in rates:
        k = round(rate * len(rows))
        caught = sum(not r.correct for r in ordered[:k])
        out["capture"][rate] = caught / n_err if n_err else float("nan")
        out["precision"][rate] = caught / k if k else float("nan")
    return out


def choose_tau(rows: Sequence[Row], target: float, min_kept: int = MIN_KEPT) -> float | None:
    """The smallest confidence threshold whose kept buildings (conf >= tau) are at least `target` accurate.

    Smallest, so the gate escalates as few buildings as possible while keeping the guarantee. Returns None when
    no threshold with at least `min_kept` kept buildings reaches the target."""
    ordered = sorted(rows, key=lambda r: -r.conf)
    correct = 0
    best: float | None = None
    for i, r in enumerate(ordered, 1):
        correct += r.correct
        nxt = ordered[i].conf if i < len(ordered) else None
        if nxt == r.conf:
            continue  # kept set must contain every building at this confidence
        if i >= min_kept and correct / i >= target:
            best = r.conf
    return best


@dataclass(frozen=True)
class Outcome:
    n: int
    escalated: int
    kept: int
    kept_accuracy: float
    accuracy_tier0: float  # D1 accuracy if nothing is escalated
    accuracy_final: float  # D1 accuracy when every escalated building is resolved by the human tier
    comm_f1_tier0: float
    comm_f1_final: float
    food_f1_tier0: float
    food_f1_final: float
    escalated_pano: int  # escalated buildings that have a verified-heading panorama crop
    escalated_photo: int  # escalated buildings that have any picked image (includes the panorama ones)


def at_threshold(rows: Sequence[Row], tau: float) -> Outcome:
    """Gate on conf < tau; the human tier is an oracle that returns the ground truth (see decision 0018)."""
    esc = [r for r in rows if r.conf < tau]
    kept = [r for r in rows if r.conf >= tau]
    n = len(rows)

    def f1(pred_comm: list[bool], truth_comm: list[bool]) -> float:
        return binary(truth_comm, pred_comm).f1

    truth_comm = [r.truth in COMM for r in rows]
    tier0_comm = [r.pred in COMM for r in rows]
    final_comm = [r.truth in COMM if r.conf < tau else r.pred in COMM for r in rows]
    truth_food = [r.food for r in rows]
    tier0_food = [r.food_prob >= 0.5 for r in rows]
    final_food = [r.food if r.conf < tau else r.food_prob >= 0.5 for r in rows]
    return Outcome(
        n=n, escalated=len(esc), kept=len(kept),
        kept_accuracy=sum(r.correct for r in kept) / len(kept) if kept else float("nan"),
        accuracy_tier0=sum(r.correct for r in rows) / n,
        accuracy_final=(len(esc) + sum(r.correct for r in kept)) / n,
        comm_f1_tier0=f1(tier0_comm, truth_comm), comm_f1_final=f1(final_comm, truth_comm),
        food_f1_tier0=f1(tier0_food, truth_food), food_f1_final=f1(final_food, truth_food),
        escalated_pano=sum(r.has_pano for r in esc), escalated_photo=sum(r.has_photo for r in esc),
    )


def human_reviews_needed(rows: Sequence[Row], gate: Callable[[Row], float], coverage: str | None = None) -> list[tuple[float, float, float]]:
    """(share escalated, D1 accuracy, share needing a human) along the gate order, escalating top-k for every k.

    With `coverage` set to "pano" or "photo", an escalated building that has that kind of image is resolved by a
    PERFECT imagery tier and does not reach the human queue. That is a ceiling for imagery, limited to the
    buildings where an image exists; it is not a measured tier."""
    ordered = order_by(rows, gate)
    n = len(rows)
    correct_kept = sum(r.correct for r in rows)
    out = [(0.0, correct_kept / n, 0.0)]
    humans = 0
    for k, r in enumerate(ordered, 1):
        correct_kept -= r.correct
        resolved_by_image = coverage == "pano" and r.has_pano or coverage == "photo" and r.has_photo
        humans += not resolved_by_image
        out.append((k / n, (k + correct_kept) / n, humans / n))
    return out


def humans_to_reach(points: list[tuple[float, float, float]], accuracy: float) -> float | None:
    """The smallest share of buildings reviewed by a human that reaches `accuracy`, or None if it never does."""
    for _share, acc, humans in points:
        if acc >= accuracy:
            return humans
    return None


@dataclass(frozen=True)
class CascadeRun:
    accuracy: float  # D1 accuracy of the final labels
    human_share: float  # share of all buildings that reach the human queue
    tier1_resolved: int  # escalated buildings Tier 1 answered on its own
    tier1_correct: int
    escalated: int


def full_cascade(rows: Sequence[Row], tau: float, accept_t1: float | None) -> CascadeRun:
    """Tier 0 keeps conf >= tau. An escalated building with a Tier 1 result is answered by Tier 1 when its confidence is at
    least `accept_t1` (None: never); every other escalated building goes to the human tier, an oracle that returns the truth."""
    right = humans = t1_done = t1_right = esc = 0
    for r in rows:
        if r.conf >= tau:
            right += r.correct
            continue
        esc += 1
        if accept_t1 is not None and r.t1 and r.t1_conf >= accept_t1:
            t1_done += 1
            t1_right += r.t1_pred == r.truth
            right += r.t1_pred == r.truth
        else:
            humans += 1
            right += 1
    return CascadeRun(right / len(rows), humans / len(rows), t1_done, t1_right, esc)


def paired_gain(rows: Sequence[Row], a: Callable[[Row], bool], b: Callable[[Row], bool]) -> tuple[float, float, float]:
    """Mean of (a - b) over rows with a 95% street-grouped interval."""
    def stat(sub: list[Row]) -> float:
        return sum(a(r) - b(r) for r in sub) / len(sub)

    lo, hi = grouped_bootstrap(rows, [r.group for r in rows], stat)
    return stat(list(rows)), lo, hi


def print_tier1(rows: Sequence[Row], tau: float, title: str) -> None:
    band = [r for r in rows if r.conf < tau]
    t1 = [r for r in band if r.t1]
    print(f"\nTier 1 (imagery) on the escalation band, {title}: {len(band)} escalated, {len(t1)} with a Tier 1 result "
          f"({len(t1) / len(band):.0%}); {len(band) - len(t1)} have no image")
    if len(t1) < 10:
        return
    by_src = Counter(r.t1_source for r in t1)
    print("  source: " + ", ".join(f"{k} {v}" for k, v in sorted(by_src.items())))
    print(f"  {'':34s} {'D1 acc':>7s}  {'commercial-any acc':>18s}")
    for name, pred in (("Tier 0 (stack-gbm)", lambda r: r.pred), ("Tier 1 alone (Jev + caption)", lambda r: r.t1_pred),
                       ("mean of Tier 0 and Tier 1", lambda r: r.mean_pred)):
        acc = sum(pred(r) == r.truth for r in t1) / len(t1)
        comm = sum((pred(r) in COMM) == (r.truth in COMM) for r in t1) / len(t1)
        print(f"  {name:34s} {acc:7.3f}  {comm:18.3f}")
    for name, f in (("Tier 1 alone", lambda r: r.t1_pred), ("mean of Tier 0 and Tier 1", lambda r: r.mean_pred)):
        d, lo, hi = paired_gain(t1, lambda r, f=f: f(r) == r.truth, lambda r: r.correct)
        print(f"  D1 accuracy, {name} minus Tier 0: {d:+.3f} [{lo:+.3f}, {hi:+.3f}]")
    for src in sorted(by_src):
        sub = [r for r in t1 if r.t1_source == src]
        print(f"  {src:18s} n={len(sub):3d}: Tier 0 {sum(r.correct for r in sub) / len(sub):.3f}, Tier 1 {sum(r.t1_pred == r.truth for r in sub) / len(sub):.3f}")
    info = [r for r in t1 if r.t1_informative]
    print(f"  Exploratory, defined after seeing the results above: only the {len(info)} buildings ({len(info) / len(t1):.0%}) whose caption says something "
          f"(a sign was read, or a storefront, door, garage or wall seen); the other {len(t1) - len(info)} captions say 'not visible' or nothing")
    if len(info) >= 10:
        d, lo, hi = paired_gain(info, lambda r: r.t1_pred == r.truth, lambda r: r.correct)
        print(f"    D1 accuracy: Tier 0 {sum(r.correct for r in info) / len(info):.3f}, Tier 1 {sum(r.t1_pred == r.truth for r in info) / len(info):.3f}; "
              f"Tier 1 minus Tier 0 {d:+.3f} [{lo:+.3f}, {hi:+.3f}]")
        comm0 = sum((r.pred in COMM) == (r.truth in COMM) for r in info) / len(info)
        comm1 = sum((r.t1_pred in COMM) == (r.truth in COMM) for r in info) / len(info)
        print(f"    commercial-any accuracy: Tier 0 {comm0:.3f}, Tier 1 {comm1:.3f}")
    blank = [r for r in t1 if not r.t1_informative]
    print(f"    on the {len(blank)} uninformative captions: Tier 0 {sum(r.correct for r in blank) / len(blank):.3f}, Tier 1 {sum(r.t1_pred == r.truth for r in blank) / len(blank):.3f}; "
          f"Tier 1 answers residential {sum(r.t1_pred == 'residential' for r in blank) / len(blank):.0%} of the time, Tier 0 {sum(r.pred == 'residential' for r in blank) / len(blank):.0%}")
    print("  Tier 1 as a resolver: accept its answer when its own confidence is at least c (the rest go on to the human tier)")
    print(f"  {'c':>5s} {'accepted':>9s} {'share of band':>14s} {'Tier 1 acc':>11s} {'Tier 0 acc, same':>17s}")
    for c in ACCEPT_BARS:
        acc = [r for r in t1 if r.t1_conf >= c]
        if acc:
            print(f"  {c:5.2f} {len(acc):9d} {len(acc) / len(band):13.1%} {sum(r.t1_pred == r.truth for r in acc) / len(acc):11.3f} "
                  f"{sum(r.correct for r in acc) / len(acc):17.3f}")


def print_tier2(rows: Sequence[Row], tau: float, title: str) -> None:
    band = [r for r in rows if r.conf < tau]
    t2 = [r for r in band if r.t2_ran]
    print(f"\nTier 2 (local LLM, text only) on the escalation band, {title}: {len(band)} escalated, {len(t2)} answered by Tier 2")
    if len(t2) < 10:
        return
    named = [r for r in t2 if r.t2]
    print(f"  replies naming a class: {len(named)}/{len(t2)}")
    print(f"  D1 accuracy on these buildings: Tier 0 {sum(r.correct for r in t2) / len(t2):.3f}, Tier 2 {sum(r.t2 == r.truth for r in t2) / len(t2):.3f}, "
          f"Jev alone {sum(r.jev_pred == r.truth for r in t2) / len(t2):.3f}")
    d, lo, hi = paired_gain(t2, lambda r: r.t2 == r.truth, lambda r: r.correct)
    print(f"  Tier 2 minus Tier 0: {d:+.3f} [{lo:+.3f}, {hi:+.3f}]")
    both = sum(r.t2 == r.truth and r.correct for r in t2)
    only2 = sum(r.t2 == r.truth and not r.correct for r in t2)
    only0 = sum(r.t2 != r.truth and r.correct for r in t2)
    print(f"  both right {both}, only Tier 2 right {only2}, only Tier 0 right {only0}, both wrong {len(t2) - both - only2 - only0}")
    agree = [r for r in t2 if r.t2 == r.pred]
    print(f"  Tier 2 agrees with Tier 0 on {len(agree)} ({len(agree) / len(t2):.0%}); accuracy there {sum(r.correct for r in agree) / len(agree):.3f}"
          if agree else "  Tier 2 never agrees with Tier 0")
    disagree = [r for r in t2 if r.t2 != r.pred]
    if disagree:
        print(f"  where they disagree ({len(disagree)}): Tier 0 right {sum(r.correct for r in disagree)}, Tier 2 right {sum(r.t2 == r.truth for r in disagree)}")


def print_by_area(train: Sequence[Row], dev: Sequence[Row], rest: Sequence[Row]) -> None:
    """The pooled threshold does not behave the same in every area, so show each. Rows: train + dev + test (if final)."""
    pooled = [*train, *dev, *rest]
    print(f"\nBy area at tau {OPERATING_TAU:.2f} (all splits pooled; train and dev predictions are out-of-fold)")
    print(f"  {'area':14s} {'n':>5s} {'Tier 0 acc':>11s} {'escalated':>10s} {'kept acc':>9s} {'final acc':>10s}  | area-specific tau for 95% (train) -> dev escalated / kept acc")
    for area in sorted({r.area for r in pooled}):
        sub = [r for r in pooled if r.area == area]
        o = at_threshold(sub, OPERATING_TAU)
        tr, dv = [r for r in train if r.area == area], [r for r in dev if r.area == area]
        tau = choose_tau(tr, 0.95, min_kept=30)
        if tau is None:
            local = "no threshold with at least 30 kept buildings reaches 95% on train"
        else:
            d = at_threshold(dv, tau)
            local = f"{tau:.2f} -> {d.escalated / d.n:5.1%} / {d.kept_accuracy:.3f} (n={d.n})"
        print(f"  {area:14s} {o.n:5d} {o.accuracy_tier0:11.3f} {o.escalated / o.n:10.1%} {o.kept_accuracy:9.3f} {o.accuracy_final:10.3f}  | {local}")
    rit = [r for r in pooled if r.area == "rittenhouse" and r.split in ("train", "dev")]
    print("  Rittenhouse, train + dev: accuracy by Tier 0 confidence (a calibrated model would match the second number to the first)")
    for lo, hi in ((0.0, 0.5), (0.5, 0.7), (0.7, 0.9), (0.9, 1.01)):
        sub = [r for r in rit if lo <= r.conf < hi]
        if sub:
            print(f"    confidence {lo:.1f} to {min(hi, 1.0):.1f}: n={len(sub):3d}  mean confidence {sum(r.conf for r in sub) / len(sub):.2f}  accuracy {sum(r.correct for r in sub) / len(sub):.2f}")


def print_by_label_status(rows: Sequence[Row]) -> None:
    """Some of Tier 0's errors are the ground truth's: where land use and OPA disagree, the label is the weak one."""
    errs = [r for r in rows if not r.correct]
    print(f"\nBy ground-truth label status (all splits pooled, {len(rows)} buildings, {len(errs)} Tier 0 errors)")
    print(f"  {'status':14s} {'n':>5s} {'Tier 0 error rate':>18s} {'escalated':>10s} {'share of all errors':>20s}")
    for st in ("agree", "land_use_only", "disputed"):
        sub = [r for r in rows if r.status == st]
        if sub:
            print(f"  {st:14s} {len(sub):5d} {sum(not r.correct for r in sub) / len(sub):18.3f} {sum(r.conf < OPERATING_TAU for r in sub) / len(sub):10.1%} "
                  f"{sum(not r.correct for r in sub) / len(errs):20.1%}")


def print_full_cascade(rows: Sequence[Row], tau: float, title: str) -> None:
    print(f"\nMeasured cascade at tau {tau:.2f} ({title}, {len(rows)} buildings): Tier 0, gate, Tier 1 where it is confident, human for the rest")
    print(f"  {'Tier 1 accepted at':>20s} {'D1 accuracy':>12s} {'human share':>12s} {'Tier 1 resolved':>16s} {'its accuracy':>13s}")
    for c in (None, *ACCEPT_BARS):
        run = full_cascade(rows, tau, c)
        label = "never (no imagery)" if c is None else f"confidence >= {c:.2f}"
        acc1 = f"{run.tier1_correct / run.tier1_resolved:.3f}" if run.tier1_resolved else "-"
        print(f"  {label:>20s} {run.accuracy:12.3f} {run.human_share:12.1%} {run.tier1_resolved:16d} {acc1:>13s}")


def print_costs(conn, rows: Sequence[Row], tau: float) -> None:
    """Measured per-building cost and time for each tier, and what that adds up to for the cascade."""
    jev = conn.execute("SELECT sum(est_cost_usd), sum(n_buildings) FROM jev_run WHERE purpose ILIKE '%%full%%' OR n_buildings > 3000").fetchone()
    lat = conn.execute("SELECT avg(latency_ms) FROM decision WHERE tier = 0 AND error IS NULL").fetchone()[0]
    t1 = conn.execute("SELECT avg(vlm_seconds), avg(jev_ms) FROM tier1_result WHERE error IS NULL").fetchone()
    t2 = conn.execute("SELECT avg(seconds) FROM tier2_result").fetchone()[0]
    human = conn.execute("SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY seconds) FROM human_label WHERE NOT undone AND seconds IS NOT NULL").fetchone()[0]
    n = len(rows)
    esc = [r for r in rows if r.conf < tau]
    with_img = [r for r in esc if r.has_photo or r.has_pano]
    print("\nCost and time per building (measured on this Mac and the Jev API; see decision 0018 for what is not measured)")
    tier0 = f"${float(jev[0]) / float(jev[1]):.5f}, Jev call {float(lat) / 1000:.1f} s" if jev and jev[0] and lat else "not recorded"
    print(f"  Tier 0  Jev + stacker, every building: {tier0}")
    if t1[0]:
        print(f"  Tier 1  caption {float(t1[0]):.1f} s (local VLM) + Jev {float(t1[1]) / 1000:.1f} s, only escalated buildings that have an image")
    if t2:
        print(f"  Tier 2  local LLM {float(t2):.1f} s, only escalated buildings")
    print("  Tier 3  human: " + (f"median {human:.0f} s per label (measured in the review queue)" if human else "not measured yet (no labels in the review queue)"))
    t1_s = float(t1[0] or 0) + float(t1[1] or 0) / 1000
    print(f"  At tau {tau:.2f}: {len(esc)}/{n} escalated ({len(esc) / n:.0%}), {len(with_img)} of them have an image. "
          f"Tier 1 for all of those would take {len(with_img) * t1_s / 60:.0f} min of compute; the human queue takes {len(esc)} reviews.")


def plot_curves(path: str, rows: Sequence[Row], tau_points: dict[float, float | None]) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    gate = GATES["stack-gbm confidence"]
    fig, (a, b) = plt.subplots(1, 2, figsize=(11, 4.4))
    for name, g in GATES.items():
        ordered = order_by(rows, g)
        errs = [not r.correct for r in ordered]
        total, caught, xs, ys = sum(errs), 0, [0.0], [0.0]
        for k, e in enumerate(errs, 1):
            caught += e
            xs.append(k / len(rows))
            ys.append(caught / total)
        b.plot(xs, ys, label=name, lw=2 if name == "stack-gbm confidence" else 1.2)
    b.plot([0, 1], [0, 1], "k:", lw=1, label="random order")
    b.set(xlim=(0, 0.6), ylim=(0, 1.02), xlabel="share of buildings escalated", ylabel="share of Tier 0 errors caught", title="Which buildings to escalate")
    b.legend(fontsize=8, loc="lower right")
    b.grid(alpha=0.25)

    for label, cov, style in (("no imagery", None, "-"), ("perfect imagery, panorama-covered only", "pano", "--"), ("perfect imagery, any picked photo", "photo", ":")):
        pts = human_reviews_needed(rows, gate, cov)
        a.plot([p[2] for p in pts], [p[1] for p in pts], style, label=label, lw=2)
    for c, marker in ((None, "o"), (0.9, "s")):
        pts = [full_cascade(rows, t, c) for t in sorted({t for t in tau_points.values() if t})]
        a.plot([p.human_share for p in pts], [p.accuracy for p in pts], marker, ms=7, label="measured cascade, no imagery" if c is None else "measured cascade, Tier 1 at confidence >= 0.9")
    a.set(xlim=(0, 0.45), ylim=(0.86, 1.005), xlabel="share of buildings reviewed by a person", ylabel="D1 accuracy of the final labels", title="Accuracy against human review")
    a.legend(fontsize=8, loc="lower right")
    a.grid(alpha=0.25)
    fig.suptitle(f"Escalation cascade, {len(rows):,} buildings (human tier = oracle: returns the parcel label)", fontsize=10)
    fig.tight_layout()
    fig.savefig(path, dpi=150)


def load_rows(conn, splits: Sequence[str]) -> list[Row]:
    sql = """
        SELECT g.building_id, a.slug, g.split, g.group_key, g.d1_class, g.d3_food,
               s.probs, j.probs, j.confidence, l.confidence,
               (ip.building_id IS NOT NULL), (pp.building_id IS NOT NULL), t1.d1, t1.source, t2.answer, (t2.building_id IS NOT NULL),
               t1.street_level, t1.own_sign, g.label_status
        FROM ground_truth g
        JOIN building b ON b.id = g.building_id JOIN area a ON a.id = b.area_id
        JOIN baseline_prediction s ON s.building_id = g.building_id AND s.baseline = 'stack-gbm'
        JOIN baseline_prediction j ON j.building_id = g.building_id AND j.baseline = 'jev-p1'
        JOIN baseline_prediction l ON l.building_id = g.building_id AND l.baseline = 'stack-lr'
        LEFT JOIN image_pick ip ON ip.building_id = g.building_id
        LEFT JOIN pano_pick pp ON pp.building_id = g.building_id
        LEFT JOIN tier1_result t1 ON t1.building_id = g.building_id AND t1.error IS NULL
        LEFT JOIN tier2_result t2 ON t2.building_id = g.building_id
        WHERE g.split = ANY(%s) ORDER BY g.building_id"""
    rows = []
    for bid, area, split, group, truth, food, sp, jp, jc, lc, photo, pano, t1, t1_src, t2, t2_ran, t1_level, t1_sign, status in conn.execute(sql, [list(splits)]).fetchall():
        rows.append(Row(
            bid, area, split, group, truth, bool(food), {c: sp[c] for c in D1_CLASSES}, sp["food"],
            {c: jp[c] for c in D1_CLASSES}, jc, lc, photo, pano,
            {c: t1[c] for c in D1_CLASSES} if t1 else None, t1_src, t2, t2_ran, t1_level, t1_sign, status,
        ))
    return rows


def pct(x: float) -> str:
    return "    -" if math.isnan(x) else f"{x * 100:5.1f}%"


def print_gates(split_rows: dict[str, list[Row]]) -> None:
    print("Gate quality: AUROC at ranking Tier 0's (stack-gbm) errors first, and the share of its errors inside each budget")
    head = "  ".join(f"{int(r * 100):>3d}% esc" for r in RATES)
    for split, rows in split_rows.items():
        errs = sum(not r.correct for r in rows)
        print(f"\n  {split}: {len(rows)} buildings, Tier 0 accuracy {sum(r.correct for r in rows) / len(rows):.3f}, {errs} errors")
        print(f"    {'gate':30s} {'AUROC':>6s}   {head}")
        for name, gate in GATES.items():
            c = error_capture(rows, gate)
            print(f"    {name:30s} {c['auroc']:6.3f}   " + "  ".join(f"{c['capture'][r] * 100:7.0f}%" for r in RATES))
        print(f"    {'random order':30s} {0.5:6.3f}   " + "  ".join(f"{r * 100:7.0f}%" for r in RATES))


def print_operating_points(taus: dict[float, float | None], split_rows: dict[str, list[Row]], with_ci: set[str]) -> None:
    print("\nOperating points: tau chosen on train out-of-fold predictions for a target accuracy among kept buildings")
    print(f"  {'target':>6s} {'tau':>5s} {'split':>5s} {'n':>5s} {'escalated':>10s} {'kept acc':>9s} {'D1 acc':>7s} -> {'final':>6s} "
          f"{'comm F1':>8s} -> {'final':>6s} {'food F1':>8s} -> {'final':>6s}  with pano / any photo")
    for target, tau in taus.items():
        if tau is None:
            print(f"  {target:6.2f}   no threshold reaches this on train")
            continue
        for split, rows in split_rows.items():
            o = at_threshold(rows, tau)
            print(f"  {target:6.2f} {tau:5.2f} {split:>5s} {o.n:5d} {o.escalated:5d} {pct(o.escalated / o.n)} {pct(o.kept_accuracy)}  "
                  f"{o.accuracy_tier0:6.3f} -> {o.accuracy_final:5.3f}  {o.comm_f1_tier0:7.2f} -> {o.comm_f1_final:5.2f} "
                  f" {o.food_f1_tier0:7.2f} -> {o.food_f1_final:5.2f}   {o.escalated_pano:3d} / {o.escalated_photo:3d}")
            if split in with_ci:
                lo, hi = grouped_bootstrap(rows, [r.group for r in rows], lambda s, t=tau: at_threshold(s, t).escalated / len(s))
                klo, khi = grouped_bootstrap(rows, [r.group for r in rows], lambda s, t=tau: at_threshold(s, t).kept_accuracy)
                print(f"{'':37s}95% CI (street-grouped): escalated [{lo * 100:.1f}%, {hi * 100:.1f}%], kept accuracy [{klo * 100:.1f}%, {khi * 100:.1f}%]")


def print_human_load(rows: list[Row], gate: Callable[[Row], float], title: str) -> None:
    print(f"\nHuman reviews needed to reach an accuracy ({title}, gate = stack-gbm confidence; escalated buildings "
          "resolved by an oracle)")
    curves = {"no imagery": human_reviews_needed(rows, gate), "perfect imagery on panorama-covered": human_reviews_needed(rows, gate, "pano"),
              "perfect imagery on any picked photo": human_reviews_needed(rows, gate, "photo")}
    print(f"  {'target D1 accuracy':20s} " + " ".join(f"{k:>38s}" for k in curves))
    for acc in (0.90, 0.92, 0.94, 0.96, 0.98, 1.00):
        cells = []
        for pts in curves.values():
            h = humans_to_reach(pts, acc)
            cells.append(f"{pct(h) if h is not None else 'unreachable':>38s}")
        print(f"  {acc:20.2f} " + " ".join(cells))


def log_test_access(note: str) -> None:
    stamp = dt.datetime.now(dt.UTC).strftime("%Y-%m-%d %H:%M UTC")
    with LOG.open("a") as f:
        f.write(f"| {stamp} | {note} | test | all areas | all |\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--final", action="store_true", help="include the frozen test split (logged)")
    ap.add_argument("--figure", help="write the headline figure to this path (needs matplotlib)")
    args = ap.parse_args()
    with db.connect() as conn:
        train, dev = load_rows(conn, ("train",)), load_rows(conn, ("dev",))
        test = load_rows(conn, ("test",)) if args.final else []
        taus = {t: choose_tau(train, t) for t in TARGET_ACCURACIES}
        if taus[0.95] is None or abs(taus[0.95] - OPERATING_TAU) > 0.01:
            print(f"warning: the 95% threshold chosen on train is {taus[0.95]}, not {OPERATING_TAU}; Tier 1 and Tier 2 ran on the {OPERATING_TAU} band")
        development = train + dev
        splits = {"train": train, "dev": dev} | ({"test": test} if args.final else {})
        print_gates(splits)
        print_operating_points(taus, splits, with_ci={"dev"} | ({"test"} if args.final else set()))
        print_human_load(development + test, GATES["stack-gbm confidence"], "train+dev" + ("+test" if args.final else ""))
        for title, rows in [("train + dev", development)] + ([("test, final", test)] if args.final else []):
            print(f"\n{'=' * 8} {title} {'=' * 8}")
            print_tier1(rows, OPERATING_TAU, title)
            print_tier2(rows, OPERATING_TAU, title)
            print_full_cascade(rows, OPERATING_TAU, title)
        print_by_area(train, dev, test)
        print_by_label_status(development + test)
        print_costs(conn, development + test, OPERATING_TAU)
    if args.figure:
        plot_curves(args.figure, development + test, taus)
        print(f"\nfigure written to {args.figure}")
    if args.final:
        log_test_access(f"cascade: gate, thresholds chosen on train; Tier 1, Tier 2 and full cascade at tau {OPERATING_TAU}")
        print("\nlogged a test-split access in docs/test-set-log.md")


if __name__ == "__main__":
    main()
