"""
windows-system-health-checker
------------------------------
Technician-facing tool that captures a point-in-time first-response snapshot of
CPU, memory, disk, top processes, running services, and
last boot time.  Output is written to both the console and a timestamped
.txt report file in the same directory.

Usage:
    python health_check.py              # console + file report
    python health_check.py --console    # console only
    python health_check.py --file       # file only

Requirements:
    pip install psutil
"""

import argparse
import copy
import datetime
import io
import json
import os
import platform
import sys
from pathlib import Path

# Force UTF-8 output so block characters render correctly on all Windows consoles
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

try:
    import psutil
except ImportError:
    print("[ERROR] psutil is not installed. Run:  pip install psutil")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def separator(char="=", width=60):
    return char * width


def fmt_bytes(n):
    """Return a human-readable byte size string."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def bar(pct, width=20):
    """Return a plain-ASCII progress bar safe on any code page."""
    filled = int(width * pct / 100)
    return "[" + "#" * filled + "-" * (width - filled) + f"] {pct:.1f}%"


# ---------------------------------------------------------------------------
# Data collectors
# ---------------------------------------------------------------------------

def get_system_info():
    boot_time = datetime.datetime.fromtimestamp(psutil.boot_time())
    uptime = datetime.datetime.now() - boot_time
    hours, remainder = divmod(int(uptime.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)

    return {
        "Hostname":        platform.node(),
        "OS":              f"{platform.system()} {platform.release()} ({platform.version()})",
        "Architecture":    platform.machine(),
        "Processor":       platform.processor() or "N/A",
        "Last Boot":       boot_time.strftime("%Y-%m-%d %H:%M:%S"),
        "Uptime":          f"{hours}h {minutes}m {seconds}s",
    }


def get_cpu():
    freq = psutil.cpu_freq()
    return {
        "Physical Cores":  psutil.cpu_count(logical=False),
        "Logical Cores":   psutil.cpu_count(logical=True),
        "Current Freq":    f"{freq.current:.0f} MHz" if freq else "N/A",
        "Usage (1s avg)":  psutil.cpu_percent(interval=1),
    }


def get_memory():
    vm = psutil.virtual_memory()
    sw = psutil.swap_memory()
    return {
        "ram_total":   vm.total,
        "ram_used":    vm.used,
        "ram_avail":   vm.available,
        "ram_pct":     vm.percent,
        "swap_total":  sw.total,
        "swap_used":   sw.used,
        "swap_pct":    sw.percent,
    }


def get_disks():
    disks = []
    for part in psutil.disk_partitions(all=False):
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except PermissionError:
            continue
        disks.append({
            "device":     part.device,
            "mountpoint": part.mountpoint,
            "fstype":     part.fstype,
            "total":      usage.total,
            "used":       usage.used,
            "free":       usage.free,
            "pct":        usage.percent,
        })
    return disks


def get_top_processes(n=10):
    procs = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
        try:
            procs.append(p.info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    # Re-sample CPU (first call always returns 0.0)
    import time; time.sleep(0.5)
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
        try:
            for rec in procs:
                if rec["pid"] == p.pid:
                    rec["cpu_percent"] = p.cpu_percent()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    procs.sort(key=lambda x: x.get("cpu_percent") or 0, reverse=True)
    return procs[:n]


def get_services(limit=15):
    """Return running Windows services sorted by name."""
    if platform.system() != "Windows":
        return []
    svcs = []
    for svc in psutil.win_service_iter():
        try:
            info = svc.as_dict()
            if info["status"] == "running":
                svcs.append(info["name"])
        except Exception:
            pass
    svcs.sort()
    return svcs[:limit]


DEFAULT_THRESHOLDS = {"cpu_percent": 85.0, "ram_percent": 90.0, "disk_percent": 85.0}


def build_observations(cpu, mem, disks, thresholds=None):
    """Describe threshold crossings without diagnosing system health."""
    thresholds = thresholds or DEFAULT_THRESHOLDS
    observations = []

    cpu_value = cpu.get("Usage (1s avg)")
    if cpu_value is None:
        observations.append("CPU sample unavailable; no CPU threshold comparison was made.")
    else:
        cpu_pct = float(cpu_value)
        if cpu_pct >= thresholds["cpu_percent"]:
            observations.append(
                f"One-second CPU sample was {cpu_pct:.1f}%, above the configured "
                f"{thresholds['cpu_percent']:.1f}% observation threshold; this sample is not a diagnosis."
            )

    ram_value = mem.get("ram_pct")
    if ram_value is None:
        observations.append("RAM measurement unavailable; no RAM threshold comparison was made.")
    else:
        ram_pct = float(ram_value)
        if ram_pct >= thresholds["ram_percent"]:
            observations.append(
                f"Point-in-time RAM use was {ram_pct:.1f}%, above the configured "
                f"{thresholds['ram_percent']:.1f}% observation threshold; confirm with repeated measurement."
            )

    for disk in disks:
        disk_pct = float(disk.get("pct") or 0)
        if disk_pct >= thresholds["disk_percent"]:
            observations.append(
                f"Disk use on {disk.get('device', 'unknown disk')} was {disk_pct:.1f}%, above the "
                f"configured {thresholds['disk_percent']:.1f}% observation threshold."
            )

    if not disks:
        observations.append("Disk measurements unavailable; no disk threshold comparison was made.")
    if not observations:
        observations.append("No configured observation threshold was crossed in this point-in-time snapshot.")
    return observations


def safe_share_snapshot(snapshot):
    """Return a copy with identifying host, storage, process, and service values redacted."""
    redacted = copy.deepcopy(snapshot)
    redacted["sharing_mode"] = "safe-share"
    if "Hostname" in redacted.get("system", {}):
        redacted["system"]["Hostname"] = "<redacted-host>"
    if "Processor" in redacted.get("system", {}):
        redacted["system"]["Processor"] = "<redacted-processor>"
    disk_names = [str(disk.get("device", "")) for disk in redacted.get("disks", [])]
    for index, disk in enumerate(redacted.get("disks", []), start=1):
        disk["device"] = f"<disk-{index}>"
        disk["mountpoint"] = f"<mount-{index}>"
    for index, process in enumerate(redacted.get("top_processes", []), start=1):
        process["pid"] = "<redacted>"
        process["name"] = f"<process-{index}>"
    redacted["services"] = [
        f"<service-{index}>" for index, _ in enumerate(redacted.get("services", []), start=1)
    ]
    for index, disk_name in enumerate(disk_names, start=1):
        if disk_name:
            redacted["observations"] = [
                observation.replace(disk_name, f"<disk-{index}>")
                for observation in redacted.get("observations", [])
            ]
    return redacted


# Backward-compatible name for callers; returned strings are observations.
build_health_findings = build_observations


def collect_snapshot(thresholds=None):
    thresholds = thresholds or DEFAULT_THRESHOLDS.copy()
    cpu = get_cpu()
    mem = get_memory()
    disks = get_disks()
    return {
        "generated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "system": get_system_info(),
        "cpu": cpu,
        "memory": mem,
        "disks": disks,
        "top_processes": get_top_processes(10),
        "services": get_services(),
        "sample_scope": "Point-in-time snapshot; CPU usage is sampled for one second. Threshold crossings are observations, not a diagnosis.",
        "thresholds": thresholds,
        "observations": build_observations(cpu, mem, disks, thresholds),
    }


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------

def build_report(snapshot=None):
    snapshot = snapshot or collect_snapshot()
    now = snapshot["generated"]
    lines = []

    def add(text=""):
        lines.append(text)

    add(separator())
    add("  WINDOWS FIRST-RESPONSE SNAPSHOT REPORT")
    add(f"  Generated: {now}")
    add(separator())

    add()
    add("THRESHOLD OBSERVATIONS")
    add(separator("-"))
    add(f"  Scope: {snapshot.get('sample_scope', 'Point-in-time observation; not a diagnosis.')}")
    for observation in snapshot.get("observations", snapshot.get("findings", [])):
        add(f"  - {observation}")

    # System info
    add()
    add("SYSTEM INFORMATION")
    add(separator("-"))
    for k, v in snapshot["system"].items():
        add(f"  {k:<20} {v}")

    # CPU
    add()
    add("CPU")
    add(separator("-"))
    cpu = snapshot["cpu"]
    add(f"  Physical Cores       {cpu['Physical Cores']}")
    add(f"  Logical Cores        {cpu['Logical Cores']}")
    add(f"  Current Frequency    {cpu['Current Freq']}")
    add(f"  Usage                {bar(cpu['Usage (1s avg)'])}")

    # Memory
    add()
    add("MEMORY")
    add(separator("-"))
    mem = snapshot["memory"]
    add(f"  RAM Total            {fmt_bytes(mem['ram_total'])}")
    add(f"  RAM Used             {fmt_bytes(mem['ram_used'])}  {bar(mem['ram_pct'])}")
    add(f"  RAM Available        {fmt_bytes(mem['ram_avail'])}")
    if mem["swap_total"] > 0:
        add(f"  Swap Total           {fmt_bytes(mem['swap_total'])}")
        add(f"  Swap Used            {fmt_bytes(mem['swap_used'])}  {bar(mem['swap_pct'])}")

    # Disks
    add()
    add("DISK USAGE")
    add(separator("-"))
    for d in snapshot["disks"]:
        add(f"  {d['device']} ({d['fstype']})  mount: {d['mountpoint']}")
        add(f"    Total: {fmt_bytes(d['total'])}  "
            f"Used: {fmt_bytes(d['used'])}  "
            f"Free: {fmt_bytes(d['free'])}")
        add(f"    {bar(d['pct'])}")

    # Top processes
    add()
    add("TOP PROCESSES (by CPU %)")
    add(separator("-"))
    add(f"  {'PID':<8} {'CPU%':<8} {'MEM%':<8} NAME")
    for p in snapshot["top_processes"]:
        add(f"  {p['pid']:<8} {(p['cpu_percent'] or 0):<8.1f} "
            f"{(p['memory_percent'] or 0):<8.1f} {p['name']}")

    # Services (Windows only)
    svcs = snapshot["services"]
    if svcs:
        add()
        add("RUNNING SERVICES (sample, A-Z)")
        add(separator("-"))
        for name in svcs:
            add(f"  - {name}")

    add()
    add(separator())
    add("  END OF REPORT")
    add(separator())

    return "\n".join(lines)


def write_snapshot_outputs(snapshot, output_dir, *, write_text=True, write_json=False, timestamp=None):
    """Write selected report formats under an explicit directory and return their paths."""
    output_dir = Path(output_dir).resolve()
    timestamp = timestamp or datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    paths = {}
    if write_text or write_json:
        output_dir.mkdir(parents=True, exist_ok=True)
    if write_text:
        text_path = output_dir / f"system_snapshot_{timestamp}.txt"
        text_path.write_text(build_report(snapshot), encoding="utf-8")
        paths["text"] = text_path
    if write_json:
        json_path = output_dir / f"system_snapshot_{timestamp}.json"
        json_path.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
        paths["json"] = json_path
    return paths


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Capture a Windows first-response system snapshot.")
    parser.add_argument(
        "--console", action="store_true",
        help="Print report to console only (skip file output)."
    )
    parser.add_argument(
        "--file", action="store_true",
        help="Write report to file only (skip console output)."
    )
    parser.add_argument("--json", action="store_true", help="Also write a JSON snapshot.")
    parser.add_argument("--safe-share", action="store_true", help="Redact identifying host, disk, process, and service values.")
    parser.add_argument("--cpu-threshold", type=float, default=85.0)
    parser.add_argument("--ram-threshold", type=float, default=90.0)
    parser.add_argument("--disk-threshold", type=float, default=85.0)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).parent,
        help="Directory for generated reports. Default: script directory.",
    )
    args = parser.parse_args()

    thresholds = {
        "cpu_percent": args.cpu_threshold,
        "ram_percent": args.ram_threshold,
        "disk_percent": args.disk_threshold,
    }
    snapshot = collect_snapshot(thresholds)
    if args.safe_share:
        snapshot = safe_share_snapshot(snapshot)
    report = build_report(snapshot)

    show_console = not args.file      # default: show console unless --file
    write_file   = not args.console   # default: write file unless --console
    if show_console:
        print(report)

    paths = write_snapshot_outputs(snapshot, args.output, write_text=write_file, write_json=args.json)
    if "text" in paths:
        prefix = "\n" if show_console else ""
        print(f"{prefix}[OK] Report saved to: {paths['text']}")
    if "json" in paths:
        print(f"[OK] JSON snapshot saved to: {paths['json']}")


if __name__ == "__main__":
    main()
