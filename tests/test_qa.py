from __future__ import annotations

from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from amd.core import isoformat_utc, load_document, refresh_artifact, save_document


class AMDQATests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.repo_root = Path(__file__).resolve().parents[1]

    def run_cli(self, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        env = dict(os.environ)
        env["PYTHONPATH"] = str(self.repo_root)
        return subprocess.run(
            [sys.executable, "-m", "amd", *args],
            cwd=str(cwd or self.repo_root),
            env=env,
            text=True,
            capture_output=True,
            check=True,
        )

    def test_cli_end_to_end_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            artifact = root / "ops-report.amd.md"

            self.run_cli(
                "init",
                str(artifact),
                "--kind",
                "report",
                "--title",
                "Ops Report",
                "--persistence",
                "ephemeral",
                "--priority",
                "25",
                "--agent",
                "qa",
            )
            self.run_cli(
                "event",
                str(artifact),
                "--agent",
                "qa",
                "--kind",
                "handoff",
                "--summary",
                "qa flow started",
            )
            self.run_cli(
                "caveat",
                str(artifact),
                "--agent",
                "qa",
                "--severity",
                "high",
                "--text",
                "benchmark data is from staging",
            )
            self.run_cli(
                "signal",
                str(artifact),
                "--agent",
                "qa",
                "--metric",
                "latency_ms",
                "--value",
                "123",
                "--unit",
                "ms",
                "--timestamp",
                "2026-03-10T09:00:00Z",
            )
            self.run_cli("set-priority", str(artifact), "70", "--agent", "qa")

            refresh_result = self.run_cli("refresh", str(artifact), "--agent", "qa")
            refresh_summary = json.loads(refresh_result.stdout)
            scan_output = self.run_cli("scan", str(artifact)).stdout

            document = load_document(artifact)
            metadata = document.metadata

            self.assertEqual(metadata["title"], "Ops Report")
            self.assertEqual(metadata["kind"], "report")
            self.assertEqual(metadata["persistence"]["mode"], "ephemeral")
            self.assertEqual(metadata["priority"]["manual"], 70)
            self.assertEqual(metadata["timeseries"]["points"], 1)
            self.assertEqual(len(metadata["caveats"]), 1)
            self.assertGreaterEqual(refresh_summary["priority"], 75)
            self.assertIn("[kind:handoff] qa flow started", document.body)
            self.assertIn("[kind:caveat] caveat added (high)", document.body)
            self.assertIn("[kind:signal] signal recorded for latency_ms", document.body)
            self.assertIn("priority:", scan_output)
            self.assertIn("active_caveats: 1", scan_output)
            self.assertIn("persistence: ephemeral", scan_output)

    def test_refresh_marks_stale_sections_and_records_fingerprint_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            artifact = root / "big-task.amd.md"

            self.run_cli(
                "init",
                str(artifact),
                "--kind",
                "task",
                "--title",
                "Big Task",
                "--stale-after-hours",
                "1",
                "--agent",
                "qa",
            )

            document = load_document(artifact)
            stale_at = isoformat_utc(load_time(document.metadata["updated_at"]) - timedelta(hours=2))
            for section in document.metadata["fingerprints"]["sections"].values():
                if section["heading"] == "Timeline":
                    continue
                section["updated_at"] = stale_at
            document.metadata["freshness"]["observed_at"] = stale_at
            save_document(artifact, document)

            refresh_artifact(artifact, agent="qa")
            stale_document = load_document(artifact)

            self.assertTrue(stale_document.metadata["freshness"]["is_stale"])
            self.assertIn("Purpose", stale_document.metadata["freshness"]["stale_reasons"])
            self.assertGreater(stale_document.metadata["priority"]["computed"], stale_document.metadata["priority"]["manual"])

            stale_document.body = stale_document.body.replace(
                "Capture facts the agents can trust right now.",
                "Trusted facts changed after a downstream review.",
            )
            save_document(artifact, stale_document)

            result = refresh_artifact(artifact, agent="qa")
            refreshed = load_document(artifact)

            self.assertIn("Current Context", result["changed_sections"])
            self.assertIn("[kind:fingerprint] section fingerprint changed: Current Context", refreshed.body)

    def test_refresh_all_expires_caveats_and_scans_tree(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            docs = root / "docs"
            docs.mkdir()
            alpha = docs / "alpha.amd.md"
            beta = docs / "nested" / "beta.amd.md"

            self.run_cli("init", str(alpha), "--title", "Alpha", "--agent", "qa")
            self.run_cli("init", str(beta), "--title", "Beta", "--kind", "report", "--agent", "qa")
            self.run_cli(
                "caveat",
                str(alpha),
                "--agent",
                "qa",
                "--severity",
                "medium",
                "--expires-at",
                "2026-03-09T00:00:00Z",
                "--text",
                "temporary warning",
            )

            refresh_all = self.run_cli("refresh-all", str(docs), "--agent", "qa")
            refresh_data = json.loads(refresh_all.stdout)
            tree_scan = self.run_cli("scan", str(docs)).stdout

            alpha_document = load_document(alpha)
            alpha_caveat = alpha_document.metadata["caveats"][0]

            self.assertEqual(len(refresh_data), 2)
            self.assertEqual(alpha_caveat["status"], "expired")
            self.assertIn(str(alpha), tree_scan)
            self.assertIn(str(beta), tree_scan)
            self.assertIn("active_caveats: 0", tree_scan)


def load_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


if __name__ == "__main__":
    unittest.main()
