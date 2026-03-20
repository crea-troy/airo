#!/bin/bash
echo ""
echo "⚡ Installing AIRO - AI Resource Optimizer"
echo "──────────────────────────────────────────"
python3 -c "import sys; print(f'✅ Python: {sys.version.split()[0]}')"
echo "📦 Installing dependencies..."
pip install psutil rich flask --quiet
echo "✅ Done!"
echo ""
echo "Start web UI:      python airo.py web"
echo "                   then open: http://localhost:7070"
echo "Start terminal:    python airo.py"
echo ""
