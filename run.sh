#!/bin/bash
echo "⌐ Starting Environment Setup..."
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
fi
# Install playwright browsers
python -m playwright install chromium

echo "⌐ Starting FastAPI Server..."
python -m uvicorn main:app --host 0.0.0.0 --port 8080
