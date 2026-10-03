"""Street-grouped bootstrap: resample whole street groups, not buildings.

Buildings on one street are not independent (they share context, owners, data quality), so a plain
building-level bootstrap gives intervals that are too narrow. Resampling groups keeps that dependence.
"""

import random
from collections.abc import Callable, Sequence


def grouped_bootstrap[Row](
    rows: Sequence[Row], groups: Sequence[str], stat: Callable[[list[Row]], float], n: int = 1000, seed: int = 0
) -> tuple[float, float]:
    """95% percentile interval of `stat` over group resamples."""
    by_group: dict[str, list[Row]] = {}
    for r, g in zip(rows, groups, strict=True):
        by_group.setdefault(g, []).append(r)
    keys = sorted(by_group)
    rng = random.Random(seed)
    stats = []
    for _ in range(n):
        sample: list[Row] = []
        for k in (rng.choice(keys) for _ in keys):
            sample.extend(by_group[k])
        stats.append(stat(sample))
    stats.sort()
    return stats[int(0.025 * n)], stats[min(n - 1, int(0.975 * n))]
