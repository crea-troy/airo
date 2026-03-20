"""
Workload Optimizer
Maps hardware profile to AI workload recommendations and efficiency configs.
"""

from dataclasses import dataclass
from typing import List, Dict
from detector.hardware import HardwareProfile


@dataclass
class WorkloadRecommendation:
    name: str
    feasible: bool
    efficiency_percent: int
    notes: str
    suggested_config: Dict


@dataclass
class OptimizationReport:
    hardware_summary: str
    recommendations: List[WorkloadRecommendation]
    suggested_framework: str
    cpu_allocation: int       # cores to dedicate
    ram_allocation_gb: float  # GB to dedicate
    gpu_allocation_gb: float  # VRAM GB to dedicate


def analyze(profile: HardwareProfile, use_fraction: float = 0.8) -> OptimizationReport:
    """
    Given a hardware profile and desired use fraction (0.0 - 1.0),
    produce an optimization report with workload recommendations.
    """
    cpu_cores = int(profile.cpu.cores_logical * use_fraction)
    ram_gb = round(profile.ram.available_gb * use_fraction, 1)
    vram_gb = round(profile.gpu.vram_gb * use_fraction, 1) if profile.gpu else 0.0

    recommendations = []

    # --- LLM Inference (e.g., Llama 3 8B) ---
    llm_feasible = ram_gb >= 6 or vram_gb >= 6
    llm_efficiency = min(100, int((ram_gb / 8) * 100)) if not vram_gb else min(100, int((vram_gb / 8) * 100))
    recommendations.append(WorkloadRecommendation(
        name="LLM Inference (7B model, e.g. Llama 3)",
        feasible=llm_feasible,
        efficiency_percent=llm_efficiency,
        notes="Needs ~6GB RAM or VRAM minimum. GPU strongly preferred." if llm_feasible
              else "Not enough RAM/VRAM. Need at least 6GB free.",
        suggested_config={
            "backend": "llama.cpp" if not vram_gb else "ollama",
            "threads": cpu_cores,
            "ctx_size": 2048 if ram_gb < 12 else 4096,
            "gpu_layers": 0 if not vram_gb else 32
        }
    ))

    # --- LLM Training (LoRA fine-tuning) ---
    lora_feasible = (ram_gb >= 12 or vram_gb >= 8)
    recommendations.append(WorkloadRecommendation(
        name="LLM Fine-tuning (LoRA, small model)",
        feasible=lora_feasible,
        efficiency_percent=min(100, int((vram_gb / 16) * 100)) if vram_gb else 20,
        notes="Requires GPU with 8GB+ VRAM for reasonable speed. CPU-only is very slow." if lora_feasible
              else "Not feasible without a GPU with 8GB+ VRAM.",
        suggested_config={
            "framework": "unsloth" if vram_gb >= 8 else "transformers",
            "batch_size": 1,
            "gradient_checkpointing": True,
            "fp16": vram_gb > 0
        }
    ))

    # --- Image Generation (Stable Diffusion) ---
    sd_feasible = ram_gb >= 8 or vram_gb >= 4
    recommendations.append(WorkloadRecommendation(
        name="Image Generation (Stable Diffusion)",
        feasible=sd_feasible,
        efficiency_percent=min(100, int((vram_gb / 8) * 100)) if vram_gb else 30,
        notes="GPU with 4GB+ VRAM is ideal. CPU-only is slow but possible.",
        suggested_config={
            "backend": "diffusers",
            "device": "cuda" if vram_gb >= 4 else "cpu",
            "dtype": "float16" if vram_gb >= 4 else "float32",
            "enable_attention_slicing": vram_gb < 8
        }
    ))

    # --- Distributed Multi-node AI ---
    distributed_feasible = cpu_cores >= 4 and ram_gb >= 8
    recommendations.append(WorkloadRecommendation(
        name="Distributed AI (multi-machine cluster)",
        feasible=distributed_feasible,
        efficiency_percent=min(100, int((cpu_cores / 8) * 100)),
        notes="This machine can participate in a Ray cluster. More nodes = more power.",
        suggested_config={
            "framework": "ray",
            "num_cpus": cpu_cores,
            "num_gpus": 1 if vram_gb > 0 else 0,
            "memory_gb": ram_gb,
            "object_store_memory_gb": round(ram_gb * 0.3, 1)
        }
    ))

    # Choose best framework
    if vram_gb >= 8:
        framework = "PyTorch + CUDA (GPU-accelerated)"
    elif vram_gb > 0:
        framework = "Ollama (GPU-assisted inference)"
    elif ram_gb >= 16:
        framework = "llama.cpp (CPU optimized)"
    else:
        framework = "llama.cpp with aggressive quantization (Q4)"

    summary = (
        f"CPU: {profile.cpu.cores_logical} logical cores @ {profile.cpu.frequency_max_ghz} GHz | "
        f"RAM: {profile.ram.total_gb} GB ({ram_gb} GB allocated) | "
        f"GPU: {profile.gpu.name} ({vram_gb} GB VRAM allocated)" if profile.gpu
        else f"CPU: {profile.cpu.cores_logical} logical cores | RAM: {profile.ram.total_gb} GB | No GPU"
    )

    return OptimizationReport(
        hardware_summary=summary,
        recommendations=recommendations,
        suggested_framework=framework,
        cpu_allocation=cpu_cores,
        ram_allocation_gb=ram_gb,
        gpu_allocation_gb=vram_gb
    )
