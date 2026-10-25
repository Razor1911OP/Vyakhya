"""
Vyakhya FastAPI Application
Main entry point for the risk API
"""
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import time

from backend.app.core.config import settings
from backend.app.core.logging import setup_logging, get_logger
from backend.app.schemas import ScoreRequest, ScoreResponse
from backend.app.risk_adapter import get_risk_engine, score_request

# Setup logging
setup_logging(log_level="INFO")
logger = get_logger(__name__)

# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="AI-driven scam pattern recognition for UPI payments"
)

# CORS middleware (development - tighten for production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],  # Vite default ports
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize detection engine on startup
@app.on_event("startup")
async def startup_event():
    """Warm up models on startup"""
    logger.info(f"Starting {settings.app_name} v{settings.app_version}")
    logger.info(f"Environment: {settings.environment}")
    
    # Pre-load detection engine (warms up all models)
    try:
        get_risk_engine()
        logger.info("Frozen risk engine loaded from model registry")
    except Exception as e:
        logger.error(f"Failed to initialize detection engine: {e}")
        raise


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info(f"Shutting down {settings.app_name}")


# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all requests with timing"""
    start_time = time.perf_counter()
    
    # Process request
    response = await call_next(request)
    
    # Calculate latency
    latency_ms = int((time.perf_counter() - start_time) * 1000)
    
    # Log
    logger.info(f"{request.method} {request.url.path}", extra={
        'method': request.method,
        'path': request.url.path,
        'status_code': response.status_code,
        'latency_ms': latency_ms
    })
    
    return response


@app.get("/")
async def root():
    """Root endpoint - API info"""
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "tagline": "The scam went AI-native. The payment still looks legitimate.",
        "status": "operational"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        get_risk_engine()
        models_loaded = True
    except:
        models_loaded = False
    
    return {
        "status": "healthy" if models_loaded else "degraded",
        "models_loaded": models_loaded,
        "environment": settings.environment
    }


@app.post(f"{settings.api_prefix}/score", response_model=ScoreResponse)
async def score_payment(request: ScoreRequest):
    """
    Score a payment request for fraud risk
    
    **Latency budget: < 300ms p95**
    
    Returns:
    - risk_score: Calibrated risk score R ∈ [0, 100]
    - tier: LOW | MEDIUM | HIGH | CRITICAL
    - soft_hold: Whether payment should be held before debit
    - reason_codes: Plain-language explanations (explainability is the product identity)
    - friction_type: UI friction pattern to apply
    
    **Privacy guarantee:**
    - Raw message text is never stored or logged
    - Only redacted, minimized text is processed
    - All decisions are auditable without exposing PII
    """
    try:
        return score_request(request)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    
    except Exception as e:
        logger.error(f"Scoring failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Internal error during risk scoring. Payment was not processed."
        )


@app.get(f"{settings.api_prefix}/model-info")
async def get_model_info():
    """Get information about loaded models"""
    try:
        import json
        from risk import config as RC
        get_risk_engine()
        cfg = json.loads((RC.ARTIFACT_DIR / "config.json").read_text(encoding="utf-8"))
        return {**cfg, "tier_policy": "band low/medium/high -> LOW/MEDIUM/HIGH; hard-rule hit -> CRITICAL + soft_hold",
                "latency_budget_ms": settings.score_latency_budget_ms}
    
    except Exception as e:
        logger.error(f"Failed to get model info: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve model information")


# Error handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "status_code": exc.status_code
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "status_code": 500
        }
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.environment == "development"
    )
