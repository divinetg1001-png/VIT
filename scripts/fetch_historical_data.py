#!/usr/bin/env python3
"""
Fetch real historical match data from football-data.org API
"""
import asyncio
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from app.services.football_api import FootballDataClient

async def fetch_historical_matches():
    """Fetch historical matches for all supported leagues"""

    api_key = os.getenv("FOOTBALL_DATA_API_KEY", "")
    if not api_key:
        print("❌ FOOTBALL_DATA_API_KEY not set")
        return

    client = FootballDataClient(api_key)

    # Leagues to fetch
    leagues = [
        "premier_league", "la_liga", "bundesliga", "serie_a", "ligue_1",
        "championship", "eredivisie", "primeira_liga", "scottish_premiership", "belgian_pro_league"
    ]

    all_matches = []

    for league in leagues:
        print(f"📊 Fetching historical data for {league}...")

        try:
            # Fetch matches from the 2023-2024 season
            start_date = "2023-08-01"
            end_date = "2024-05-31"

            # Use competition-specific endpoint
            comp_code = client.COMPETITIONS.get(league, league)
            endpoint = f"/competitions/{comp_code}/matches"
            params = {
                "dateFrom": start_date,
                "dateTo": end_date,
                "status": "FINISHED",
                "limit": 50
            }
            
            data = await client._cached_request(endpoint, params, ttl=3600)
            matches = data.get("matches", [])

            print(f"   ✅ Found {len(matches)} matches for {league}")

            # Convert to our format
            for match in matches:
                try:
                    home_team = match["homeTeam"]["name"]
                    away_team = match["awayTeam"]["name"]
                    home_score = match["score"]["fullTime"]["home"]
                    away_score = match["score"]["fullTime"]["away"]

                    if home_score is None or away_score is None:
                        continue  # Skip matches without final scores

                    # Determine outcome
                    if home_score > away_score:
                        outcome = "home"
                    elif away_score > home_score:
                        outcome = "away"
                    else:
                        outcome = "draw"

                    match_data = {
                        "home_team": home_team,
                        "away_team": away_team,
                        "league": league,
                        "match_date": match["utcDate"],
                        "home_goals": home_score,
                        "away_goals": away_score,
                        "outcome": outcome,
                        "total_goals": home_score + away_score,
                        "btts": 1 if home_score > 0 and away_score > 0 else 0
                    }

                    all_matches.append(match_data)

                except KeyError as e:
                    print(f"   ⚠️ Skipping match due to missing data: {e}")
                    continue

        except Exception as e:
            print(f"   ❌ Failed to fetch {league}: {e}")
            continue

        # Rate limiting - wait 1 second between requests
        await asyncio.sleep(1)

    # Save to file
    output_path = Path(__file__).parent.parent / "data" / "historical_matches.json"

    # Load existing data if any
    existing_matches = []
    if output_path.exists():
        try:
            with open(output_path, 'r') as f:
                existing_matches = json.load(f)
            print(f"📁 Loaded {len(existing_matches)} existing matches")
        except:
            pass

    # Merge and deduplicate
    all_match_keys = {(m["home_team"], m["away_team"], m["match_date"]) for m in all_matches}
    existing_match_keys = {(m["home_team"], m["away_team"], m.get("match_date", "")) for m in existing_matches}

    new_matches = [m for m in all_matches if (m["home_team"], m["away_team"], m["match_date"]) not in existing_match_keys]
    combined_matches = existing_matches + new_matches

    # Save
    with open(output_path, 'w') as f:
        json.dump(combined_matches, f, indent=2, default=str)

    print(f"💾 Saved {len(combined_matches)} total matches ({len(new_matches)} new) to {output_path}")

if __name__ == "__main__":
    asyncio.run(fetch_historical_matches())