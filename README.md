# Windows First-Response System Snapshot

A small, explainable Windows CLI that captures a point-in-time support snapshot: system version, one-second CPU sample, memory, disks, top processes, and a sample of running services. Configurable thresholds produce observations for follow-up; they are not diagnoses or proof of good or poor health.

## Run it

```powershell
python -m pip install -r requirements.txt

# Console only; does not write a report directory
python .\health_check.py --console

# Redacted text and JSON files under an explicit directory
python .\health_check.py --file --json --safe-share --output .\reports

# Optional observation thresholds
python .\health_check.py --console --cpu-threshold 80 --ram-threshold 85 --disk-threshold 90
```

By default the tool prints to the console and writes a timestamped text report. `--file` suppresses console report output; `--console` suppresses the text file. `--json` adds a JSON snapshot.

## How to interpret it

- CPU is a one-second sample. A threshold crossing may justify repeated measurement; it is not a root cause.
- Memory and disk percentages are point-in-time measurements. Static thresholds do not establish user impact.
- Process CPU values are short samples and can change immediately.
- Missing or inaccessible measurements remain unavailable; the tool does not invent a healthy value.
- A snapshot with no threshold crossings is not a clean bill of health.

Use the output to record a starting state, compare an authorized before/after test, and decide what evidence to collect next.

## Privacy and safe sharing

Reports can contain hostname, processor, storage paths, process names/PIDs, and service names. Depending on future extensions or surrounding logs, usernames, IP addresses, installed-software names, internal domains, and other identifiers may also appear. Treat raw reports as sensitive support data.

`--safe-share` replaces hostname, processor, disk/mount, process/PID, and service identifiers in both text and JSON output. It is a narrow redaction aid, not data-loss prevention: manually review every file before attaching it to a ticket or publishing it. The tool does not currently collect IP addresses, usernames, or an installed-software inventory.

## Test and evidence boundary

```powershell
python -m unittest discover -s tests -v
```

Tests cover unavailable measurements, configurable thresholds as observations, safe-share redaction, report paths, and report rendering. A local `--safe-share` run can prove collection on the current authorized machine at that moment only.

[`evidence/README.md`](evidence/README.md) defines the evidence required for a future controlled high-CPU or low-disk before/after lab. It contains no fabricated result.

## Limits

- This is a first-response snapshot, not continuous monitoring, benchmarking, asset management, or endpoint administration.
- It does not determine why a process is busy, why storage is full, whether malware is present, or whether a system is suitable for production.
- Windows service collection depends on platform support and permissions.
- No real report is committed; the examples in this README are illustrative.
