#!/usr/bin/env python
# scripts/train_all_models.py
"""Train all 12 models on historical data"""

import json
import asyncio
import inspect
import logging
import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from services.ml_service.models.model_1_poisson import PoissonGoalModel
from services.ml_service.models.model_2_xgboost import XGBoostOutcomeClassifier
from services.ml_service.models.model_3_lstm import LSTMMomentumNetworkModel
from services.ml_service.models.model_4_monte_carlo import MonteCarloEngine
from services.ml_service.models.model_5_ensemble_agg import EnsembleAggregator
from services.ml_service.models.model_6_transformer import TransformerSequenceModel
from services.ml_service.models.model_7_gnn import GraphNeuralNetworkModel
from services.ml_service.models.model_8_bayesian import BayesianHierarchicalModel
from services.ml_service.models.model_9_rl_agent import RLPolicyAgent
from services.ml_service.models.model_10_causal import CausalInferenceModel
from services.ml_service.models.model_11_sentiment import SentimentFusionModel
from services.ml_service.models.model_12_anomaly import AnomalyRegimeDetectionModel

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class ModelTrainer:
    """Train all models"""
    
    MODELS = {
        'poisson': PoissonGoalModel("poisson_001"),
        'xgboost': XGBoostOutcomeClassifier("xgb_001"),
        'lstm': LSTMMomentumNetworkModel("lstm_001"),
        'monte_carlo': MonteCarloEngine("mc_001"),
        'ensemble': EnsembleAggregator("ensemble_001"),
        'transformer': TransformerSequenceModel("trans_001"),
        'gnn': GraphNeuralNetworkModel("gnn_001"),
        'bayesian': BayesianHierarchicalModel("bayes_001"),
        'rl_agent': RLPolicyAgent("rl_001"),
        'causal': CausalInferenceModel("causal_001"),
        'sentiment': SentimentFusionModel("sent_001"),
        'anomaly': AnomalyRegimeDetectionModel("anom_001"),
    }
    
    def __init__(self, data_path: str = None):
        self.data_path = data_path or os.path.join(PROJECT_ROOT, "data", "historical_matches.json")
        self.matches = []
        self.results = {}
    
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
    
    def train_model(self, name: str, model) -> dict:
        """Train a single model"""
        logger.info(f"=== Training {name} ===")
        
        try:
            # Try training with different parameter sets based on model type
            model_kwargs = {}
            if name == 'poisson':
                model_kwargs = {
                    'validation_split': 0.2,
                    'use_time_weights': True,
                }
            elif name in ['lstm', 'transformer', 'gnn', 'bayesian', 'causal', 'sentiment', 'anomaly']:
                model_kwargs = {'validation_split': 0.2}
            elif name == 'rl_agent':
                model_kwargs = {'episodes': 200}
            # XGBoost only supports positional match list input in this version
            train_signature = inspect.signature(model.train)
            model_kwargs = {
                k: v for k, v in model_kwargs.items() if k in train_signature.parameters
            }
            result = model.train(self.matches, **model_kwargs)
            
            # Save model
            project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
            model_dir = os.path.join(project_root, "models")
            os.makedirs(model_dir, exist_ok=True)
            model_path = os.path.join(model_dir, f"{name}_model.pkl")
            model.save(model_path)
            logger.info(f"✅ {name} trained and saved to {model_path}")
            
            return {
                'name': name,
                'status': 'success',
                'accuracy': result.get('accuracy', 0) if isinstance(result, dict) else 0,
                'message': 'Training completed successfully'
            }
        except Exception as e:
            logger.error(f"❌ {name} training failed: {e}")
            return {
                'name': name,
                'status': 'failed',
                'error': str(e)
            }
    
    def train_all(self):
        """Train all models sequentially"""
        logger.info("=" * 60)
        logger.info("Starting model training for all 12 models")
        logger.info("=" * 60)
        
        if not self.load_data():
            return False
        
        for name, model in self.MODELS.items():
            result = self.train_model(name, model)
            self.results[name] = result
            logger.info("")
        
        # Summary
        logger.info("=" * 60)
        logger.info("Training Summary")
        logger.info("=" * 60)
        
        successful = sum(1 for r in self.results.values() if r.get('status') == 'success')
        failed = sum(1 for r in self.results.values() if r.get('status') == 'failed')
        
        for name, result in self.results.items():
            status_icon = "✅" if result.get('status') == 'success' else "❌"
            logger.info(f"{status_icon} {name}: {result.get('status')}")
        
        logger.info("=" * 60)
        logger.info(f"Successfully trained: {successful}/{len(self.MODELS)}")
        logger.info(f"Failed: {failed}/{len(self.MODELS)}")
        logger.info("=" * 60)
        
        return successful == len(self.MODELS)


async def main():
    """Main training workflow"""
    trainer = ModelTrainer()
    trainer.train_all()


if __name__ == "__main__":
    asyncio.run(main())