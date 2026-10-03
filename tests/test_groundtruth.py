import pytest

from streetwalker.groundtruth import (
    D1_CLASSES,
    LAND_USE_C2,
    OPA_CLASS,
    assign_splits,
    label_status,
    land_use_class,
    opa_class,
)


@pytest.mark.parametrize(
    ("c1", "c2", "expected"),
    [
        (1, 12, "residential"), (1, 11, "residential"), (2, 21, "commercial"), (2, 22, "commercial"),
        (2, 23, "mixed-use"), (3, 31, "industrial"), (4, 41, "civic-institutional"), (6, 61, "civic-institutional"),
        (9, 91, "vacant"), (5, 51, "other"), (9, 92, "other"),
        (2, None, "commercial"),  # falls back to the first digit
        (7, None, "other"), (None, None, "other"),
    ],
)
def test_land_use_class(c1, c2, expected):
    assert land_use_class(c1, c2) == expected


def test_every_mapping_lands_in_a_known_class():
    assert set(LAND_USE_C2.values()) <= set(D1_CLASSES)
    assert set(OPA_CLASS.values()) <= set(D1_CLASSES)


def test_opa_class_handles_unknown_and_missing():
    assert opa_class("MIXED USE") == "mixed-use"
    assert opa_class("APARTMENTS  > 4 UNITS") == "residential"
    assert opa_class(None) is None
    assert opa_class("SOMETHING NEW") is None


def test_label_status():
    assert label_status("residential", "residential") == "agree"
    assert label_status("civic-institutional", "commercial") == "disputed"
    assert label_status("residential", None) == "land_use_only"


def _groups(n_per_area=40):
    return {f"{area}|street {i}": (area, float(1 + (i * 7) % 11)) for area in ("a", "b") for i in range(n_per_area)}


def test_assign_splits_is_deterministic_and_balanced_within_each_area():
    groups = _groups()
    first = assign_splits(groups)
    assert first == assign_splits(groups)
    for area in ("a", "b"):
        weight = {s: 0.0 for s in ("train", "dev", "test")}
        for key, (ar, w) in groups.items():
            if ar == area:
                weight[first[key]] += w
        total = sum(weight.values())
        assert weight["train"] / total == pytest.approx(0.6, abs=0.06)
        assert weight["dev"] / total == pytest.approx(0.2, abs=0.06)
        assert weight["test"] / total == pytest.approx(0.2, abs=0.06)


def test_a_few_huge_groups_still_populate_every_split():
    groups = {"x|big1": ("x", 100.0), "x|big2": ("x", 90.0), "x|big3": ("x", 80.0), "x|s1": ("x", 5.0), "x|s2": ("x", 4.0)}
    assigned = assign_splits(groups)
    assert set(assigned.values()) == {"train", "dev", "test"}


def test_frozen_assignments_never_move_and_new_groups_fill_gaps():
    groups = _groups()
    first = assign_splits(groups)
    frozen = {k: first[k] for k in list(first)[:30]}
    again = assign_splits({**groups, "a|brand new street": ("a", 6.0)}, frozen)
    assert all(again[k] == v for k, v in frozen.items())
    assert again["a|brand new street"] in ("train", "dev", "test")
