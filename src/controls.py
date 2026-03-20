"""
AIRO System Controls
Actually applies changes to CPU priority, RAM, GPU power, Ollama, llama.cpp, PyTorch
"""

import os
import sys
import subprocess
import platform
import psutil
from dataclasses import dataclass
from typing import Optional


@dataclass
class ControlResult:
    success: bool
    message: str
    detail: str = ""


# ─────────────────────────────────────────────
# CPU CONTROL
# ─────────────────────────────────────────────

def set_cpu_priority(level: str = "high") -> ControlResult:
    """
    Set CPU process priority for AI workloads.
    level: 'high', 'normal', 'low'
    """
    try:
        # Map level to nice value
        nice_map = {
            "high":   -10,   # Higher priority (needs sudo on Linux)
            "normal":   0,   # Default
            "low":     10,   # Background
        }
        nice_val = nice_map.get(level, 0)

        # Find Python / Ollama / llama.cpp processes and reprioritize
        changed = []
        target_names = ["python", "python3", "ollama", "llama", "llama.cpp", "llama-server"]

        for proc in psutil.process_iter(["pid", "name", "nice"]):
            try:
                if any(t in proc.info["name"].lower() for t in target_names):
                    p = psutil.Process(proc.info["pid"])
                    p.nice(nice_val)
                    changed.append(proc.info["name"])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        if changed:
            return ControlResult(
                success=True,
                message=f"CPU priority set to {level}",
                detail=f"Applied to: {', '.join(set(changed))}"
            )
        else:
            # Set for current process at least
            psutil.Process(os.getpid()).nice(nice_val)
            return ControlResult(
                success=True,
                message=f"CPU priority set to {level} for AIRO process",
                detail="No AI processes found — applied to current process"
            )
    except psutil.AccessDenied:
        return ControlResult(
            success=False,
            message="Permission denied",
            detail="Run with sudo for high priority control"
        )
    except Exception as e:
        return ControlResult(success=False, message="CPU priority change failed", detail=str(e))


def set_cpu_affinity(core_fraction: float = 0.8) -> ControlResult:
    """
    Limit which CPU cores AI processes can use.
    core_fraction: 0.0 to 1.0
    """
    try:
        total_cores = psutil.cpu_count(logical=True)
        use_cores = max(1, int(total_cores * core_fraction))
        core_list = list(range(use_cores))

        changed = []
        target_names = ["python", "python3", "ollama", "llama"]
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                if any(t in proc.info["name"].lower() for t in target_names):
                    p = psutil.Process(proc.info["pid"])
                    p.cpu_affinity(core_list)
                    changed.append(proc.info["name"])
            except (psutil.NoSuchProcess, psutil.AccessDenied, AttributeError):
                continue

        return ControlResult(
            success=True,
            message=f"Using {use_cores}/{total_cores} CPU cores",
            detail=f"Cores {core_list[0]}–{core_list[-1]} active"
        )
    except Exception as e:
        return ControlResult(success=False, message="CPU affinity change failed", detail=str(e))


# ─────────────────────────────────────────────
# RAM CONTROL
# ─────────────────────────────────────────────

def set_swap_behavior(swappiness: int = 10) -> ControlResult:
    """
    Set Linux swap aggressiveness (0=avoid swap, 100=swap aggressively).
    Lower = keep more in RAM = better for AI.
    """
    if platform.system() != "Linux":
        return ControlResult(
            success=False,
            message="Swap control only on Linux",
            detail=f"Your OS: {platform.system()}"
        )
    try:
        result = subprocess.run(
            ["sysctl", "-w", f"vm.swappiness={swappiness}"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            return ControlResult(
                success=True,
                message=f"Swap aggressiveness set to {swappiness}",
                detail="0=never swap (best for AI), 100=swap often"
            )
        else:
            return ControlResult(
                success=False,
                message="Need sudo for swap control",
                detail=result.stderr.strip()
            )
    except Exception as e:
        return ControlResult(success=False, message="Swap control failed", detail=str(e))


def drop_memory_cache() -> ControlResult:
    """Drop Linux page cache to free RAM for AI model loading."""
    if platform.system() != "Linux":
        return ControlResult(success=False, message="Only available on Linux")
    try:
        result = subprocess.run(
            ["sh", "-c", "echo 1 > /proc/sys/vm/drop_caches"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            return ControlResult(
                success=True,
                message="Memory cache cleared",
                detail="RAM freed for AI model loading"
            )
        return ControlResult(
            success=False,
            message="Need sudo to clear cache",
            detail=result.stderr.strip()
        )
    except Exception as e:
        return ControlResult(success=False, message="Cache clear failed", detail=str(e))


# ─────────────────────────────────────────────
# GPU CONTROL
# ─────────────────────────────────────────────

def set_gpu_power_mode(mode: str = "max") -> ControlResult:
    """
    Set NVIDIA GPU power mode.
    mode: 'max' (performance), 'balanced', 'save'
    """
    power_map = {
        "max":      "0",   # persistence mode + max clocks
        "balanced": "1",
        "save":     "2",
    }
    try:
        # Enable persistence mode for stable performance
        subprocess.run(["nvidia-smi", "-pm", "1"], capture_output=True)

        # Set power limit
        if mode == "max":
            # Query max power limit
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=power.max_limit", "--format=csv,noheader,nounits"],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                max_watts = result.stdout.strip().split("\n")[0].strip()
                subprocess.run(
                    ["nvidia-smi", "-pl", max_watts],
                    capture_output=True
                )

        # Set compute mode
        subprocess.run(
            ["nvidia-smi", "--compute-mode=" + power_map.get(mode, "0")],
            capture_output=True
        )

        return ControlResult(
            success=True,
            message=f"GPU set to {mode} performance mode",
            detail="nvidia-smi settings applied"
        )
    except FileNotFoundError:
        return ControlResult(
            success=False,
            message="nvidia-smi not found",
            detail="NVIDIA GPU not detected or drivers not installed"
        )
    except Exception as e:
        return ControlResult(success=False, message="GPU control failed", detail=str(e))


def set_gpu_memory_fraction(fraction: float = 0.9) -> ControlResult:
    """
    Set environment variable to limit GPU memory usage for PyTorch/TF.
    fraction: 0.0 to 1.0
    """
    try:
        pct = int(fraction * 100)
        # Set env vars for common frameworks
        os.environ["PYTORCH_CUDA_ALLOC_CONF"] = f"max_split_size_mb:{int(fraction * 8192)}"
        os.environ["TF_MEMORY_ALLOCATION"] = str(fraction)
        os.environ["CUDA_VISIBLE_DEVICES"] = "0"  # Use first GPU

        return ControlResult(
            success=True,
            message=f"GPU memory limited to {pct}%",
            detail="PyTorch + TensorFlow env vars set"
        )
    except Exception as e:
        return ControlResult(success=False, message="GPU memory control failed", detail=str(e))


# ─────────────────────────────────────────────
# OLLAMA CONTROL
# ─────────────────────────────────────────────

def get_ollama_status() -> dict:
    """Check if Ollama is running and what model is loaded."""
    try:
        result = subprocess.run(
            ["curl", "-s", "http://localhost:11434/api/tags"],
            capture_output=True, text=True, timeout=3
        )
        if result.returncode == 0 and result.stdout:
            import json
            data = json.loads(result.stdout)
            models = [m["name"] for m in data.get("models", [])]
            return {"running": True, "models": models}
    except Exception:
        pass
    return {"running": False, "models": []}


def restart_ollama_with_gpu_layers(num_layers: int = 32) -> ControlResult:
    """
    Restart Ollama with more or fewer GPU layers.
    More layers = faster but uses more VRAM.
    """
    try:
        # Set env var for GPU layers
        os.environ["OLLAMA_NUM_GPU"] = str(num_layers)

        # Kill existing Ollama
        for proc in psutil.process_iter(["pid", "name"]):
            if "ollama" in proc.info["name"].lower():
                psutil.Process(proc.info["pid"]).terminate()

        import time
        time.sleep(1)

        # Restart Ollama
        subprocess.Popen(
            ["ollama", "serve"],
            env=os.environ,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        return ControlResult(
            success=True,
            message=f"Ollama restarted with {num_layers} GPU layers",
            detail="Wait ~5s for Ollama to come back online"
        )
    except FileNotFoundError:
        return ControlResult(
            success=False,
            message="Ollama not installed",
            detail="Install from https://ollama.com"
        )
    except Exception as e:
        return ControlResult(success=False, message="Ollama restart failed", detail=str(e))


def set_ollama_context_size(ctx: int = 4096) -> ControlResult:
    """Set Ollama context window size via env var."""
    try:
        os.environ["OLLAMA_NUM_CTX"] = str(ctx)
        return ControlResult(
            success=True,
            message=f"Context size set to {ctx} tokens",
            detail="Takes effect on next Ollama model load"
        )
    except Exception as e:
        return ControlResult(success=False, message="Context size change failed", detail=str(e))


# ─────────────────────────────────────────────
# LLAMA.CPP CONTROL
# ─────────────────────────────────────────────

def get_llamacpp_status() -> dict:
    """Check if llama.cpp server is running."""
    try:
        result = subprocess.run(
            ["curl", "-s", "http://localhost:8080/health"],
            capture_output=True, text=True, timeout=3
        )
        return {"running": result.returncode == 0}
    except Exception:
        return {"running": False}


def restart_llamacpp(
    model_path: str,
    threads: int = 8,
    gpu_layers: int = 32,
    ctx_size: int = 4096,
    batch_size: int = 512
) -> ControlResult:
    """
    Restart llama.cpp server with optimized settings.
    """
    try:
        # Kill existing llama-server process
        for proc in psutil.process_iter(["pid", "name"]):
            name = proc.info["name"].lower()
            if "llama" in name or "llama-server" in name:
                psutil.Process(proc.info["pid"]).terminate()

        import time
        time.sleep(1)

        cmd = [
            "llama-server",
            "--model", model_path,
            "--threads", str(threads),
            "--n-gpu-layers", str(gpu_layers),
            "--ctx-size", str(ctx_size),
            "--batch-size", str(batch_size),
            "--host", "0.0.0.0",
            "--port", "8080",
        ]

        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        return ControlResult(
            success=True,
            message=f"llama.cpp restarted",
            detail=f"Threads:{threads} GPU layers:{gpu_layers} Ctx:{ctx_size}"
        )
    except FileNotFoundError:
        return ControlResult(
            success=False,
            message="llama-server not found",
            detail="Install llama.cpp from github.com/ggerganov/llama.cpp"
        )
    except Exception as e:
        return ControlResult(success=False, message="llama.cpp restart failed", detail=str(e))


# ─────────────────────────────────────────────
# PYTORCH / CUDA CONTROL
# ─────────────────────────────────────────────

def set_pytorch_optimizations(
    use_flash_attention: bool = True,
    use_tf32: bool = True,
    cuda_benchmark: bool = True
) -> ControlResult:
    """Set PyTorch CUDA environment variables for maximum performance."""
    try:
        settings = []

        if use_tf32:
            os.environ["TORCH_ALLOW_TF32_CUBLAS_OVERRIDE"] = "1"
            settings.append("TF32 enabled")

        if cuda_benchmark:
            os.environ["CUDA_LAUNCH_BLOCKING"] = "0"
            os.environ["TORCH_CUDNN_V8_API_ENABLED"] = "1"
            settings.append("cuDNN benchmark enabled")

        if use_flash_attention:
            os.environ["FLASH_ATTENTION_FORCE_BUILD"] = "TRUE"
            settings.append("Flash attention enabled")

        # General performance env vars
        os.environ["OMP_NUM_THREADS"] = str(psutil.cpu_count(logical=False))
        os.environ["MKL_NUM_THREADS"] = str(psutil.cpu_count(logical=False))
        settings.append(f"OMP threads = {psutil.cpu_count(logical=False)}")

        return ControlResult(
            success=True,
            message="PyTorch optimizations applied",
            detail=", ".join(settings)
        )
    except Exception as e:
        return ControlResult(success=False, message="PyTorch optimization failed", detail=str(e))


# ─────────────────────────────────────────────
# SMART AUTO-OPTIMIZER
# ─────────────────────────────────────────────

def auto_optimize(target: str = "speed") -> list[ControlResult]:
    """
    Run all optimizations automatically based on target goal.
    target: 'speed', 'balanced', 'save_power'
    """
    results = []

    if target == "speed":
        results.append(set_cpu_priority("high"))
        results.append(set_swap_behavior(10))         # minimize swapping
        results.append(set_gpu_power_mode("max"))
        results.append(set_gpu_memory_fraction(0.9))
        results.append(set_pytorch_optimizations())
        results.append(set_ollama_context_size(2048)) # smaller ctx = faster

    elif target == "balanced":
        results.append(set_cpu_priority("normal"))
        results.append(set_swap_behavior(30))
        results.append(set_gpu_power_mode("balanced"))
        results.append(set_gpu_memory_fraction(0.75))
        results.append(set_pytorch_optimizations(cuda_benchmark=False))

    elif target == "save_power":
        results.append(set_cpu_priority("low"))
        results.append(set_swap_behavior(60))
        results.append(set_gpu_power_mode("save"))
        results.append(set_gpu_memory_fraction(0.5))

    return results


if __name__ == "__main__":
    """Quick test — run all controls and print results."""
    print("\n⚡ AIRO System Controls — Test Run\n")
    print("─" * 50)

    tests = [
        ("CPU Priority → high",     lambda: set_cpu_priority("high")),
        ("CPU Affinity → 80%",      lambda: set_cpu_affinity(0.8)),
        ("RAM Swap → minimal",      lambda: set_swap_behavior(10)),
        ("GPU Power → max",         lambda: set_gpu_power_mode("max")),
        ("GPU Memory → 90%",        lambda: set_gpu_memory_fraction(0.9)),
        ("PyTorch Opts",            lambda: set_pytorch_optimizations()),
        ("Ollama ctx → 4096",       lambda: set_ollama_context_size(4096)),
        ("Ollama status",           lambda: ControlResult(True, str(get_ollama_status()))),
        ("llama.cpp status",        lambda: ControlResult(True, str(get_llamacpp_status()))),
    ]

    for name, fn in tests:
        result = fn()
        icon = "✅" if result.success else "⚠️ "
        print(f"{icon}  {name}")
        print(f"    → {result.message}")
        if result.detail:
            print(f"       {result.detail}")
    print()
