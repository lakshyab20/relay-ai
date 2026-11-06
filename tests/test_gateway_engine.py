import tempfile
import unittest
from pathlib import Path

from mission_control.gateway_engine import MissionControlEngine


class MissionControlEngineTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="relay-test-")
        self.root = Path(self.temp_dir.name)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.db_path = self.root / "state" / "mission_control.db"

    def tearDown(self):
        self.temp_dir.cleanup()

    def make_engine(self):
        return MissionControlEngine(
            workspace_dir=str(self.workspace),
            db_path=str(self.db_path),
        )

    def test_first_run_starts_empty_and_creates_context_file(self):
        engine = self.make_engine()

        self.assertEqual(engine.get_dashboard_state()["shared_brain"], [])
        context = (self.workspace / ".aios_shared_context.md").read_text()
        self.assertIn("# 🧠 AIOS Shared Context", context)
        self.assertNotIn("Auto-Synced", context)

    def test_saved_memory_persists_and_does_not_replace_instruction_files(self):
        protected_files = ["AGENTS.md", "CLAUDE.md", "GEMINI.md", ".cursorrules"]
        for name in protected_files:
            (self.workspace / name).write_text(f"user instructions: {name}\n")
        engine = self.make_engine()

        saved = engine.add_shared_memory("Test Client", "Decision", "Keep the export API stable.")
        for name in protected_files:
            self.assertEqual((self.workspace / name).read_text(), f"user instructions: {name}\n")

        reloaded = self.make_engine()
        memories = reloaded.get_dashboard_state()["shared_brain"]
        self.assertEqual(len(memories), 1)
        self.assertEqual(memories[0]["id"], saved["id"])
        self.assertIn("Keep the export API stable.", (self.workspace / ".aios_shared_context.md").read_text())

    def test_file_change_is_recorded_and_can_be_reverted(self):
        note = self.workspace / "notes.md"
        note.write_text("before\n")
        engine = self.make_engine()
        note.write_text("after\n")

        snapshots = engine.scan_for_file_changes(default_agent="Test Client")
        self.assertEqual(len(snapshots), 1)
        self.assertIn("+after", snapshots[0]["unified_diff"])

        result = engine.rollback_snapshot(snapshots[0]["id"])
        self.assertEqual(result["status"], "ok")
        self.assertEqual(note.read_text(), "before\n")

    def test_secret_scrubber_redacts_matching_credentials(self):
        token_like = "sk-" + ("A" * 24)

        scrubbed, redacted = self.make_engine().scrub_secrets(f"credential={token_like}")

        self.assertTrue(redacted)
        self.assertNotIn(token_like, scrubbed)
        self.assertIn("AIOS_REDACTED_OPENAI_KEY", scrubbed)


if __name__ == "__main__":
    unittest.main()
