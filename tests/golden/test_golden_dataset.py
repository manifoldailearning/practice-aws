"""Golden dataset file integrity and API surface."""

from __future__ import annotations

from app.core.golden_dataset import load_golden_dataset


def test_golden_dataset_loads() -> None:
    ds = load_golden_dataset()
    assert ds.version
    assert len(ds.cases) >= 1
    first = ds.cases[0]
    assert first.id
    assert first.user_query
    assert first.expected_classification


def test_golden_case_ids_unique() -> None:
    ds = load_golden_dataset()
    ids = [c.id for c in ds.cases]
    assert len(ids) == len(set(ids))
