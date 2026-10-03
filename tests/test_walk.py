from collections import Counter
from itertools import pairwise

import pytest

from streetwalker.walk import StreetEdge, is_service, is_street, plan_walk


def xy(n: int) -> dict[int, tuple[float, float]]:
    """Nodes 1..n laid out west to east, ~85 m apart (so jumps have real lengths)."""
    return {i: (-75.17 + i * 0.001, 39.95) for i in range(1, n + 1)}


def check_valid(edges, plan):
    """Every segment walked, one non-repeat pass each, passes connected within a component."""
    passes = Counter(s.edge_idx for s in plan.steps)
    assert set(passes) == set(range(len(edges)))
    firsts = Counter(s.edge_idx for s in plan.steps if not s.is_repeat)
    assert all(firsts[i] == 1 for i in range(len(edges)))
    by_comp: dict[int, list] = {}
    for s in plan.steps:
        by_comp.setdefault(s.component, []).append(s)
    for steps in by_comp.values():
        for a, b in pairwise(steps):
            assert a.v == b.u
        assert steps[0].u == steps[-1].v  # closed circuit
    assert [s.seq for s in plan.steps] == list(range(len(plan.steps)))


def test_even_cycle_has_no_repeats():
    edges = [StreetEdge(1, 2, 0, 100), StreetEdge(2, 3, 0, 100), StreetEdge(3, 4, 0, 100), StreetEdge(4, 1, 0, 100)]
    plan = plan_walk(edges, xy(4))
    check_valid(edges, plan)
    assert plan.walked_m == pytest.approx(400)
    assert plan.repeat_m == pytest.approx(0)
    assert plan.n_components == 1 and plan.n_jumps == 0


def test_dead_end_spur_is_walked_twice():
    edges = [
        StreetEdge(1, 2, 0, 100), StreetEdge(2, 3, 0, 100), StreetEdge(3, 4, 0, 100), StreetEdge(4, 1, 0, 100),
        StreetEdge(4, 5, 0, 40),  # spur
    ]
    plan = plan_walk(edges, xy(5))
    check_valid(edges, plan)
    assert plan.repeat_m == pytest.approx(40)
    assert sum(s.is_repeat for s in plan.steps) == 1


def test_path_must_be_retraced():
    edges = [StreetEdge(1, 2, 0, 50), StreetEdge(2, 3, 0, 60), StreetEdge(3, 4, 0, 70)]
    plan = plan_walk(edges, xy(4))
    check_valid(edges, plan)
    assert plan.walked_m == pytest.approx(2 * 180)


def test_matching_minimises_repeated_metres():
    # Two odd nodes (1 and 4) joined by a short 2-hop route (20 m) and a long 1-hop route (500 m).
    edges = [
        StreetEdge(1, 2, 0, 10), StreetEdge(2, 4, 0, 10), StreetEdge(1, 4, 0, 500),
        StreetEdge(1, 5, 0, 100), StreetEdge(5, 4, 0, 100),  # 1 and 4 now have degree 3
    ]
    plan = plan_walk(edges, xy(5))
    check_valid(edges, plan)
    assert plan.repeat_m == pytest.approx(20)  # not the 500 m single hop


def test_parallel_edges_and_self_loop():
    edges = [StreetEdge(1, 2, 0, 80), StreetEdge(1, 2, 1, 90), StreetEdge(2, 2, 0, 30), StreetEdge(2, 3, 0, 50)]
    plan = plan_walk(edges, xy(3))
    check_valid(edges, plan)
    assert plan.repeat_m == pytest.approx(50)  # only the 2-3 spur is retraced


def test_disconnected_components_are_jumped_between():
    edges = [
        StreetEdge(1, 2, 0, 100), StreetEdge(2, 3, 0, 100), StreetEdge(3, 1, 0, 100),
        StreetEdge(7, 8, 0, 100), StreetEdge(8, 9, 0, 100), StreetEdge(9, 7, 0, 100),
    ]
    plan = plan_walk(edges, xy(9))
    check_valid(edges, plan)
    assert plan.n_components == 2 and plan.n_jumps == 1
    assert sum(s.is_jump for s in plan.steps) == 1
    assert plan.jump_m > 0


def test_plan_is_deterministic():
    edges = [StreetEdge(1, 2, 0, 100), StreetEdge(2, 3, 0, 100), StreetEdge(3, 4, 0, 100), StreetEdge(4, 1, 0, 100),
             StreetEdge(2, 4, 0, 140)]
    a, b = plan_walk(edges, xy(4)), plan_walk(edges, xy(4))
    assert [(s.u, s.v, s.edge_idx) for s in a.steps] == [(s.u, s.v, s.edge_idx) for s in b.steps]


def test_never_longer_than_naive_baseline():
    edges = [StreetEdge(1, 2, 0, 10), StreetEdge(2, 4, 0, 10), StreetEdge(1, 4, 0, 500),
             StreetEdge(1, 5, 0, 100), StreetEdge(5, 4, 0, 100)]
    plan = plan_walk(edges, xy(5))
    assert plan.walked_m <= plan.naive_walked_m + 1e-9


@pytest.mark.parametrize(
    ("highway", "expected"),
    [("residential", True), ("service", True), ("primary", True), ("footway", False), ("path", False),
     ('["footway", "steps"]', False), ('["secondary", "service"]', True), ('["service", "footway"]', True),
     (None, False)],
)
def test_is_street(highway, expected):
    assert is_street(highway) is expected


@pytest.mark.parametrize(
    ("highway", "expected"),
    [("service", True), ("residential", False), ('["service", "footway"]', True), ('["secondary", "service"]', False),
     ("footway", False), (None, False)],
)
def test_is_service(highway, expected):
    assert is_service(highway) is expected
