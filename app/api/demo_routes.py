"""Teaching-only routes: golden dataset listing (no side effects)."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.schemas import GoldenCaseItem, GoldenDatasetResponse
from app.core.golden_dataset import load_golden_dataset

router = APIRouter(tags=["demo"])


@router.get("/golden-dataset", response_model=GoldenDatasetResponse)
async def get_golden_dataset() -> GoldenDatasetResponse:
    """Return the curated golden dataset for class demos and pytest-backed checks."""
    ds = load_golden_dataset()
    return GoldenDatasetResponse(
        version=ds.version,
        description=ds.description,
        cases=[
            GoldenCaseItem(
                id=c.id,
                user_query=c.user_query,
                expected_classification=c.expected_classification,
                tags=c.tags,
            )
            for c in ds.cases
        ],
    )
