# Windows System Health Checker

 [github.com/vxti-glitch](https://github.com/vxti-glitch)

A technician-facing command-line tool that captures a point-in-time health snapshot of a Windows machine and saves it as a timestamped report. Built for the first step of any "my computer is slow" troubleshooting workflow.

---

## Example output

```
============================================================
  WINDOWS SYSTEM HEALTH REPORT
  Generated: 2026-08-03 20:15:42
============================================================

SYSTEM INFORMATION
------------------------------------------------------------
  Hostname             DESKTOP-IV1234
  OS                   Windows 11 10.0.22631
  Last Boot            2026-08-03 09:01:12
  Uptime               11h 14m 30s

CPU
------------------------------------------------------------
  Physical Cores       8
  Logical Cores        16
  Current Frequency    2496 MHz
  Usage                [████████░░░░░░░░░░░░] 42.0%

MEMORY
------------------------------------------------------------
  RAM Total            31.9 GB
  RAM Used             14.2 GB  [█████████░░░░░░░░░░░] 44.5%
  RAM Available        17.7 GB

DISK USAGE
------------------------------------------------------------
  C:\ (NTFS)  mount: C:\
    Total: 476.8 GB  Used: 210.3 GB  Free: 266.5 GB
    [█████████░░░░░░░░░░░] 44.1%

TOP PROCESSES (by CPU %)
------------------------------------------------------------
  PID      CPU%     MEM%     NAME
  4821     8.2      1.1      chrome.exe
  1204     3.1      0.4      explorer.exe
  ...
```

---

## Usage

```bash
# Install dependency
pip install psutil

# Run - prints to console AND saves a timestamped .txt file
python health_check.py

# Console only
python health_check.py --console

# File only
python health_check.py --file

# Also write a JSON snapshot to a specific folder
python health_check.py --json --output reports
```

---

## What it collects

| Section | Data points |
|---|---|
| System | Hostname, OS version, architecture, processor, last boot, uptime |
| CPU | Core count, frequency, live usage % with ASCII bar |
| Memory | Total, used, available RAM + swap |
| Disks | Per-drive: size, used, free, usage % |
| Top Processes | Top 10 by CPU %, with PID and memory % |
| Running Services | Sample of active Windows services (Windows only) |
| Health Summary | Threshold-based warnings for high CPU, high RAM, and low disk headroom |

Run tests:

```bash
python -m unittest discover -s tests -v
```

---

## Help Desk relevance

This tool automates the data-collection step of a "user says their PC is slow" ticket. Instead of manually opening Task Manager, Disk Management, and System Properties one at a time, this script captures everything in a single run and saves a time-stamped file, useful for before/after comparisons and for attaching to a ticket as supporting documentation.

**Skills:** Python · psutil · Windows system diagnostics · CLI tooling

---

*Part of the [vxti-glitch IT Support Portfolio](https://github.com/vxti-glitch)*
