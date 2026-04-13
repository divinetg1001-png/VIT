#!/usr/bin/env python
"""Import manually filled AI predictions into database"""

import asyncio
import csv
import json
import os
import sys
from datetime import datetime
import numpy as np

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.db.models import AIPrediction, Match, AISignalCache
from app.core.dependencies import get_data_loader

# AI sources
AI_SOURCES = ["chatgpt", "gemini", "grok", "deepseek", "perplexity"]


async def import_csv(source: str, csv_path: str, session):
    """Import predictions from a single CSV file"""
    imported = 0
    skipped = 0

    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)

        for row in reader:
            # Skip if probabilities missing
            if not row.get('home_prob') or not row.get('draw_prob') or not row.get('away_prob'):
                skipped += 1
                continue

            # Find match
            result = await session.execute(
                select(Match).where(Match.external_id == row['match_id'])
            )
            match = result.scalar_one_or_none()

            if not match:
                print(f"⚠️ Match not found: {row['match_id']}")
                skipped += 1
                continue

            # Parse probabilities
            home_prob = float(row['home_prob'])
            draw_prob = float(row['draw_prob'])
            away_prob = float(row['away_prob'])

            # Normalize to sum 1.0
            total = home_prob + draw_prob + away_prob
            if abs(total - 1.0) > 0.01:
                home_prob /= total
                draw_prob /= total
                away_prob /= total
                print(f"   Normalized {row['match_id']}: {home_prob:.2f}/{draw_prob:.2f}/{away_prob:.2f}")

            confidence = float(row['confidence']) if row.get('confidence') else 0.7

            # Check if prediction already exists
            existing = await session.execute(
                select(AIPrediction).where(
                    AIPrediction.match_id == match.id,
                    AIPrediction.source == source
                )
            )
            existing_pred = existing.scalar_one_or_none()

            if existing_pred:
                # Update existing
                existing_pred.home_prob = home_prob
                existing_pred.draw_prob = draw_prob
                existing_pred.away_prob = away_prob
                existing_pred.confidence = confidence
                existing_pred.reason = row.get('reason', '')
                existing_pred.timestamp = datetime.now()
            else:
                # Create new
                ai_pred = AIPrediction(
                    match_id=match.id,
                    source=source,
                    home_prob=home_prob,
                    draw_prob=draw_prob,
                    away_prob=away_prob,
                    confidence=confidence,
                    reason=row.get('reason', ''),
                    model_version="manual_v1"
                )
                session.add(ai_pred)

            imported += 1

    return imported, skipped


async def import_all_templates(timestamp: str = None):
    """Import all AI predictions from template directory"""

    # Determine which templates to import
    template_dir = "data/templates"

    if timestamp:
        # Import specific timestamp
        csv_files = [f for f in os.listdir(template_dir) if timestamp in f and f.endswith('.csv')]
    else:
        # Import latest
        csv_files = [f for f in os.listdir(template_dir) if f.endswith('.csv') and 'ai_predictions_' in f]
        # Get most recent by timestamp in filename
        csv_files.sort(reverse=True)
        csv_files = csv_files[:5]  # Latest 5 (one per AI)

    # Group by AI source
    imports = {}
    for source in AI_SOURCES:
        matching = [f for f in csv_files if source in f]
        if matching:
            imports[source] = os.path.join(template_dir, matching[0])
        else:
            print(f"⚠️ No file found for {source}")

    if not imports:
        print("❌ No template files found")
        return

    print(f"\n📥 Importing predictions from {len(imports)} sources...")

    # Setup database
    from app.db.database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        async with session.begin():
            for source, filepath in imports.items():
                print(f"\n📄 Processing {source} from {os.path.basename(filepath)}")
                imported, skipped = await import_csv(source, filepath, session)
                print(f"   ✅ Imported: {imported}, Skipped: {skipped}")

            # After imports, recalculate signal cache
            print("\n🔄 Recalculating AI signal cache...")
            await recalculate_signal_cache(session)

        await session.commit()

    print("\n✅ Import complete!")


async def recalculate_signal_cache(session):
    """Recalculate aggregated AI signals for all matches"""

    # Get all matches with AI predictions
    result = await session.execute(
        select(Match, AIPrediction)
        .join(AIPrediction, Match.id == AIPrediction.match_id)
    )

    matches_with_ai = {}
    for match, pred in result:
        if match.id not in matches_with_ai:
            matches_with_ai[match.id] = {"match": match, "predictions": []}
        matches_with_ai[match.id]["predictions"].append(pred)

    for match_id, data in matches_with_ai.items():
        predictions = data["predictions"]

        if len(predictions) < 2:
            continue

        # Calculate consensus
        home_probs = [p.home_prob for p in predictions]
        draw_probs = [p.draw_prob for p in predictions]
        away_probs = [p.away_prob for p in predictions]
        confidences = [p.confidence for p in predictions]

        consensus_home = sum(home_probs) / len(home_probs)
        consensus_draw = sum(draw_probs) / len(draw_probs)
        consensus_away = sum(away_probs) / len(away_probs)

        # Disagreement = variance
        all_probs = home_probs + draw_probs + away_probs
        disagreement = np.var(all_probs) if len(all_probs) > 1 else 0

        # Weighted by confidence
        total_confidence = sum(confidences)
        if total_confidence > 0:
            weighted_home = sum(p.home_prob * p.confidence for p in predictions) / total_confidence
            weighted_draw = sum(p.draw_prob * p.confidence for p in predictions) / total_confidence
            weighted_away = sum(p.away_prob * p.confidence for p in predictions) / total_confidence
        else:
            weighted_home = weighted_draw = weighted_away = 0.33

        # Check if cache exists
        existing = await session.execute(
            select(AISignalCache).where(AISignalCache.match_id == match_id)
        )
        cache = existing.scalar_one_or_none()

        if cache:
            # Update existing
            cache.consensus_home = consensus_home
            cache.consensus_draw = consensus_draw
            cache.consensus_away = consensus_away
            cache.disagreement_score = disagreement
            cache.max_confidence = max(confidences)
            cache.weighted_home = weighted_home
            cache.weighted_draw = weighted_draw
            cache.weighted_away = weighted_away
            cache.per_ai_predictions = {
                p.source: {
                    "home": p.home_prob,
                    "draw": p.draw_prob,
                    "away": p.away_prob,
                    "confidence": p.confidence
                }
                for p in predictions
            }
        else:
            # Create new
            cache = AISignalCache(
                match_id=match_id,
                consensus_home=consensus_home,
                consensus_draw=consensus_draw,
                consensus_away=consensus_away,
                disagreement_score=disagreement,
                max_confidence=max(confidences),
                weighted_home=weighted_home,
                weighted_draw=weighted_draw,
                weighted_away=weighted_away,
                per_ai_predictions={
                    p.source: {
                        "home": p.home_prob,
                        "draw": p.draw_prob,
                        "away": p.away_prob,
                        "confidence": p.confidence
                    }
                    for p in predictions
                }
            )
            session.add(cache)

    print(f"   ✅ Updated signal cache for {len(matches_with_ai)} matches")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Import AI predictions")
    parser.add_argument("--timestamp", help="Specific timestamp to import")
    parser.add_argument("--file", help="Import specific file")

    args = parser.parse_args()

    if args.file:
        # Import single file
        print(f"Importing {args.file}...")
        # TODO: implement single file import
    else:
        asyncio.run(import_all_templates(args.timestamp))