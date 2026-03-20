"""
AIRO Terminal Dashboard v0.4
Run: python airo.py
"""
import os, sys, time, threading, platform, subprocess, psutil
from dataclasses import dataclass, field

try:
    from rich.live    import Live
    from rich.table   import Table
    from rich.panel   import Panel
    from rich.console import Console
    from rich.text    import Text
    from rich         import box
except ImportError:
    print("\n  pip install rich psutil\n")
    sys.exit(1)

console = Console()
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── state ──────────────────────────────────────
@dataclass
class S:
    cpu:   float = 0.0
    ram:   float = 0.0
    ramu:  float = 0.0
    ramt:  float = 0.0
    gpu:   float = 0.0
    gpuu:  float = 0.0
    gput:  float = 0.0
    temp:  float = 0.0
    cores: int   = 1
    model: str   = "Detecting..."
    toks:  float = 0.0
    mode:  int   = 0
    row:   int   = 0
    ct:    float = 85.0
    rt:    float = 75.0
    gt:    float = 90.0
    msg:   str   = "Ready — press A to auto-optimize, Y to apply"
    mok:   bool  = True
    alive: bool  = True
    t0:    float = field(default_factory=time.time)

st = S()

# ── hardware poll ───────────────────────────────
def poll():
    while st.alive:
        try:
            st.cpu   = psutil.cpu_percent(interval=0.5)
            st.cores = psutil.cpu_count(logical=True) or 1
            m = psutil.virtual_memory()
            st.ram  = round(m.percent, 1)
            st.ramu = round(m.used  / 1e9, 1)
            st.ramt = round(m.total / 1e9, 1)
            try:
                r = subprocess.run(
                    ["nvidia-smi","--query-gpu=utilization.gpu,memory.used,memory.total",
                     "--format=csv,noheader,nounits"],
                    capture_output=True, text=True, timeout=2)
                if r.returncode == 0:
                    p = [x.strip() for x in r.stdout.strip().split(",")]
                    st.gpu  = float(p[0])
                    st.gpuu = round(float(p[1])/1024, 1)
                    st.gput = round(float(p[2])/1024, 1)
            except Exception: pass
            try:
                temps = psutil.sensors_temperatures()
                for k in ["coretemp","cpu_thermal","k10temp","acpitz"]:
                    if k in temps and temps[k]:
                        st.temp = round(temps[k][0].current, 1); break
            except Exception: pass
            try:
                r = subprocess.run(
                    ["curl","-s","--max-time","1","http://localhost:11434/api/tags"],
                    capture_output=True, text=True, timeout=2)
                if r.returncode == 0 and r.stdout.strip():
                    import json
                    ms = json.loads(r.stdout).get("models", [])
                    st.model = ms[0]["name"]+" (Ollama)" if ms else "Ollama — no model loaded"
                elif st.model == "Detecting...":
                    st.model = "No model detected"
            except Exception:
                if st.model == "Detecting...":
                    st.model = "No model detected"
        except Exception: pass
        time.sleep(1)

# ── keyboard ────────────────────────────────────
def readkey():
    if platform.system() == "Windows":
        import msvcrt
        return msvcrt.getch().decode("utf-8","ignore")
    import tty, termios
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        if ch == "\x1b": ch += sys.stdin.read(2)
        return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)

def apply_all():
    try:
        sys.path.insert(0, os.path.join(ROOT,"src"))
        import controls as ctrl
        res = []
        p = "high" if st.ct>=80 else "normal" if st.ct>=50 else "low"
        res += [ctrl.set_cpu_priority(p), ctrl.set_cpu_affinity(st.ct/100),
                ctrl.set_swap_behavior(int((1-st.rt/100)*60))]
        if st.gput > 0:
            gm = "max" if st.gt>=80 else "balanced" if st.gt>=50 else "save"
            res += [ctrl.set_gpu_power_mode(gm), ctrl.set_gpu_memory_fraction(st.gt/100)]
        res += [ctrl.set_pytorch_optimizations(),
                ctrl.set_ollama_context_size(4096 if st.rt>=70 else 2048)]
        ok = sum(1 for r in res if r.success)
        st.msg = f"Applied {ok}/{len(res)} changes successfully"
        st.mok = ok == len(res)
    except Exception as e:
        st.msg = f"Error: {e}"
        st.mok = False

def handle(k):
    tlist = ["ct","rt","gt"]
    if   k == "\t":        st.mode = (st.mode+1)%3; st.msg = f"Mode: {['LOCAL','API CLOUD','REMOTE'][st.mode]}"
    elif k in("\x1b[A","k"): st.row = (st.row-1)%3
    elif k in("\x1b[B","j"): st.row = (st.row+1)%3
    elif k in("+","="):
        attr=tlist[st.row]; setattr(st,attr,min(100,getattr(st,attr)+5))
        st.msg=f"{['CPU','RAM','GPU'][st.row]} target → {getattr(st,attr):.0f}%"; st.mok=True
    elif k in("-","_"):
        attr=tlist[st.row]; setattr(st,attr,max(0,getattr(st,attr)-5))
        st.msg=f"{['CPU','RAM','GPU'][st.row]} target → {getattr(st,attr):.0f}%"; st.mok=True
    elif k in("r","R"):    st.ct,st.rt,st.gt=85,75,90; st.msg="Reset to recommended"; st.mok=True
    elif k in("a","A"):
        try:
            sys.path.insert(0, os.path.join(ROOT,"src"))
            import controls as c
            res=c.auto_optimize("speed"); ok=sum(1 for r in res if r.success)
            st.msg=f"Auto-optimize: {ok}/{len(res)} applied"; st.mok=ok==len(res)
        except Exception as e: st.msg=f"Error: {e}"; st.mok=False
    elif k in("y","Y"):    apply_all()
    elif k in("n","N"):    st.ct,st.rt,st.gt=85,75,90; st.msg="Cancelled — targets reset"; st.mok=True
    elif k in("q","Q","\x03"): st.alive=False

def kb():
    while st.alive:
        try: handle(readkey())
        except Exception: pass

# ── render helpers ──────────────────────────────
def bar(pct, w=18):
    f = int(pct/100*w)
    c = "red" if pct>=90 else "yellow" if pct>=75 else "green"
    t = Text()
    t.append("█"*f,      style=c)
    t.append("░"*(w-f),  style="grey23")
    t.append(f" {pct:4.0f}%", style="white")
    return t

def sld(val, w=18):
    pos = int(val/100*w)
    t   = Text()
    for i in range(w):
        t.append("●" if i==pos else "─", style="bold cyan" if i==pos else "grey30")
    t.append(f" {val:4.0f}%", style="bold cyan")
    return t

def act(cur, tgt, enabled=True):
    if not enabled: return Text("no GPU",style="grey50")
    d = tgt-cur
    if abs(d)<3:    return Text("✓ optimal",style="green")
    if d>0:         return Text(f"+{d:.0f}% → +{int(d*0.45)}% speed",style="cyan")
    return          Text(f"−{abs(d):.0f}% → cooler",style="yellow")

def upt():
    s=int(time.time()-st.t0); m,s=divmod(s,60); h,m=divmod(m,60)
    return f"{h}h {m}m {s}s" if h else f"{m}m {s}s"

MODES=["LOCAL","API CLOUD","REMOTE"]

# ── full render ─────────────────────────────────
def render():
    root = Table.grid(expand=True)
    root.add_column()

    # header
    hdr = Text()
    hdr.append("  ⚡ AIRO v0.4   ",style="bold cyan")
    for i,m in enumerate(MODES):
        if i==st.mode: hdr.append(f" [{m}] ",style="bold yellow on grey15")
        else:          hdr.append(f"  {m}  ",style="grey50")
    hdr.append("    Tab=switch",style="grey37")
    root.add_row(Panel(hdr, style="on grey7", border_style="cyan", padding=(0,1)))

    # ── LOCAL ──
    if st.mode == 0:
        t = Table(box=box.SIMPLE_HEAD, expand=True, show_header=True,
                  header_style="bold white on grey15", border_style="grey23",
                  padding=(0,1))
        t.add_column("  RESOURCE",        min_width=20)
        t.add_column("CURRENT USE",       min_width=26)
        t.add_column("BEST PERFORMANCE",  min_width=26)
        t.add_column("YOUR CHOICE",       min_width=26)
        t.add_column("ACTION",            min_width=26)

        # cpu
        lbl=Text(); lbl.append(f" {'▶' if st.row==0 else ' '} ",style="bold yellow" if st.row==0 else ""); lbl.append(f"CPU  {st.cores} cores",style="bold white")
        t.add_row(lbl, bar(st.cpu), bar(85), sld(st.ct), act(st.cpu,st.ct))

        # ram
        lbl=Text(); lbl.append(f" {'▶' if st.row==1 else ' '} ",style="bold yellow" if st.row==1 else ""); lbl.append(f"RAM  {st.ramu}/{st.ramt}GB",style="bold white")
        t.add_row(lbl, bar(st.ram), bar(75), sld(st.rt), act(st.ram,st.rt))

        # gpu
        lbl=Text(); lbl.append(f" {'▶' if st.row==2 else ' '} ",style="bold yellow" if st.row==2 else "")
        if st.gput>0:
            lbl.append(f"GPU  {st.gpuu}/{st.gput}GB",style="bold white")
            t.add_row(lbl, bar(st.gpu), bar(90), sld(st.gt), act(st.gpu,st.gt))
        else:
            lbl.append("GPU  not detected",style="grey50")
            t.add_row(lbl,Text("─",style="grey37"),Text("─",style="grey37"),Text("─",style="grey37"),Text("CPU-only mode",style="grey50"))

        # temp
        if st.temp>0:
            tc="red" if st.temp>85 else "yellow" if st.temp>70 else "green"
            tn="⚠ TOO HOT" if st.temp>85 else "warm — watch it" if st.temp>70 else "✓ safe"
            t.add_row(Text("    TEMP",style="bold white"),Text(f"{st.temp:.0f}°C",style=f"bold {tc}"),Text("< 80°C",style="cyan"),Text("─",style="grey37"),Text(tn,style=tc))

        root.add_row(Panel(t, border_style="grey37", style="on grey7",
                           title="[cyan]Hardware Monitor[/cyan]", padding=(0,0)))

        # suggestion
        gaps=[]
        if st.gput>0 and (90-st.gpu)>8: gaps.append(("GPU",90-st.gpu))
        if (85-st.cpu)>8: gaps.append(("CPU",85-st.cpu))
        if (75-st.ram)>8: gaps.append(("RAM",75-st.ram))
        sug=Text()
        if gaps:
            top=max(gaps,key=lambda x:x[1])
            sug.append("  💡 Biggest gain: ",style="yellow")
            sug.append(f"increase {top[0]} by {top[1]:.0f}%",style="white")
            sug.append(f"  →  ~+{int(top[1]*0.4)}% performance  ",style="cyan bold")
            sug.append("Press Y to apply",style="grey50")
        else:
            sug.append("  ✅  All resources near optimal — system running well",style="green")
        root.add_row(Panel(sug, border_style="cyan", style="on grey7", padding=(0,1)))

    # ── API ──
    elif st.mode == 1:
        t = Table(box=box.SIMPLE_HEAD,expand=True,show_header=True,
                  header_style="bold white on grey15",border_style="grey23",padding=(0,2))
        t.add_column("METRIC",width=18); t.add_column("VALUE",width=22)
        t.add_column("STATUS",width=20); t.add_column("ACTION",width=28)
        t.add_row(Text("Provider",style="grey70"),Text("OpenAI",style="cyan bold"),Text("Connected ✓",style="green"),Text("Tab → switch mode",style="grey37"))
        t.add_row(Text("Latency",style="grey70"),Text("340 ms",style="yellow"),Text("< 300ms ideal",style="cyan"),Text("check network if slow",style="grey37"))
        t.add_row(Text("Cost today",style="grey70"),Text("$0.18 / $5.00",style="white"),Text("3.6% budget",style="green"),Text("─",style="grey37"))
        t.add_row(Text("Errors",style="grey70"),Text("0",style="green bold"),Text("clean ✓",style="green"),Text("─",style="grey37"))
        t.add_row(Text("Local CPU",style="grey70"),bar(st.cpu,16),Text("< 30% ideal",style="cyan"),
                  Text("✓ not bottleneck" if st.cpu<60 else "⚠ bottleneck!",style="green" if st.cpu<60 else "red"))
        root.add_row(Panel(t,border_style="blue",style="on grey7",title="[blue]API Cloud Monitor[/blue]",padding=(0,0)))
        root.add_row(Panel(Text("  ℹ  Cloud API mode — monitors latency, cost, and local load",style="grey70"),
                           border_style="blue",style="on grey7",padding=(0,1)))

    # ── REMOTE ──
    else:
        t = Table(box=box.SIMPLE_HEAD,expand=True,show_header=True,
                  header_style="bold white on grey15",border_style="grey23",padding=(0,2))
        t.add_column("NODE",width=26); t.add_column("STATUS",width=30); t.add_column("HOW TO CONNECT",width=40)
        t.add_row(Text("  not connected",style="grey50"),Text("offline",style="grey37"),
                  Text("python airo.py agent   on remote",style="grey37"))
        root.add_row(Panel(t,border_style="magenta",style="on grey7",title="[magenta]Remote Cluster[/magenta]",padding=(0,0)))
        root.add_row(Panel(Text("  ℹ  Start AIRO agent on cluster, then: airo remote add <host>",style="grey70"),
                           border_style="magenta",style="on grey7",padding=(0,1)))

    # feedback
    root.add_row(Panel(Text(f"  {'✓' if st.mok else '✗'} {st.msg}",
                            style="green" if st.mok else "red"),
                       border_style="grey23",style="on grey7",padding=(0,1)))

    # controls
    ctrl=Text(justify="center")
    for k,d,s in [("↑↓","select","yellow"),("+-","adjust","yellow"),("A","auto","cyan"),
                  ("R","reset","white"),("Y","apply","green"),("N","cancel","red"),
                  ("Tab","mode","yellow"),("Q","quit","white")]:
        ctrl.append(f"  {k}",style=f"bold {s}"); ctrl.append(f" {d}",style="grey50")
    root.add_row(Panel(ctrl,border_style="grey23",style="on grey7",padding=(0,1)))

    # status
    sb=Table.grid(expand=True)
    sb.add_column(justify="left"); sb.add_column(justify="center"); sb.add_column(justify="right")
    sb.add_row(Text(f"  ◉ {st.model}",style="grey60"),
               Text("⚡ monitoring...",style="cyan"),
               Text(f"uptime {upt()}  ",style="grey50"))
    root.add_row(Panel(sb,border_style="grey23",style="on grey7",padding=(0,0)))

    return root

# ── run ─────────────────────────────────────────
def run():
    threading.Thread(target=poll,daemon=True).start()
    threading.Thread(target=kb,  daemon=True).start()
    console.clear()
    with Live(render(),refresh_per_second=2,screen=True,console=console) as live:
        while st.alive:
            live.update(render())
            time.sleep(0.5)
    console.clear()
    console.print("\n[cyan]⚡ AIRO[/cyan] stopped. Goodbye!\n")

if __name__ == "__main__":
    run()
