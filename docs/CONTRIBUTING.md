# Contributing to AIRO

All hardware backgrounds welcome. If you have AMD GPU, Windows, Apple Silicon, or a cluster — your contributions are needed.

## Setup
```bash
git clone https://github.com/YOUR_USERNAME/airo
cd airo
pip install -r requirements.txt
python airo.py web
```

## Areas to contribute
- `src/detector/hardware.py` — AMD GPU, Apple Silicon detection
- `src/controls.py` — Windows support
- `src/modes/remote.py` — cluster agent improvements
- `web/static/index.html` — UI improvements

## Philosophy
This tool should be usable by someone who has never heard of CUDA. If your contribution requires a PhD to understand, simplify it.
