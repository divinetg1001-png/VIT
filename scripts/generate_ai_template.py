#!/usr/bin/env python
"""Generate prediction templates for manual AI input"""

import csv
import json
import os
from datetime import datetime
from pathlib import Path

# Ensure directories exist
Path("data/templates").mkdir(parents=True, exist_ok=True)
Path("data/imports").mkdir(parents=True, exist_ok=True)

# AI sources to track
AI_SOURCES = ["chatgpt", "gemini", "grok", "deepseek", "perplexity"]

def fetch_fixtures():
    """Fetch upcoming fixtures from database or API"""
    # TODO: Connect to your football-data.org client
    # For now, return sample or read from DB

    # Option 1: From database
    # from app.db.database import AsyncSessionLocal
    # from app.db.models import Match
    # ...

    # Option 2: Sample for testing
    return [
        {
            "match_id": "m001",
            "home_team": "Arsenal",
            "away_team": "Chelsea",
            "league": "Premier League",
            "date": "2025-04-15T15:00:00"
        },
        {
            "match_id": "m002",
            "home_team": "Liverpool",
            "away_team": "Manchester City",
            "league": "Premier League",
            "date": "2025-04-15T17:30:00"
        },
        {
            "match_id": "m003",
            "home_team": "Manchester United",
            "away_team": "Tottenham",
            "league": "Premier League",
            "date": "2025-04-16T15:00:00"
        }
    ]

def generate_csv_templates():
    """Generate CSV templates for each AI source"""
    fixtures = fetch_fixtures()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    for ai_source in AI_SOURCES:
        filename = f"data/templates/ai_predictions_{ai_source}_{timestamp}.csv"

        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                "match_id", "home_team", "away_team", "league", "date",
                "home_prob", "draw_prob", "away_prob", "confidence", "reason"
            ])

            for fixture in fixtures:
                writer.writerow([
                    fixture["match_id"],
                    fixture["home_team"],
                    fixture["away_team"],
                    fixture["league"],
                    fixture["date"],
                    "",  # home_prob (0.00-1.00)
                    "",  # draw_prob (0.00-1.00)
                    "",  # away_prob (0.00-1.00)
                    "",  # confidence (0.00-1.00)
                    ""   # reason (short text)
                ])

        print(f"✅ Created: {filename}")

    # Also create a combined JSON template
    combined = {
        "metadata": {
            "generated_at": datetime.now().isoformat(),
            "fixture_count": len(fixtures),
            "ai_sources": AI_SOURCES,
            "version": "2.0"
        },
        "fixtures": fixtures,
        "predictions": []
    }

    json_path = f"data/templates/ai_predictions_all_{timestamp}.json"
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(combined, f, indent=2)

    print(f"✅ Created combined JSON: {json_path}")

    return timestamp

def generate_markdown_workflow(timestamp):
    """Generate a markdown checklist for manual input"""
    md_path = f"data/templates/AI_INPUT_WORKFLOW_{timestamp}.md"

    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(f"""# 🤖 AI Prediction Input Workflow
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## 📋 Instructions

1. Open each CSV file in Excel/Google Sheets
2. For each match, fill in:
   - `home_prob`: Probability 0.00-1.00 (e.g., 0.65)
   - `draw_prob`: Probability 0.00-1.00 (e.g., 0.20)
   - `away_prob`: Probability 0.00-1.00 (e.g., 0.15)
   - `confidence`: Your confidence 0.00-1.00
   - `reason`: Short reason (max 50 chars)

## 📁 Files to Fill

| AI Source | File |
|-----------|------|
| ChatGPT | `data/templates/ai_predictions_chatgpt_{timestamp}.csv` |
| Gemini | `data/templates/ai_predictions_gemini_{timestamp}.csv` |
| Grok | `data/templates/ai_predictions_grok_{timestamp}.csv` |
| DeepSeek | `data/templates/ai_predictions_deepseek_{timestamp}.csv` |
| Perplexity | `data/templates/ai_predictions_perplexity_{timestamp}.csv` |

## ✅ After Filling

Run import script:
```bash
python scripts/import_ai_predictions.py --timestamp {timestamp}
```

🎯 Pro Tips

· Probabilities should sum to 1.0 (script will normalize)
· Higher confidence = more weight in ensemble
· Be consistent across matches for the same AI
  """)
    print(f"✅ Created workflow guide: {md_path}")

if __name__ == "__main__":
    print("=" * 60)
    print("🤖 VIT - AI Prediction Template Generator")
    print("=" * 60)

    generate_csv_templates()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    generate_markdown_workflow(timestamp)