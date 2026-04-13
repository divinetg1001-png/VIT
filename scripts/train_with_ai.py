#!/usr/bin/env python
"""Train models with AI signals as additional features"""

import json
import asyncio
import logging
import os
import sys
import numpy as np
import pandas as pd

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from services.ml_service.models.model_orchestrator import ModelOrchestrator
from app.db.database import AsyncSessionLocal
from app.services.ai_signals import AISignalService

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class AITrainer:
    """Train models with AI signals integrated"""

    def __init__(self, data_path: str = None):
        self.data_path = data_path or os.path.join(PROJECT_ROOT, "data", "historical_matches.json")
        self.matches = []
        self.enhanced_matches = []

    def load_data(self):
        """Load historical match data"""
        logger.info(f"Loading data from {self.data_path}")
        try:
            with open(self.data_path, 'r') as f:
                self.matches = json.load(f)
            logger.info(f"Loaded {len(self.matches)} matches")
            return True
        except FileNotFoundError:
            logger.error(f"Data file not found: {self.data_path}")
            return False

    async def enhance_with_ai_signals(self):
        """Add AI signals to match data"""
        logger.info("Enhancing matches with AI signals...")

        async with AsyncSessionLocal() as db:
            ai_service = AISignalService(db)

            enhanced = []
            for match in self.matches:
                # Try to find match in database by teams and date
                # For now, assume matches have external_id or we can match by teams
                match_id = match.get("match_id") or match.get("id")

                if match_id:
                    # Get AI signals for this match
                    signals = await ai_service.get_signals_for_match(match_id)
                else:
                    # No AI data available
                    signals = ai_service._empty_signals()

                # Add AI signals to match features
                enhanced_match = match.copy()
                enhanced_match["ai_signals"] = signals

                # Flatten AI signals into top-level features for model input
                for key, value in signals.items():
                    enhanced_match[f"feature_{key}"] = value

                enhanced.append(enhanced_match)

            self.enhanced_matches = enhanced
            logger.info(f"Enhanced {len(enhanced)} matches with AI signals")

    def prepare_training_data(self):
        """Convert enhanced matches to training format"""
        if not self.enhanced_matches:
            logger.error("No enhanced matches available")
            return None

        # Convert to DataFrame for easier processing
        df = pd.DataFrame(self.enhanced_matches)

        # Extract target variables
        targets = []
        features = []

        for _, match in df.iterrows():
            # Target: actual outcome (home/draw/away)
            if match.get("home_goals") is not None and match.get("away_goals") is not None:
                if match["home_goals"] > match["away_goals"]:
                    target = "home"
                elif match["home_goals"] == match["away_goals"]:
                    target = "draw"
                else:
                    target = "away"
            else:
                continue  # Skip matches without results

            # Features: existing + AI signals
            feature_dict = {
                "home_team": match.get("home_team", ""),
                "away_team": match.get("away_team", ""),
                "league": match.get("league", ""),
                "season": match.get("season", ""),
                # AI signals
                "ai_consensus_home": match.get("feature_ai_consensus_home", 0.33),
                "ai_consensus_draw": match.get("feature_ai_consensus_draw", 0.33),
                "ai_consensus_away": match.get("feature_ai_consensus_away", 0.33),
                "ai_disagreement": match.get("feature_ai_disagreement", 0.0),
                "ai_max_confidence": match.get("feature_ai_max_confidence", 0.5),
                "ai_weighted_home": match.get("feature_ai_weighted_home", 0.33),
                "ai_weighted_draw": match.get("feature_ai_weighted_draw", 0.33),
                "ai_weighted_away": match.get("feature_ai_weighted_away", 0.33),
                # Add more features as needed
            }

            targets.append(target)
            features.append(feature_dict)

        logger.info(f"Prepared {len(features)} training samples")
        return features, targets

    async def train_with_ai_signals(self):
        """Main training workflow with AI signals"""
        logger.info("=" * 60)
        logger.info("Starting AI-enhanced model training")
        logger.info("=" * 60)

        # Load base data
        if not self.load_data():
            return False

        # Enhance with AI signals
        await self.enhance_with_ai_signals()

        # Prepare training data
        training_data = self.prepare_training_data()
        if not training_data:
            return False

        features, targets = training_data

        # Initialize orchestrator
        try:
            orchestrator = ModelOrchestrator()
            orchestrator.load_all_models()
        except Exception as e:
            logger.error(f"Failed to initialize orchestrator: {e}")
            return False

        # Train each model with AI-enhanced features
        results = {}
        for model_name, model in orchestrator.models.items():
            logger.info(f"Training {model_name} with AI signals...")

            try:
                # Pass enhanced features to model training
                result = model.train(features, targets)
                results[model_name] = {
                    "status": "success",
                    "accuracy": result.get("accuracy", 0),
                    "ai_features_used": len([k for k in features[0].keys() if k.startswith("ai_")])
                }
                logger.info(f"✅ {model_name} trained successfully")
            except Exception as e:
                logger.error(f"❌ {model_name} training failed: {e}")
                results[model_name] = {"status": "failed", "error": str(e)}

        # Summary
        logger.info("=" * 60)
        logger.info("AI-Enhanced Training Summary")
        logger.info("=" * 60)

        successful = sum(1 for r in results.values() if r.get("status") == "success")
        avg_accuracy = np.mean([r.get("accuracy", 0) for r in results.values() if r.get("status") == "success"])

        for name, result in results.items():
            status_icon = "✅" if result.get("status") == "success" else "❌"
            accuracy = result.get("accuracy", 0)
            logger.info(f"{status_icon} {name}: {result.get('status')} (acc: {accuracy:.3f})")

        logger.info("=" * 60)
        logger.info(f"Successfully trained: {successful}/{len(results)}")
        logger.info(f"Average accuracy: {avg_accuracy:.3f}")
        logger.info("=" * 60)

        return successful > 0


async def main():
    """Main execution"""
    trainer = AITrainer()
    success = await trainer.train_with_ai_signals()

    if success:
        logger.info("🎉 AI-enhanced training completed successfully!")
    else:
        logger.error("❌ AI-enhanced training failed")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())