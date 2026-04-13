# app/services/results_settler.py
"""
Auto-settlement service.
Polls Football-Data.org for FINISHED matches and settles any unsettled
predictions in the database with actual scores + CLV calculation.
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models import Match, Prediction, CLVEntry
from app.services.clv_tracker import CLVTracker

logger = logging.getLogger(__name__)

COMPETITIONS = {
    "premier_league": "PL",
    "serie_a":        "SA",
    "la_liga":        "PD",
    "bundesliga":     "BL1",
    "ligue_1":        "FL1",
    "championship":   "ELC",
    "eredivisie":     "DED",
    "primeira_liga":  "PPL",
    "scottish_premiership": "SPL",
    "belgian_pro_league":   "BJL",
}


def _norm_name(name: str) -> str:
    """Normalise team name for fuzzy matching."""
    for suffix in [" FC", " AFC", " CF", " SC", " United", " City",
                   " Town", " Wanderers", " Athletic", " Hotspur"]:
        name = name.replace(suffix, "")
    return name.strip().lower()


def _names_match(api_name: str, db_name: str) -> bool:
    """Return True if the two team names refer to the same club."""
    if api_name.lower() == db_name.lower():
        return True
    return _norm_name(api_name) == _norm_name(db_name)


async def fetch_finished_matches(days_back: int = 2) -> list[dict]:
    """
    Pull FINISHED matches from Football-Data.org for the last `days_back` days.
    Returns a list of dicts with home_team, away_team, league, kickoff,
    home_goals, away_goals.
    """
    key = os.getenv("FOOTBALL_DATA_API_KEY", "")
    if not key:
        logger.warning("FOOTBALL_DATA_API_KEY not set — cannot fetch finished matches")
        return []

    now       = datetime.now(timezone.utc)
    date_from = (now - timedelta(days=days_back)).strftime("%Y-%m-%d")
    date_to   = now.strftime("%Y-%m-%d")
    finished  = []

    async with httpx.AsyncClient(timeout=20) as client:
        for league, code in COMPETITIONS.items():
            try:
                r = await client.get(
                    f"https://api.football-data.org/v4/competitions/{code}/matches",
                    headers={"X-Auth-Token": key},
                    params={"status": "FINISHED", "dateFrom": date_from, "dateTo": date_to},
                )
                if r.status_code == 200:
                    for m in r.json().get("matches", []):
                        score = m.get("score", {}).get("fullTime", {})
                        home_g = score.get("home")
                        away_g = score.get("away")
                        if home_g is None or away_g is None:
                            continue
                        finished.append({
                            "home_team":    m["homeTeam"]["name"],
                            "away_team":    m["awayTeam"]["name"],
                            "league":       league,
                            "kickoff":      m.get("utcDate", ""),
                            "home_goals":   int(home_g),
                            "away_goals":   int(away_g),
                        })
                elif r.status_code == 429:
                    logger.warning(f"Rate limit hit for {league}")
                elif r.status_code == 403:
                    logger.warning(f"API key rejected for {league} — check FOOTBALL_DATA_API_KEY tier")
            except Exception as e:
                logger.warning(f"Finished-match fetch failed for {league}: {e}")

    return finished


async def fetch_live_matches() -> list[dict]:
    """
    Pull IN_PLAY matches from Football-Data.org right now.
    Returns a list of fixture dicts identical to the fixtures endpoint format.
    """
    key = os.getenv("FOOTBALL_DATA_API_KEY", "")
    if not key:
        return []

    live = []
    async with httpx.AsyncClient(timeout=15) as client:
        for league, code in COMPETITIONS.items():
            try:
                r = await client.get(
                    f"https://api.football-data.org/v4/competitions/{code}/matches",
                    headers={"X-Auth-Token": key},
                    params={"status": "IN_PLAY"},
                )
                if r.status_code == 200:
                    for m in r.json().get("matches", []):
                        score = m.get("score", {}).get("currentScore") or \
                                m.get("score", {}).get("halfTime", {})
                        live.append({
                            "home_team":    m["homeTeam"]["name"],
                            "away_team":    m["awayTeam"]["name"],
                            "league":       league,
                            "kickoff_time": m.get("utcDate", ""),
                            "status":       "live",
                            "home_score":   score.get("home") if score else None,
                            "away_score":   score.get("away") if score else None,
                            "minute":       m.get("minute"),
                            "market_odds":  {},
                        })
            except Exception as e:
                logger.warning(f"Live-match fetch failed for {league}: {e}")

    return live


async def settle_results(days_back: int = 2) -> dict:
    """
    Main settlement entry point.
    1. Fetches finished matches from the API.
    2. Finds matching unsettled DB predictions.
    3. Applies actual result + CLV calc to each.
    Returns a summary dict.
    """
    finished = await fetch_finished_matches(days_back)
    if not finished:
        return {
            "settled": 0,
            "already_settled": 0,
            "no_prediction": 0,
            "not_found": 0,
            "errors": 0,
            "message": "No finished matches returned from API",
        }

    settled          = 0
    already_settled  = 0
    no_prediction    = 0
    not_found        = 0
    errors           = 0

    async for db in get_db():
        for api_match in finished:
            try:
                # Find this match in our DB (unsettled predictions)
                result = await db.execute(
                    select(Match)
                    .where(Match.status != "completed")
                    .order_by(Match.kickoff_time.desc())
                )
                unsettled = result.scalars().all()

                db_match: Optional[Match] = None
                for m in unsettled:
                    if _names_match(api_match["home_team"], m.home_team) and \
                       _names_match(api_match["away_team"], m.away_team):
                        db_match = m
                        break

                if not db_match:
                    not_found += 1
                    continue

                if db_match.status == "completed":
                    already_settled += 1
                    continue

                # Determine outcome
                home_g = api_match["home_goals"]
                away_g = api_match["away_goals"]
                if home_g > away_g:
                    outcome = "home"
                elif home_g == away_g:
                    outcome = "draw"
                else:
                    outcome = "away"

                # Update the match
                async with db.begin_nested():
                    db_match.home_goals    = home_g
                    db_match.away_goals    = away_g
                    db_match.actual_outcome = outcome
                    db_match.status        = "completed"

                    # Settle the linked prediction if one exists
                    pred_res = await db.execute(
                        select(Prediction).where(Prediction.match_id == db_match.id)
                    )
                    prediction = pred_res.scalar_one_or_none()

                    profit = 0.0
                    if prediction and prediction.bet_side:
                        if prediction.bet_side == outcome:
                            profit = prediction.recommended_stake * (
                                (prediction.entry_odds or 2.0) - 1
                            )
                        else:
                            profit = -(prediction.recommended_stake or 0.0)

                        # Update CLV entry
                        clv_res = await db.execute(
                            select(CLVEntry).where(CLVEntry.prediction_id == prediction.id)
                        )
                        clv_entry = clv_res.scalar_one_or_none()
                        if clv_entry:
                            closing = {
                                "home": db_match.closing_odds_home or 2.0,
                                "draw": db_match.closing_odds_draw or 3.3,
                                "away": db_match.closing_odds_away or 3.0,
                            }
                            side_odds = closing.get(prediction.bet_side, 2.0)
                            clv_entry.closing_odds = side_odds
                            clv_entry.clv          = CLVTracker.calculate_clv(
                                clv_entry.entry_odds or 2.0, side_odds
                            )
                            clv_entry.bet_outcome  = "win" if prediction.bet_side == outcome else "loss"
                            clv_entry.profit       = profit
                        elif prediction.bet_side:
                            await CLVTracker.update_closing_by_prediction(
                                db, prediction.id,
                                db_match.closing_odds_home or 2.0,
                                db_match.closing_odds_draw or 3.3,
                                db_match.closing_odds_away or 3.0,
                                outcome, profit,
                            )
                    else:
                        no_prediction += 1

                await db.commit()
                settled += 1
                logger.info(
                    f"Settled: {db_match.home_team} {home_g}-{away_g} {db_match.away_team} ({outcome})"
                )

            except Exception as e:
                errors += 1
                logger.error(f"Settlement error for {api_match}: {e}", exc_info=True)
                await db.rollback()

    return {
        "settled":         settled,
        "already_settled": already_settled,
        "no_prediction":   no_prediction,
        "not_found":       not_found,
        "errors":          errors,
        "message":         f"Settlement complete: {settled} match(es) settled",
    }
