#!/usr/bin/env python
"""Evaluate AI performance and generate reports"""

import asyncio
import logging
import os
import sys
from datetime import datetime, timedelta

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from app.db.database import AsyncSessionLocal
from app.services.ai_profiler import AIProfilerService
from app.services.ai_ingestion import AIIngestionService

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class AIPerformanceEvaluator:
    """Evaluate and report on AI performance"""

    def __init__(self):
        self.profiler = None
        self.ingestion = None

    async def initialize_services(self):
        """Initialize database services"""
        async with AsyncSessionLocal() as db:
            self.profiler = AIProfilerService(db)
            self.ingestion = AIIngestionService(db)

    async def update_all_metrics(self):
        """Update all AI performance metrics"""
        logger.info("Updating AI performance metrics...")

        async with AsyncSessionLocal() as db:
            service = AIIngestionService(db)
            await service.update_performance_metrics()

            profiler = AIProfilerService(db)
            await profiler.update_weights()

        logger.info("✅ Performance metrics updated")

    async def generate_comprehensive_report(self):
        """Generate detailed performance report"""
        logger.info("Generating comprehensive AI performance report...")

        async with AsyncSessionLocal() as db:
            profiler = AIProfilerService(db)
            report = await profiler.get_performance_report()

        # Print report
        print("\n" + "="*80)
        print("🤖 VIT AI META-LAYER PERFORMANCE REPORT")
        print("="*80)
        print(f"Generated: {report['generated_at']}")
        print(f"AI Sources: {report['ai_sources']}")

        if report['sources']:
            print("\n📊 Performance by AI Source:")
            print("-" * 60)
            print("<15")
            print("-" * 60)

            for source in report['sources']:
                print("<15"
                      "<10.1f"
                      "<10.1f"
                      "<8.0f"
                      "<8.0f"
                      "<8.1f")

        else:
            print("\n⚠️ No AI performance data available")

        print("\n" + "="*80)

        return report

    async def analyze_recent_performance(self, days: int = 30):
        """Analyze performance over recent period"""
        logger.info(f"Analyzing performance over last {days} days...")

        cutoff_date = datetime.now() - timedelta(days=days)

        async with AsyncSessionLocal() as db:
            profiler = AIProfilerService(db)

            # Get all sources
            report = await profiler.get_performance_report()
            sources = [s['source'] for s in report.get('sources', [])]

            drift_analysis = {}
            for source in sources:
                drift = await profiler.detect_drift(source, days)
                drift_analysis[source] = drift

        print(f"\n📈 Performance Drift Analysis (Last {days} days)")
        print("-" * 60)

        for source, analysis in drift_analysis.items():
            if analysis['drift_detected']:
                print(f"⚠️  {source}: DRIFT DETECTED")
                print(".3f")
                print(".3f")
                print(".3f")
            else:
                print(f"✅ {source}: Stable")

        return drift_analysis

    async def benchmark_vs_models(self):
        """Compare AI performance vs traditional models"""
        logger.info("Benchmarking AI vs traditional models...")

        async with AsyncSessionLocal() as db:
            profiler = AIProfilerService(db)
            report = await profiler.get_performance_report()

        # This would compare against model performances from the database
        # For now, just show AI metrics
        ai_avg_accuracy = sum(s.get('accuracy', 0) for s in report.get('sources', [])) / len(report.get('sources', []))

        print("
🎯 AI vs Model Benchmark:"        print(".3f"
        print("   (Traditional models typically 65-70%)")

        return {"ai_avg_accuracy": ai_avg_accuracy}


async def main():
    """Main evaluation workflow"""
    evaluator = AIPerformanceEvaluator()

    print("🚀 VIT AI Performance Evaluation")
    print("=" * 50)

    # Update metrics
    await evaluator.update_all_metrics()

    # Generate report
    await evaluator.generate_comprehensive_report()

    # Analyze recent performance
    await evaluator.analyze_recent_performance(days=30)

    # Benchmark
    await evaluator.benchmark_vs_models()

    print("\n✅ Evaluation complete!")


if __name__ == "__main__":
    asyncio.run(main())