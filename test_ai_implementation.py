#!/usr/bin/env python
"""Test script for AI Meta-Layer implementation"""

import asyncio
import sys
import os

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from app.db.database import AsyncSessionLocal
from app.services.ai_ingestion import AIIngestionService
from app.services.ai_signals import AISignalService
from app.services.ai_profiler import AIProfilerService


async def test_ai_services():
    """Test the AI services"""
    print("🧪 Testing AI Meta-Layer Implementation")
    print("=" * 50)

    async with AsyncSessionLocal() as db:
        # Test services
        ingestion = AIIngestionService(db)
        signals = AISignalService(db)
        profiler = AIProfilerService(db)

        print("✅ Services initialized successfully")

        # Test empty signals
        empty_signals = signals._empty_signals()
        print(f"✅ Empty signals: {len(empty_signals)} features")

        # Test performance metrics (should be empty initially)
        performance = await ingestion.get_ai_performance()
        print(f"✅ Performance tracking: {len(performance)} AI sources")

        print("\n🎉 AI Meta-Layer implementation ready!")
        print("\nNext steps:")
        print("1. Run: python scripts/generate_ai_template.py")
        print("2. Fill the generated CSV files manually")
        print("3. Run: python scripts/import_ai_predictions.py")
        print("4. Run: python scripts/train_with_ai.py")
        print("5. Run: python scripts/evaluate_ai_performance.py")


if __name__ == "__main__":
    asyncio.run(test_ai_services())