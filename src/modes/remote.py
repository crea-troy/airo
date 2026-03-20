"""
AIRO Mode: Remote Cluster
SSH-based agent that collects stats from a remote machine
and sends them back to the local AIRO dashboard.

On the REMOTE machine, run:
    python -m airo.agent --host 0.0.0.0 --port 7070

On your LOCAL machine:
    airo remote add <hostname>
"""

import json
import socket
import threading
import time
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class RemoteNodeStats:
    host: str
    connected: bool
    cpu_percent: float = 0.0
    ram_percent: float = 0.0
    ram_used_gb: float = 0.0
    ram_total_gb: float = 0.0
    gpu_percent: float = 0.0
    gpu_vram_used_gb: float = 0.0
    gpu_vram_total_gb: float = 0.0
    cpu_temp: float = 0.0
    model_name: str = "Unknown"
    tokens_per_sec: float = 0.0
    latency_ms: float = 0.0


class RemoteAgent:
    """
    Runs on the REMOTE machine.
    Collects hardware stats and serves them over a simple TCP socket.
    """

    def __init__(self, host: str = "0.0.0.0", port: int = 7070):
        self.host = host
        self.port = port

    def collect_stats(self) -> dict:
        import psutil, subprocess, platform
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

        return {
            "cpu_percent": cpu,
            "ram_percent": mem.percent,
            "ram_used_gb": round(mem.used / (1024**3), 1),
            "ram_total_gb": round(mem.total / (1024**3), 1),
            "gpu_percent": gpu_pct,
            "gpu_vram_used_gb": gpu_used,
            "gpu_vram_total_gb": gpu_total,
        }

    def serve(self):
        """Start the agent server."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((self.host, self.port))
            s.listen(5)
            print(f"AIRO agent listening on {self.host}:{self.port}")
            while True:
                conn, addr = s.accept()
                with conn:
                    stats = self.collect_stats()
                    conn.sendall(json.dumps(stats).encode() + b"\n")


class RemoteClient:
    """
    Runs on the LOCAL machine.
    Connects to a RemoteAgent and fetches stats.
    """

    def __init__(self, host: str, port: int = 7070, timeout: float = 3.0):
        self.host = host
        self.port = port
        self.timeout = timeout

    def fetch(self) -> Optional[RemoteNodeStats]:
        try:
            start = time.time()
            with socket.create_connection((self.host, self.port),
                                          timeout=self.timeout) as s:
                data = b""
                while True:
                    chunk = s.recv(4096)
                    if not chunk:
                        break
                    data += chunk
                    if b"\n" in data:
                        break
            latency_ms = round((time.time() - start) * 1000, 1)
            stats = json.loads(data.decode().strip())
            stats["host"] = self.host
            stats["connected"] = True
            stats["latency_ms"] = latency_ms
            return RemoteNodeStats(**stats)
        except Exception as e:
            return RemoteNodeStats(host=self.host, connected=False)


class ClusterMonitor:
    """
    Monitors multiple remote nodes simultaneously.
    """

    def __init__(self):
        self.clients: dict[str, RemoteClient] = {}
        self._stats: dict[str, RemoteNodeStats] = {}
        self._running = False

    def add_node(self, host: str, port: int = 7070):
        self.clients[host] = RemoteClient(host, port)

    def remove_node(self, host: str):
        self.clients.pop(host, None)
        self._stats.pop(host, None)

    def poll_once(self):
        for host, client in self.clients.items():
            stats = client.fetch()
            if stats:
                self._stats[host] = stats

    def start_polling(self, interval: float = 2.0):
        self._running = True
        def loop():
            while self._running:
                self.poll_once()
                time.sleep(interval)
        threading.Thread(target=loop, daemon=True).start()

    def stop(self):
        self._running = False

    def get_stats(self) -> dict[str, RemoteNodeStats]:
        return dict(self._stats)

    def all_connected(self) -> bool:
        return all(s.connected for s in self._stats.values())


if __name__ == "__main__":
    import sys
    if "--serve" in sys.argv:
        agent = RemoteAgent()
        agent.serve()
    else:
        print("Usage: python remote.py --serve")
        print("       Starts the AIRO agent on this machine.")
        print("       Then connect from another machine with: airo remote add <this-host>")
