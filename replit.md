# VIT Sports Intelligence Network v3.0.0

## Architecture

**Full-stack sports prediction platform** with a FastAPI Python backend and React/Vite frontend using a 12-model ML ensemble.

### Backend (port configurable via `BACKEND_PORT`, default 8000)
- FastAPI with async SQLAlchemy + SQLite (via aiosqlite; PostgreSQL in production via `DATABASE_URL`)
- 12-model ML ensemble for match outcome prediction
- Routes: `/predict`, `/history`, `/results`, `/admin`, `/training`, `/analytics`, `/odds`
- `GET /admin/fixtures/by-date?date=YYYY-MM-DD` — fetch real fixtures for a specific calendar day
- Entry point: `main.py`
- Config: `app/config.py` (single source of truth for version, constants, and env-driven settings)

### Frontend (port configurable via `FRONTEND_PORT`, default 5000)
- React 19 + Vite 8
- Proxies API calls to backend (configured via `VITE_BACKEND_URL`)
- Entry: `frontend/src/`

### ML Service (`services/ml_service/`)
- `model_orchestrator.py` — loads all 12 models; `_total_model_specs` is set dynamically from the model list
- Models: Poisson, XGBoost, LSTM, MonteCarlo, Ensemble, Transformer, GNN, Bayesian, RLAgent, Causal, Sentiment, Anomaly
- Beast Mode: `simulation_engine.py`, `market_engine.py`, `edge_memory.py`
- Training pipeline: `app/api/routes/training.py` (11 Beast Mode endpoints)

## Running the App

```bash
bash start.sh
```

Starts FastAPI backend then Vite frontend. Ports are read from `BACKEND_PORT` / `FRONTEND_PORT` env vars (defaults: 8000 / 5000).

## Key Configuration (app/config.py)

All constants come from env vars with safe defaults:

| Env Var | Default | Purpose |
|---|---|---|
| `APP_VERSION` | `3.0.0` | Application version (single source of truth across all files) |
| `API_KEY` | *(required in prod)* | Admin API key |
| `MAX_STAKE` | `0.05` | Maximum bet stake fraction |
| `MIN_EDGE_THRESHOLD` | `0.02` | Minimum edge to flag a bet |
| `LSTM_MAX_TRAINING_SEQS` | `2000` | Cap LSTM sequences to prevent OOM during bootstrap |
| `CORS_ALLOWED_ORIGINS` | `*` | Comma-separated CORS origins; `*` allows all |
| `BACKEND_PORT` | `8000` | Backend port |
| `FRONTEND_PORT` | `5000` | Frontend port |
| `DATABASE_URL` | `sqlite+aiosqlite:///vit.db` | Database URL |
| `AUTH_ENABLED` | `false` | Enable API key auth middleware |

## Key Files

- `main.py` — FastAPI app entry point
- `app/config.py` — Central constants and env-var helpers
- `app/__init__.py` — Package version (reads from `APP_VERSION`)
- `app/api/routes/` — API route handlers
- `app/services/` — Business logic services
- `frontend/src/` — React components
- `services/ml_service/` — ML models and Beast Mode components
- `models/` — Saved model weights (.pkl)
- `vit.db` — SQLite database (dev only)

## Environment Variables (Secrets)

Set these in Replit Secrets for production:
- `DATABASE_URL` — PostgreSQL connection string
- `API_KEY` — Admin API key
- `FOOTBALL_DATA_API_KEY` — football-data.org API key
- `ODDS_API_KEY` — The Odds API key
- `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` — Telegram bot for alerts
- `OPENAI_API_KEY` — GPT-4o-mini for sentiment model

## Model Weight Files

Saved to `models/` as `.pkl` files. On first startup models are untrained (market-implied fallback). Use Training panel to train them.
