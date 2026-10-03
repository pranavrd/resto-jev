"""Calibration of confidence scores: reliability bins and expected calibration error (ECE).

Used for every probabilistic classifier (GBM now, Jev next), so the numbers are comparable.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Bin:
    lo: float
    hi: float
    n: int
    mean_confidence: float
    accuracy: float


def reliability_bins(confidence: list[float], correct: list[bool], n_bins: int = 10) -> list[Bin]:
    """Equal-width bins over [0, 1]. Empty bins are omitted."""
    out = []
    for i in range(n_bins):
        lo, hi = i / n_bins, (i + 1) / n_bins
        idx = [j for j, c in enumerate(confidence) if (lo <= c < hi) or (i == n_bins - 1 and c == 1.0)]
        if idx:
            out.append(Bin(
                lo, hi, len(idx),
                sum(confidence[j] for j in idx) / len(idx),
                sum(correct[j] for j in idx) / len(idx),
            ))
    return out


def ece(confidence: list[float], correct: list[bool], n_bins: int = 10) -> float:
    """Expected calibration error: the count-weighted gap between confidence and accuracy per bin."""
    n = len(confidence)
    if n == 0:
        return 0.0
    return sum(b.n / n * abs(b.mean_confidence - b.accuracy) for b in reliability_bins(confidence, correct, n_bins))
