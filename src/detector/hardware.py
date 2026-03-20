"""
Hardware Detector Module
Automatically detects CPU, RAM, GPU, and SSD specifications.
"""

import platform
import os
import json
import subprocess
from dataclasses import dataclass, asdict
from typing import Optional

@dataclass
class CPUInfo:
    brand: str
    cores_physical: int
    cores_logical: int
    frequency_max_ghz: float
    architecture: str

@dataclass
class RAMInfo:
    total_gb: float
    available_gb: float

@dataclass
class GPUInfo:
    name: str
    vram_gb: float
    vendor: str  # nvidia / amd / apple / intel / none

@dataclass
class StorageInfo:
    total_gb: float
    free_gb: float
    type: str  # SSD / HDD / NVMe / Unknown

@dataclass
class HardwareProfile:
    cpu: CPUInfo
    ram: RAMInfo
    gpu: Optional[GPUInfo]
    storage: StorageInfo
    os: str
    python_version: str

    def to_dict(self):
        return asdict(self)

    def to_json(self):
        return json.dumps(self.to_dict(), indent=2)


def detect_cpu() -> CPUInfo:
    """Detect CPU information using psutil and platform."""
    try:
        import psutil
        freq = psutil.cpu_freq()
        freq_max = round(freq.max / 1000, 2) if freq else 0.0
        return CPUInfo(
            brand=platform.processor() or "Unknown",
            cores_physical=psutil.cpu_count(logical=False) or 1,
            cores_logical=psutil.cpu_count(logical=True) or 1,
            frequency_max_ghz=freq_max,
            architecture=platform.machine()
        )
    except ImportError:
        return CPUInfo(
            brand=platform.processor() or "Unknown",
            cores_physical=os.cpu_count() or 1,
            cores_logical=os.cpu_count() or 1,
            frequency_max_ghz=0.0,
            architecture=platform.machine()
        )


def detect_ram() -> RAMInfo:
    """Detect RAM using psutil."""
    try:
        import psutil
        mem = psutil.virtual_memory()
        return RAMInfo(
            total_gb=round(mem.total / (1024 ** 3), 2),
            available_gb=round(mem.available / (1024 ** 3), 2)
        )
    except ImportError:
        return RAMInfo(total_gb=0.0, available_gb=0.0)


def detect_gpu() -> Optional[GPUInfo]:
    """Detect GPU — supports NVIDIA, AMD, and Apple Silicon."""

    # Try NVIDIA first (nvidia-smi)
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            lines = result.stdout.strip().split("\n")
            name, vram_mb = lines[0].split(", ")
            return GPUInfo(
                name=name.strip(),
                vram_gb=round(float(vram_mb.strip()) / 1024, 2),
                vendor="nvidia"
            )
    except Exception:
        pass

    # Try AMD (rocm-smi)
    try:
        result = subprocess.run(
            ["rocm-smi", "--showproductname", "--showmeminfo", "vram"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            return GPUInfo(name="AMD GPU", vram_gb=0.0, vendor="amd")
    except Exception:
        pass

    # Try Apple Silicon
    if platform.system() == "Darwin" and platform.machine() == "arm64":
        try:
            result = subprocess.run(
                ["system_profiler", "SPHardwareDataType"],
                capture_output=True, text=True, timeout=5
            )
            if "Apple M" in result.stdout:
                chip = "Apple Silicon (M-series)"
                # Unified memory — estimate based on total RAM
                import psutil
                mem_gb = round(psutil.virtual_memory().total / (1024 ** 3), 2)
                return GPUInfo(name=chip, vram_gb=mem_gb, vendor="apple")
        except Exception:
            pass

    return None  # No GPU detected


def detect_storage() -> StorageInfo:
    """Detect storage info for the main drive."""
    try:
        import psutil
        disk = psutil.disk_usage("/")
        total_gb = round(disk.total / (1024 ** 3), 2)
        free_gb = round(disk.free / (1024 ** 3), 2)

        # Attempt to detect SSD vs HDD (Linux only)
        drive_type = "Unknown"
        try:
            with open("/sys/block/sda/queue/rotational") as f:
                rotational = f.read().strip()
                drive_type = "HDD" if rotational == "1" else "SSD/NVMe"
        except Exception:
            drive_type = "SSD"  # Safe assumption for modern hardware

        return StorageInfo(total_gb=total_gb, free_gb=free_gb, type=drive_type)
    except ImportError:
        return StorageInfo(total_gb=0.0, free_gb=0.0, type="Unknown")


def detect_all() -> HardwareProfile:
    """Run full hardware detection and return a HardwareProfile."""
    import sys
    return HardwareProfile(
        cpu=detect_cpu(),
        ram=detect_ram(),
        gpu=detect_gpu(),
        storage=detect_storage(),
        os=f"{platform.system()} {platform.release()}",
        python_version=sys.version.split()[0]
    )


if __name__ == "__main__":
    profile = detect_all()
    print(profile.to_json())
