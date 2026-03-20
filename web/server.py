"""
AIRO Web Server v0.4
Run: python airo.py web
Open: http://localhost:7070
"""

import json, time, platform, subprocess, threading, os, sys, urllib.request

ROOT   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
sys.path.insert(0, os.path.join(ROOT, "src"))

from flask import Flask, jsonify, send_from_directory, request
import psutil

app = Flask(__name__, static_folder=STATIC, static_url_path="")

# ── live cache ──────────────────────────────────
cache = {
    "cpu_percent": 0.0, "ram_percent": 0.0,
    "ram_used_gb": 0.0, "ram_total_gb": 0.0,
    "gpu_percent": 0.0, "gpu_vram_used_gb": 0.0, "gpu_vram_total_gb": 0.0,
    "cpu_temp": 0.0,    "cpu_cores": 1,
    "model_name": "Detecting...", "tokens_per_sec": 0.0,
    "tok_history": [],  # last 20 measurements for sparkline
    "tok_status": "waiting",  # waiting / measuring / ready
}
targets  = {"cpu": 85, "ram": 75, "gpu": 90}
start_ts = time.time()


# ── tokens/sec from Ollama ──────────────────────
def measure_tokens(model):
    """
    Send a small prompt to Ollama, measure tokens/sec from eval stats.
    Ollama returns eval_count (tokens generated) and eval_duration (nanoseconds).
    """
    try:
        cache["tok_status"] = "measuring"
        payload = json.dumps({
            "model": model.replace(" (Ollama)", "").strip(),
            "prompt": "Say hello in one word.",
            "stream": False,
            "options": {"num_predict": 15}
        }).encode()
        req = urllib.request.Request(
            "http://localhost:11434/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
            ec = data.get("eval_count", 0)
            ed = data.get("eval_duration", 1)
            if ec > 0 and ed > 0:
                tps = round(ec / (ed / 1e9), 1)
                cache["tokens_per_sec"] = tps
                cache["tok_history"].append(tps)
                if len(cache["tok_history"]) > 20:
                    cache["tok_history"].pop(0)
                cache["tok_status"] = "ready"
            else:
                cache["tok_status"] = "waiting"
    except Exception:
        cache["tok_status"] = "waiting"


def tokens_loop():
    """Measure tokens/sec every 30s in background."""
    time.sleep(6)
    while True:
        m = cache.get("model_name", "")
        if m and "Ollama" in m and "no model" not in m.lower() and "Detecting" not in m:
            threading.Thread(target=measure_tokens, args=(m,), daemon=True).start()
        time.sleep(30)


# ── hardware poll ───────────────────────────────
def poll_hardware():
    while True:
        try:
            cache["cpu_percent"] = psutil.cpu_percent(interval=0.5)
            cache["cpu_cores"]   = psutil.cpu_count(logical=True)
            m = psutil.virtual_memory()
            cache["ram_percent"]  = round(m.percent, 1)
            cache["ram_used_gb"]  = round(m.used  / 1e9, 1)
            cache["ram_total_gb"] = round(m.total / 1e9, 1)

            # GPU
            try:
                r = subprocess.run(
                    ["nvidia-smi","--query-gpu=utilization.gpu,memory.used,memory.total",
                     "--format=csv,noheader,nounits"],
                    capture_output=True, text=True, timeout=2)
                if r.returncode == 0:
                    p = [x.strip() for x in r.stdout.strip().split(",")]
                    cache["gpu_percent"]       = float(p[0])
                    cache["gpu_vram_used_gb"]  = round(float(p[1])/1024, 2)
                    cache["gpu_vram_total_gb"] = round(float(p[2])/1024, 2)
            except Exception: pass

            # Temperature
            try:
                temps = psutil.sensors_temperatures()
                for k in ["coretemp","cpu_thermal","k10temp","acpitz"]:
                    if k in temps and temps[k]:
                        cache["cpu_temp"] = round(temps[k][0].current, 1); break
            except Exception: pass

            # Ollama model detection
            try:
                r = subprocess.run(
                    ["curl","-s","--max-time","1","http://localhost:11434/api/tags"],
                    capture_output=True, text=True, timeout=2)
                if r.returncode == 0 and r.stdout.strip():
                    d  = json.loads(r.stdout)
                    ms = d.get("models", [])
                    cache["model_name"] = ms[0]["name"] + " (Ollama)" if ms else "Ollama running — no model"
                elif cache["model_name"] == "Detecting...":
                    cache["model_name"] = "No model detected"
            except Exception:
                if cache["model_name"] == "Detecting...":
                    cache["model_name"] = "No model detected"

        except Exception: pass
        time.sleep(1.5)


# ── routes ──────────────────────────────────────
@app.route("/")
def index():
    return send_from_directory(STATIC, "index.html")

@app.route("/api/stats")
def stats():
    return jsonify({
        **cache,
        "uptime_sec": int(time.time() - start_ts),
        "targets": targets,
        "best": {"cpu": 85, "ram": 75, "gpu": 90},
        "os": platform.system(),
    })

@app.route("/api/targets", methods=["POST"])
def set_targets():
    data = request.json or {}
    for k in ["cpu","ram","gpu"]:
        if k in data:
            targets[k] = max(0, min(100, int(data[k])))
    return jsonify({"ok": True, "targets": targets})

@app.route("/api/measure_tokens", methods=["POST"])
def trigger_measure():
    """Manually trigger a tokens/sec measurement."""
    m = cache.get("model_name", "")
    if m and "Ollama" in m:
        threading.Thread(target=measure_tokens, args=(m,), daemon=True).start()
        return jsonify({"ok": True, "message": "Measuring... check back in ~10s"})
    return jsonify({"ok": False, "message": "No Ollama model running"})

@app.route("/api/apply", methods=["POST"])
def apply():
    results = []
    try:
        import controls as ctrl
        p = "high" if targets["cpu"]>=80 else "normal" if targets["cpu"]>=50 else "low"
        results.append({"name":"CPU priority", **vars(ctrl.set_cpu_priority(p))})
        results.append({"name":"CPU affinity", **vars(ctrl.set_cpu_affinity(targets["cpu"]/100))})
        results.append({"name":"RAM swap",     **vars(ctrl.set_swap_behavior(int((1-targets["ram"]/100)*60)))})
        if cache["gpu_vram_total_gb"] > 0:
            gm = "max" if targets["gpu"]>=80 else "balanced" if targets["gpu"]>=50 else "save"
            results.append({"name":"GPU power",  **vars(ctrl.set_gpu_power_mode(gm))})
            results.append({"name":"GPU memory", **vars(ctrl.set_gpu_memory_fraction(targets["gpu"]/100))})
        results.append({"name":"PyTorch",    **vars(ctrl.set_pytorch_optimizations())})
        results.append({"name":"Ollama ctx", **vars(ctrl.set_ollama_context_size(4096 if targets["ram"]>=70 else 2048))})
    except Exception as e:
        results.append({"name":"Error","success":False,"message":str(e),"detail":""})
    ok = sum(1 for r in results if r.get("success"))
    return jsonify({"ok": True, "results": results, "summary": f"Applied {ok}/{len(results)} changes"})

@app.route("/api/auto_optimize", methods=["POST"])
def auto_optimize():
    try:
        import controls as ctrl
        res = ctrl.auto_optimize("speed")
        ok  = sum(1 for r in res if r.success)
        return jsonify({"ok": True, "summary": f"Auto-optimized: {ok}/{len(res)} applied"})
    except Exception as e:
        return jsonify({"ok": False, "summary": str(e)})


if __name__ == "__main__":
    threading.Thread(target=poll_hardware, daemon=True).start()
    threading.Thread(target=tokens_loop,   daemon=True).start()
    print("\n⚡ AIRO Web UI starting...")
    print(f"   Local:   http://localhost:7070")
    print(f"   Network: http://0.0.0.0:7070\n")
    app.run(host="0.0.0.0", port=7070, debug=False)
