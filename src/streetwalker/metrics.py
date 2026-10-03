"""Classification metrics with no dependencies, so every number in the write-up is reproducible."""

import math
from collections import Counter
from dataclasses import dataclass


@dataclass(frozen=True)
class ClassStats:
    label: str
    support: int  # true count
    predicted: int
    precision: float
    recall: float
    f1: float


def confusion(truth: list[str], pred: list[str]) -> Counter:
    return Counter(zip(truth, pred, strict=True))


def per_class(truth: list[str], pred: list[str], labels: list[str]) -> list[ClassStats]:
    cm = confusion(truth, pred)
    out = []
    for lab in labels:
        tp = cm[(lab, lab)]
        support = sum(n for (t, _), n in cm.items() if t == lab)
        predicted = sum(n for (_, p), n in cm.items() if p == lab)
        prec = tp / predicted if predicted else 0.0
        rec = tp / support if support else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        out.append(ClassStats(lab, support, predicted, prec, rec, f1))
    return out


def accuracy(truth: list[str], pred: list[str]) -> float:
    return sum(t == p for t, p in zip(truth, pred, strict=True)) / len(truth) if truth else 0.0


def macro_f1(stats: list[ClassStats]) -> float:
    present = [s for s in stats if s.support > 0]
    return sum(s.f1 for s in present) / len(present) if present else 0.0


def binary(truth: list[bool], pred: list[bool]) -> ClassStats:
    """Precision, recall and F1 of the positive class."""
    t = ["pos" if x else "neg" for x in truth]
    p = ["pos" if x else "neg" for x in pred]
    return per_class(t, p, ["pos"])[0]


def multiclass_log_loss(truth: list[str], probs: list[list[float]], classes: tuple[str, ...] | list[str]) -> float:
    """Mean negative log probability of the true class. Columns of `probs` follow `classes` in the order
    given (sklearn's log_loss silently assumes sorted order, which misaligns custom class orders)."""
    index = {c: i for i, c in enumerate(classes)}
    return -sum(math.log(max(row[index[t]], 1e-15)) for t, row in zip(truth, probs, strict=True)) / len(truth)
