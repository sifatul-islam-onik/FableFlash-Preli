"""GET /health — readiness endpoint."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health():
    """Return service health status.

    The judge harness calls this to confirm readiness
    before sending test cases. Must respond within 60s of service start.
    """
    return {"status": "ok"}
