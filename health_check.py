"""
windows-system-health-checker
------------------------------
Technician-facing tool that captures a point-in-time snapshot of a Windows
machine's health: CPU, memory, disk, top processes, running services, and
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
import datetime
import io
import os
import platform
import sys

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


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------

def build_report():
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = []

    def add(text=""):
        lines.append(text)

    add(separator())
    add("  WINDOWS SYSTEM HEALTH REPORT")
    add(f"  Generated: {now}")
    add(separator())

    # System info
    add()
    add("SYSTEM INFORMATION")
    add(separator("-"))
    for k, v in get_system_info().items():
        add(f"  {k:<20} {v}")

    # CPU
    add()
    add("CPU")
    add(separator("-"))
    cpu = get_cpu()
    add(f"  Physical Cores       {cpu['Physical Cores']}")
    add(f"  Logical Cores        {cpu['Logical Cores']}")
    add(f"  Current Frequency    {cpu['Current Freq']}")
    add(f"  Usage                {bar(cpu['Usage (1s avg)'])}")

    # Memory
    add()
    add("MEMORY")
    add(separator("-"))
    mem = get_memory()
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
    for d in get_disks():
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
    for p in get_top_processes(10):
        add(f"  {p['pid']:<8} {(p['cpu_percent'] or 0):<8.1f} "
            f"{(p['memory_percent'] or 0):<8.1f} {p['name']}")

    # Services (Windows only)
    svcs = get_services()
    if svcs:
        add()
        add("RUNNING SERVICES (sample, A-Z)")
        add(separator("-"))
        for name in svcs:
            add(f"  • {name}")

    add()
    add(separator())
    add("  END OF REPORT")
    add(separator())

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Windows System Health Checker — generates a technician report."
    )
    parser.add_argument(
        "--console", action="store_true",
        help="Print report to console only (skip file output)."
    )
    parser.add_argument(
        "--file", action="store_true",
        help="Write report to file only (skip console output)."
    )
    args = parser.parse_args()

    report = build_report()

    show_console = not args.file      # default: show console unless --file
    write_file   = not args.console   # default: write file unless --console

    if show_console:
        print(report)

    if write_file:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"health_report_{timestamp}.txt"
        filepath = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(report)
        if show_console:
            print(f"\n[✓] Report saved to: {filepath}")
        else:
            print(f"[✓] Report saved to: {filepath}")


if __name__ == "__main__":
    main()
