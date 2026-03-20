# ⚡ AIRO — AI Resource Optimizer

> Run AI workloads at full power on any machine.

AIRO auto-detects your hardware and shows you exactly how to get maximum performance from your CPU, RAM, and GPU for AI workloads — with a single click.

## Quick Start

```bash
git clone https://github.com/YOUR_USERNAME/airo
cd airo
bash install.sh
python airo.py web
```

Then open **http://localhost:7070** in your browser.

## What it does

- Detects CPU, RAM, GPU automatically — zero config
- Live monitoring dashboard in your browser
- Shows current use vs best performance vs your choice
- One click to apply optimizations
- Works with Ollama, llama.cpp, PyTorch, any model
- Live tokens/sec measurement from Ollama

## Modes

| Mode | What it monitors |
|------|-----------------|
| Local | Your machine's CPU/RAM/GPU in real time |
| API Cloud | OpenAI/Anthropic latency, cost, errors |
| Remote | GPU cluster over SSH agent |

## Commands

```bash
python airo.py web       # web UI (recommended)
python airo.py           # terminal dashboard
python airo.py detect    # show hardware specs
python airo.py optimize  # show AI recommendations
```

## Requirements

- Python 3.8+
- `pip install psutil rich flask`
- Ollama (optional) for live token speed

## License

MIT — free to use, modify, distribute.

---
*Built by researchers, for researchers — and everyone else.*
