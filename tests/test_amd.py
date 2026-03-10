from __future__ import annotations

import tempfile
from pathlib import Path
import unittest

from amd.core import (
    add_caveat,
    add_signal,
    create_artifact,
    derive_skill_artifact,
    load_document,
    refresh_artifact,
    save_document,
    scan_artifact,
    set_manual_priority,
)


class AMDTests(unittest.TestCase):
    def test_task_artifact_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = root / "big-task.amd.md"
            create_artifact(path, title="Big Task", kind="task", agent="planner")

            add_caveat(path, text="staging data only", severity="high", agent="reviewer")
            add_signal(path, metric="error_rate", value=0.42, unit="ratio", agent="monitor")
            set_manual_priority(path, value=60, agent="planner")
            refresh_artifact(path, agent="system")

            document = load_document(path)
            metadata = document.metadata

            self.assertEqual(metadata["title"], "Big Task")
            self.assertEqual(metadata["kind"], "task")
            self.assertEqual(metadata["priority"]["manual"], 60)
            self.assertEqual(metadata["timeseries"]["points"], 1)
            self.assertEqual(len(metadata["caveats"]), 1)
            self.assertIn("planner", metadata["agents"]["contributors"])
            self.assertIn("monitor", metadata["agents"]["contributors"])
            self.assertIn("reviewer", metadata["agents"]["contributors"])
            self.assertIn("[kind:init] artifact initialized", document.body)
            self.assertIn("[kind:signal] signal recorded for error_rate", document.body)

            summary = scan_artifact(path)
            self.assertEqual(summary["timeseries_points"], 1)
            self.assertEqual(len(summary["active_caveats"]), 1)

    def test_derive_skill_from_mental_model(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "payments.amd.md"
            create_artifact(source, title="Payments Mental Model", kind="mental-model", agent="modeler")

            document = load_document(source)
            document.body = document.body.replace(
                "List the primitives, invariants, and entities that matter.",
                "- ledger\n- settlement\n- reconciliation",
            )
            document.body = document.body.replace(
                "Record heuristics, escalation rules, and default actions.",
                "- retry idempotent failures\n- escalate settlement mismatches",
            )
            document.body = document.body.replace(
                "Note common traps, stale assumptions, and diagnostic signals.",
                "- delayed webhooks\n- duplicate callbacks",
            )
            save_document(source, document)
            refresh_artifact(source, agent="modeler")

            derived = root / "payments-skill.amd.md"
            derive_skill_artifact(source, derived, agent="system")
            derived_document = load_document(derived)

            self.assertEqual(derived_document.metadata["kind"], "skill-derived")
            self.assertIn(str(source), derived_document.metadata["provenance"]["derived_from"])
            self.assertIn("retry idempotent failures", derived_document.body)
            self.assertIn("duplicate callbacks", derived_document.body)


if __name__ == "__main__":
    unittest.main()
