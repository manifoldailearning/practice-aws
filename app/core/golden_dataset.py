"""Load the teaching golden dataset from ``data/golden_dataset.json``."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class GoldenCase:
    """One labeled example for regression-style checks."""

    id: str
    user_query: str
    expected_classification: str
    tags: list[str]


@dataclass(frozen=True)
class GoldenDataset:
    """Versioned bundle of golden cases."""

    version: str
    description: str
    cases: list[GoldenCase]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def golden_dataset_path() -> Path:
    """Path to ``data/golden_dataset.json`` at repository root."""
    return _repo_root() / "data" / "golden_dataset.json"


def load_golden_dataset(path: Path | None = None) -> GoldenDataset:
    """Parse and validate the golden dataset file."""
    p = path or golden_dataset_path()
    raw = json.loads(p.read_text(encoding="utf-8"))
    version = str(raw.get("version", "")).strip() or "0"
    description = str(raw.get("description", ""))
    cases_raw: list[dict[str, Any]] = list(raw.get("cases") or [])
    cases: list[GoldenCase] = []
    for i, row in enumerate(cases_raw):
        cid = str(row.get("id", "")).strip()
        q = str(row.get("user_query", "")).strip()
        exp = str(row.get("expected_classification", "")).strip()
        tags = list(row.get("tags") or [])
        if not cid or not q or not exp:
            raise ValueError(f"golden_dataset cases[{i}]: missing id, user_query, or expected_classification")
        if not isinstance(tags, list):
            raise ValueError(f"golden_dataset cases[{i}]: tags must be a list")
        cases.append(
            GoldenCase(
                id=cid,
                user_query=q,
                expected_classification=exp,
                tags=[str(t) for t in tags],
            )
        )
    return GoldenDataset(version=version, description=description, cases=cases)
