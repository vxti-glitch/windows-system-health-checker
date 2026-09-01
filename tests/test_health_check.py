import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import health_check


class HealthCheckTests(unittest.TestCase):
    def test_thresholds_are_reported_as_observations_not_diagnoses(self):
        observations = health_check.build_observations(
            {"Usage (1s avg)": 91.0},
            {"ram_pct": 92.0},
            [{"device": "C:", "pct": 88.0}],
        )

        self.assertEqual(len(observations), 3)
        self.assertTrue(any("one-second cpu sample" in item.lower() for item in observations))
        self.assertTrue(any("not a diagnosis" in item.lower() for item in observations))
        self.assertFalse(any("health" in item.lower() for item in observations))

    def test_configurable_thresholds_change_observations(self):
        metrics = ({"Usage (1s avg)": 70.0}, {"ram_pct": 70.0}, [{"device": "C:", "pct": 70.0}])
        self.assertEqual(
            health_check.build_observations(*metrics),
            ["No configured observation threshold was crossed in this point-in-time snapshot."],
        )
        observations = health_check.build_observations(
            *metrics,
            thresholds={"cpu_percent": 60.0, "ram_percent": 60.0, "disk_percent": 60.0},
        )
        self.assertEqual(len(observations), 3)

    def test_unavailable_sensors_are_explicit(self):
        observations = health_check.build_observations(
            {"Usage (1s avg)": None}, {"ram_pct": None}, []
        )
        self.assertTrue(any("CPU sample unavailable" in item for item in observations))
        self.assertTrue(any("RAM measurement unavailable" in item for item in observations))
        self.assertTrue(any("Disk measurements unavailable" in item for item in observations))

    def test_disk_permission_failure_is_skipped_without_inventing_data(self):
        partition = SimpleNamespace(device="C:", mountpoint="C:\\", fstype="NTFS")
        with (
            mock.patch.object(health_check.psutil, "disk_partitions", return_value=[partition]),
            mock.patch.object(health_check.psutil, "disk_usage", side_effect=PermissionError("denied")),
        ):
            self.assertEqual(health_check.get_disks(), [])

    def test_safe_share_redacts_identifying_values_without_mutating_source(self):
        snapshot = {
            "system": {"Hostname": "PRIVATE-PC", "Processor": "Specific CPU"},
            "disks": [{"device": "C:", "mountpoint": "C:\\Users\\Private"}],
            "top_processes": [{"pid": 42, "name": "private-app.exe"}],
            "services": ["PrivateService"],
            "observations": ["Disk use on C: was 90.0%, above the threshold."],
        }
        redacted = health_check.safe_share_snapshot(snapshot)
        rendered = str(redacted)
        self.assertNotIn("PRIVATE-PC", rendered)
        self.assertNotIn("private-app.exe", rendered)
        self.assertNotIn("PrivateService", rendered)
        self.assertNotIn("C:\\Users\\Private", rendered)
        self.assertEqual(snapshot["system"]["Hostname"], "PRIVATE-PC")

    def test_build_report_uses_snapshot(self):
        snapshot = {
            "generated": "2026-08-23 12:00:00",
            "sample_scope": "Point-in-time snapshot; CPU usage is sampled for one second. This is not a diagnosis.",
            "observations": ["No configured observation threshold was crossed in this point-in-time snapshot."],
            "system": {"Hostname": "WS-01"},
            "cpu": {
                "Physical Cores": 4,
                "Logical Cores": 8,
                "Current Freq": "3000 MHz",
                "Usage (1s avg)": 10.0,
            },
            "memory": {
                "ram_total": 16 * 1024**3,
                "ram_used": 4 * 1024**3,
                "ram_avail": 12 * 1024**3,
                "ram_pct": 25.0,
                "swap_total": 0,
                "swap_used": 0,
                "swap_pct": 0,
            },
            "disks": [],
            "top_processes": [{"pid": 1, "cpu_percent": 0.0, "memory_percent": 1.0, "name": "init"}],
            "services": [],
        }

        report = health_check.build_report(snapshot)
        self.assertIn("THRESHOLD OBSERVATIONS", report)
        self.assertIn("not a diagnosis", report.lower())
        self.assertIn("WS-01", report)

    def test_report_paths_stay_under_requested_output_directory(self):
        snapshot = {
            "generated": "2026-08-23 12:00:00", "observations": [], "system": {},
            "cpu": {"Physical Cores": 0, "Logical Cores": 0, "Current Freq": "N/A", "Usage (1s avg)": 0},
            "memory": {"ram_total": 0, "ram_used": 0, "ram_avail": 0, "ram_pct": 0, "swap_total": 0, "swap_used": 0, "swap_pct": 0},
            "disks": [], "top_processes": [], "services": [],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "nested" / "reports"
            paths = health_check.write_snapshot_outputs(
                snapshot, output, write_text=True, write_json=True, timestamp="20260823_120000"
            )
            self.assertEqual(set(paths), {"text", "json"})
            self.assertTrue(all(path.parent == output.resolve() for path in paths.values()))
            self.assertTrue(all(path.is_file() for path in paths.values()))


if __name__ == "__main__":
    unittest.main()
