"""FastAPI application entry point for QueueStorm Investigator."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.config import settings
from app.routers.health import router as health_router
from app.routers.analyze import router as analyze_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Log configuration on startup."""
    logger.info("QueueStorm Investigator starting up...")
    logger.info(f"Groq model: {settings.GROQ_MODEL}")
    logger.info(f"Groq API keys configured: {len(settings.groq_keys)}")
    if not settings.has_groq_keys:
        logger.warning(
            "No Groq API keys configured! "
            "The service will use rule-based fallback for all requests."
        )
    logger.info("Service ready.")
    yield
    logger.info("QueueStorm Investigator shutting down...")


# Create FastAPI app
app = FastAPI(
    title="QueueStorm Investigator",
    description="AI/API copilot for digital finance customer support",
    version="1.0.0",
    lifespan=lifespan,
)

# Include routers
app.include_router(health_router)
app.include_router(analyze_router)


# --- Global exception handlers ---

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
):
    """Handle Pydantic validation errors → 422 or 400."""
    errors = exc.errors()
    # Check if it's a missing required field → 400
    for error in errors:
        if error.get("type") in ("missing", "json_invalid"):
            return JSONResponse(
                status_code=400,
                content={
                    "error": "Malformed input",
                    "detail": "Invalid JSON or missing required fields.",
                },
            )

    # Otherwise → 422
    safe_errors = []
    for error in errors:
        safe_errors.append({
            "field": ".".join(str(loc) for loc in error.get("loc", [])),
            "message": error.get("msg", "Invalid value"),
        })

    return JSONResponse(
        status_code=422,
        content={
            "error": "Validation error",
            "detail": safe_errors,
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Catch-all handler to prevent process crashes.

    Returns 500 with safe message — no stack traces or secrets.
    """
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": "An unexpected error occurred. Please try again.",
        },
    )


