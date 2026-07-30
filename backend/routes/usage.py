"""Read-only view of the month-to-date model spend."""

from fastapi import APIRouter

from services.usage import month_to_date

router = APIRouter()


@router.get("/usage")
async def get_usage():
    """Month-to-date totals grouped by purpose, model, route, and origin.

    unpriced_calls is reported rather than folded into the total so an
    unknown model shows as a gap instead of an understated bill.
    """
    return month_to_date()
