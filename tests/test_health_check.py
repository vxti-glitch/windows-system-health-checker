import unittest

import health_check


class HealthCheckTests(unittest.TestCase):
    def test_build_health_findings_warns_on_thresholds(self):
        findings = health_check.build_health_findings(
            {"Usage (1s avg)": 91.0},
            {"ram_pct": 92.0},
            [{"device": "C:", "pct": 88.0}],
        )

        self.assertEqual(len(findings), 3)
        self.assertTrue(any("High CPU" in item for item in findings))
        self.assertTrue(any("High RAM" in item for item in findings))
        self.assertTrue(any("Low disk" in item for item in findings))

    def test_build_report_uses_snapshot(self):
        snapshot = {
            "generated": "2026-08-23 12:00:00",
            "findings": ["No threshold-based health warnings detected."],
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
        self.assertIn("HEALTH SUMMARY", report)
        self.assertIn("WS-01", report)


if __name__ == "__main__":
    unittest.main()
