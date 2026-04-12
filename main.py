# main.py — VIT Sports Intelligence Network v3.0.0
# Refactored to use dependency injection for core services.

import os
import uuid
from dotenv import load_dotenv
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import get_env, APP_VERSION
from app.db.database import engine, Base, get_db, _is_sqlite
from app.api.routes import predict, result, history, admin
from app.api.routes import training as training_route
from app.api.routes import analytics as analytics_route
from app.api.routes import odds_compare as odds_route
from app.api.middleware.auth import APIKeyMiddleware
from app.api.middleware.logging import LoggingMiddleware
from app.schemas.schemas import HealthResponse
from app.services.alerts import TelegramAlert
from app.core.dependencies import (
    get_orchestrator,
    get_orchestrator_dep,
    get_data_loader,
    get_data_loader_dep,
    get_telegram_alerts,
)

load_dotenv()


async def _check_db_connection() -> bool:
    try:
        async for session in get_db():
            await session.execute(select(1))
            return True
    except Exception as e:
        print(f"❌ DB Connection Check Failed: {e}")
        return False


async def fetch_and_predict(competition: str, days_ahead: int = 7):
    data_loader = get_data_loader()
    orchestrator = get_orchestrator()

    if not data_loader or not orchestrator:
        print("❌ Data loader or orchestrator not initialized")
        return

    try:
        print(f"\n📡 Fetching data for {competition}...")
        context = await data_loader.fetch_all_context(
            competition=competition,
            days_ahead=days_ahead,
            include_recent_form=True,
            include_h2h=True,
            include_odds=True,
        )
        print(f"   ✅ Fetched {len(context.fixtures)} fixtures")
        for fixture in context.fixtures:
            try:
                features = {
                    "home_team":   fixture["home_team"]["name"],
                    "away_team":   fixture["away_team"]["name"],
                    "league":      competition,
                    "market_odds": fixture.get("odds", {}),
                }
                await orchestrator.predict(features, str(fixture.get("external_id", "")))
            except Exception as e:
                print(f"   ⚠️ Prediction failed: {e}")
    except Exception as e:
        print(f"❌ Fetch failed: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"\n🚀 VIT Sports Intelligence Network v{APP_VERSION} — Starting...")

    print("\n🗄️ Initializing database...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("   ✅ Database ready")

    orchestrator = get_orchestrator()
    if orchestrator:
        print(f"   ✅ ML Orchestrator ready: {orchestrator.num_models_ready()} models")

    alerts = get_telegram_alerts()
    if alerts and alerts.enabled:
        try:
            await alerts.send_startup_message()
            print("   ✅ Telegram Alerts: ENABLED")
        except Exception as e:
            print(f"   ⚠️ Telegram startup failed: {e}")
    else:
        print("   ⚠️ Telegram Alerts: DISABLED")

    print("=" * 50)
    print("✅ VIT Network is OPERATIONAL")
    print("📍 API: http://localhost:8000")
    print("📊 Health: http://localhost:8000/health")
    print("=" * 50)

    yield

    print("\n🛑 VIT Network shutting down...")
    alerts = get_telegram_alerts()
    if alerts and alerts.enabled:
        try:
            await alerts.send_shutdown_message()
        except Exception:
            pass
    print("✅ Cleanup complete")


app = FastAPI(
    title="VIT Sports Intelligence Network",
    version=APP_VERSION,
    description="12-Model ML Ensemble for Football Match Predictions",
    lifespan=lifespan,
)

_cors_origins_env = get_env("CORS_ALLOWED_ORIGINS", "*")
_cors_origins = ["*"] if _cors_origins_env == "*" else [o.strip() for o in _cors_origins_env.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(APIKeyMiddleware)
app.add_middleware(LoggingMiddleware)

app.include_router(predict.router)
app.include_router(result.router)
app.include_router(history.router)
app.include_router(admin.router)
app.include_router(training_route.router)
app.include_router(analytics_route.router)
app.include_router(odds_route.router)


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = str(uuid.uuid4())[:8]
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.get("/health", response_model=HealthResponse)
async def health(db: AsyncSession = Depends(get_db)):
    db_status = False
    try:
        await db.execute(select(1))
        db_status = True
    except Exception:
        pass

    orch = get_orchestrator()
    return HealthResponse(
        status="ok" if orch and orch.num_models_ready() > 0 else "degraded",
        models_loaded=orch.num_models_ready() if orch else 0,
        db_connected=db_status,
        clv_tracking_enabled=True,
    )


@app.get("/health/ml")
async def ml_health(orchestrator = Depends(get_orchestrator_dep)):
    status = orchestrator.get_model_status()
    return {
        "status": "healthy" if status.get("ready", 0) > 0 else "degraded",
        "models_loaded": status.get("ready", 0),
        "models_total": status.get("total", 0),
        "models": status.get("models", []),
    }


@app.get("/health/data")
async def data_health(loader = Depends(get_data_loader_dep)):
    return {
        "status": "healthy",
        "scraping_enabled": loader.enable_scraping,
        "odds_enabled": loader.enable_odds,
        "odds_client_ready": hasattr(loader, "odds_client") and loader.odds_client is not None,
        "scraper_ready": hasattr(loader, "scraper") and loader.scraper is not None,
    }


@app.get("/health/alerts")
async def alerts_health(alerts = Depends(get_telegram_alerts)):
    return {
        "telegram_enabled": alerts.enabled if alerts else False,
        "status": "ready" if (alerts and alerts.enabled) else "disabled",
        "bot_configured": bool(alerts and alerts.bot_token) if alerts else False,
    }


@app.get("/system/status")
async def system_status(
    db: AsyncSession = Depends(get_db),
    orchestrator = Depends(get_orchestrator_dep),
    loader = Depends(get_data_loader_dep),
    alerts = Depends(get_telegram_alerts),
):
    db_connected = False
    try:
        await db.execute(select(1))
        db_connected = True
    except Exception:
        pass

    status = orchestrator.get_model_status()
    return {
        "version": APP_VERSION,
        "status": "operational",
        "components": {
            "orchestrator": {
                "models_ready": status.get("ready", 0),
                "models_total": status.get("total", 0),
                "status": "ready" if status.get("ready", 0) > 0 else "degraded",
            },
            "data_loader": {
                "scraping_enabled": loader.enable_scraping,
                "odds_enabled": loader.enable_odds,
                "status": "ready",
            },
            "alerts": {
                "telegram_enabled": alerts.enabled if alerts else False,
                "status": "ready" if (alerts and alerts.enabled) else "disabled",
            },
            "database": {
                "connected": db_connected,
                "type": "sqlite" if _is_sqlite else "postgresql",
            },
        },
    }


@app.post("/test-predict")
async def test_predict(match: dict):
    orchestrator = get_orchestrator()
    if orchestrator is None:
        return {"error": "Orchestrator not initialized", "status": "unavailable"}

    features = {
        "home_team":   match.get("home_team"),
        "away_team":   match.get("away_team"),
        "league":      match.get("league", "premier_league"),
        "market_odds": match.get("market_odds", {}),
    }
    try:
        result = await orchestrator.predict(features, "test")
        return {"status": "success", "predictions": result.get("predictions", {})}
    except Exception as e:
        return {"error": str(e), "status": "failed"}


@app.get("/api")
async def root():
    return {
        "name": "VIT Sports Intelligence Network",
        "version": APP_VERSION,
        "status": "operational",
        "endpoints": {
            "core": {
                "POST /predict": "Predict",
                "GET /history": "History",
                "GET /health": "Health",
            },
            "admin": {
                "GET /admin/models/status": "Model status",
                "POST /admin/models/reload": "Reload",
                "GET /admin/data-sources/status": "API health",
                "POST /admin/matches/manual": "Manual match",
                "POST /admin/upload/csv": "Bulk upload",
                "GET /admin/accumulator/candidates": "Acc candidates",
                "POST /admin/accumulator/generate": "Build acca",
            },
            "training": {
                "POST /training/start": "Start training",
                "GET /training/progress/{id}": "Stream progress",
                "GET /training/compare": "Compare versions",
                "POST /training/promote": "Promote",
                "POST /training/rollback": "Rollback",
            },
            "analytics": {
                "GET /analytics/summary": "Analytics",
                "GET /analytics/compare": "Compare performance",
            },
            "odds": {
                "GET /odds": "Current odds",
                "GET /odds/sharp": "Sharp odds",
            },
        },
    }


# Static files (React frontend)
frontend_dist = os.path.join(os.path.dirname(__file__), "frontend", "dist")
if os.path.exists(frontend_dist):
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        log_level="info",
        reload=False,
    )
