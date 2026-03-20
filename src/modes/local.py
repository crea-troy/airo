"""
AIRO Mode: Local
Monitors hardware directly on this machine.
This is the default mode — no setup needed.
"""

import psutil
import subprocess
import platform
from dataclasses import dataclass


@dataclass
class LocalStats:
    cpu_percent: float
    ram_percent: float
    ram_used_gb: float
    ram_total_gb: float
    gpu_percent: float
    gpu_vram_used_gb: float
    gpu_vram_total_gb: float
    cpu_temp: float
    model_name: str = "No model detected"
    tokens_per_sec: float = 0.0


def read() -> LocalStats:
    """Read all local hardware stats in one call."""
    cpu = psutil.cpu_percent(interval=0.3)
    mem = psutil.virtual_memory()

    gpu_pct, gpu_used, gpu_total = 0.0, 0.0, 0.0
    try:
        r = subprocess.run(
            ["nvidia-smi",
             "--query-gpu=utilization.gpu,memory.used,memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=2)
        if r.returncode == 0:
            p = r.stdout.strip().split(", ")
            gpu_pct  = float(p[0])
            gpu_used = round(float(p[1]) / 1024, 2)
            gpu_total= round(float(p[2]) / 1024, 2)
    except Exception:
        pass

    temp = 0.0
    try:
        temps = psutil.sensors_temperatures()
        for key in ["coretemp", "cpu_thermal", "k10temp", "acpitz"]:
            if key in temps and temps[key]:
                temp = temps[key][0].current
                break
    except Exception:
        pass

    model = "No model detected"
    try:
        r = subprocess.run(
            ["curl", "-s", "--max-time", "1", "http://localhost:11434/api/tags"],
            capture_output=True, text=True, timeout=2)
        if r.returncode == 0 and r.stdout:
            import json
            data = json.loads(r.stdout)
            models = data.get("models", [])
            model = models[0]["name"] + " (Ollama)" if models else "Ollama running"
    except Exception:
        pass

    return LocalStats(
        cpu_percent=cpu,
        ram_percent=mem.percent,
        ram_used_gb=round(mem.used / (1024**3), 1),
        ram_total_gb=round(mem.total / (1024**3), 1),
        gpu_percent=gpu_pct,
        gpu_vram_used_gb=gpu_used,
        gpu_vram_total_gb=gpu_total,
        cpu_temp=temp,
        model_name=model,
    )
