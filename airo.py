#!/usr/bin/env python3
"""
AIRO - AI Resource Optimizer
Usage:
    python airo.py          # terminal dashboard
    python airo.py web      # web UI at http://localhost:7070
    python airo.py detect   # show hardware
    python airo.py optimize # show recommendations
"""
import sys, os, subprocess
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "src"))

def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "dashboard"

    if cmd in ("dashboard", "terminal"):
        from dashboard import run
        run()

    elif cmd == "web":
        server = os.path.join(ROOT, "web", "server.py")
        subprocess.run([sys.executable, server])

    elif cmd == "detect":
        from detector.hardware import detect_all
        print(detect_all().to_json())

    elif cmd == "optimize":
        from detector.hardware import detect_all
        from optimizer.workload import analyze
        r = analyze(detect_all())
        print(f"\n  Framework: {r.suggested_framework}")
        for rec in r.recommendations:
            print(f"  {'OK' if rec.feasible else 'NO'} {rec.name} — {rec.notes}")
        print()

    else:
        print(f"\n  Unknown command: {cmd}")
        print("  Usage: python airo.py [web|terminal|detect|optimize]\n")

if __name__ == "__main__":
    main()
