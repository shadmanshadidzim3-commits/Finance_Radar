"""Diagnostic: prove the scheduled task can find everything it needs.

Task Scheduler gives a process a different environment from the terminal you
were typing in, so a pipeline that works by hand can still fail every night at
20:30 without saying anything. This runs under the real scheduled-task
conditions and writes what it found to logs/probe.txt.

    powershell -ExecutionPolicy Bypass -File .\install_schedule.ps1   # then
    Start-ScheduledTask -TaskName "FinanceRadar Probe"
"""

import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

root = Path(__file__).parent
out = root / "logs" / "probe.txt"
out.parent.mkdir(exist_ok=True)

lines = [f"probe run at {datetime.now():%Y-%m-%d %H:%M:%S}",
         f"python      : {sys.executable}",
         f"cwd         : {os.getcwd()}",
         f"user        : {os.environ.get('USERNAME')}"]

for exe in ("claude", "claude.cmd", "gemini.cmd", "node"):
    lines.append(f"which {exe:12}: {shutil.which(exe) or 'NOT FOUND'}")

npm = [p for p in os.environ.get("PATH", "").split(";") if "npm" in p.lower()]
lines.append(f"npm on PATH : {npm or 'NO'}")

sys.path.insert(0, str(root))
try:
    from radar import engine
    for cls in (engine.ClaudeCLIEngine, engine.GeminiCLIEngine):
        e = cls()
        lines.append(f"engine {e.name:12}: available={e.available()} exe={e.exe}")
except Exception as e:
    lines.append(f"engine import FAILED: {type(e).__name__}: {e}")

# The real test: can we actually get a reply out of the model?
try:
    from radar import engine
    e = engine.ClaudeCLIEngine()
    if e.available():
        reply = e.run("Reply with exactly one word.", "Say READY.")
        lines.append(f"live call   : OK -> {reply.strip()[:60]!r}")
    else:
        lines.append("live call   : SKIPPED (claude not available)")
except Exception as e:
    lines.append(f"live call   : FAILED {type(e).__name__}: {str(e)[:200]}")

out.write_text("\n".join(lines) + "\n", encoding="utf8")
print("\n".join(lines))
