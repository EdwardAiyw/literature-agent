from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


TASK_NAMES = ("Literature Agent Local", "Literature Agent Daily")


def _powershell(script: str, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    if os.name != "nt":
        raise RuntimeError("Windows Task Scheduler is only available on Windows")
    return subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )


def scheduler_status() -> dict:
    if os.name != "nt":
        return {"supported": False, "tasks": []}
    names = ",".join("'" + name.replace("'", "''") + "'" for name in TASK_NAMES)
    command = (
        f"Get-ScheduledTask -TaskName {names} -ErrorAction SilentlyContinue | "
        "ForEach-Object { $i = $_ | Get-ScheduledTaskInfo; [pscustomobject]@{ "
        "name=$_.TaskName; state=[string]$_.State; last_run=$(if($i.LastRunTime){$i.LastRunTime.ToString('o')}else{''}); "
        "last_result=$i.LastTaskResult; next_run=$(if($i.NextRunTime){$i.NextRunTime.ToString('o')}else{''}) } } | ConvertTo-Json -Compress"
    )
    try:
        result = _powershell(command, timeout=10)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "supported": True,
            "tasks": [],
            "error": f"{type(exc).__name__}: Windows Task Scheduler status is unavailable",
        }
    if result.returncode != 0:
        return {"supported": True, "tasks": [], "error": result.stderr.strip() or result.stdout.strip()}
    raw = result.stdout.strip()
    try:
        items = [] if not raw else json.loads(raw)
    except json.JSONDecodeError:
        return {"supported": True, "tasks": [], "error": "Windows Task Scheduler returned invalid JSON"}
    if isinstance(items, dict):
        items = [items]
    return {"supported": True, "tasks": items}


def run_scheduler_action(project_root: Path, action: str) -> dict:
    if action not in {"register", "repair", "disable"}:
        raise ValueError("Unsupported scheduler action")
    startup = project_root / "scripts" / "register-local-startup.ps1"
    daily = project_root / "scripts" / "register-windows-task.ps1"
    for path in (startup, daily):
        if not path.is_file():
            raise RuntimeError(f"Scheduler helper is missing: {path}")
    unregister = " -Unregister" if action == "disable" else ""
    for path in (startup, daily):
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(path), *(["-Unregister"] if unregister else [])],
            cwd=project_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or f"Failed to run {path.name}")
    return scheduler_status()
