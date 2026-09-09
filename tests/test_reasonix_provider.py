import os
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from vibe_stick.protocol.state import AgentStatus
from vibe_stick.providers import reasonix


class ReasonixProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 9, 9, 10, 0, tzinfo=timezone.utc)
        self.root = Path("src") / "project"

    def test_running_runtime_maps_to_running(self) -> None:
        observation = self._observe(
            {
                "phase": "executing",
                "running": True,
                "turnId": "turn-1",
                "turnStatus": "in_progress",
            }
        )

        self.assertEqual(observation.status, AgentStatus.RUNNING)
        self.assertEqual(observation.provider_id, "reasonix")

    def test_pending_prompt_maps_to_approval(self) -> None:
        observation = self._observe(
            {
                "phase": "executing",
                "running": False,
                "turnId": "turn-2",
                "turnStatus": "waiting_user",
                "pendingPrompt": True,
            },
            prompts=[
                {
                    "kind": "approval_request",
                    "approval": {"subject": "Run tests"},
                }
            ],
        )

        self.assertEqual(observation.status, AgentStatus.APPROVAL)
        self.assertEqual(observation.alert_type, "APPROVAL")
        self.assertIn("Run tests", observation.alert_message)

    def test_completed_turn_has_stable_done_event(self) -> None:
        runtime = {
            "phase": "idle",
            "running": False,
            "turnId": "turn-3",
            "turnStatus": "completed",
            "revision": 8,
        }
        first = self._observe(runtime)
        second = self._observe(runtime)

        self.assertEqual(first.status, AgentStatus.DONE)
        self.assertEqual(first.alert_event_id, second.alert_event_id)

    def test_failed_turn_maps_to_error(self) -> None:
        observation = self._observe(
            {
                "phase": "idle",
                "running": False,
                "turnId": "turn-4",
                "turnStatus": "failed",
                "activity": "Provider request failed",
            }
        )

        self.assertEqual(observation.status, AgentStatus.ERROR)
        self.assertEqual(observation.alert_type, "ERROR")
        self.assertEqual(observation.alert_message, "Provider request failed")

    def test_project_root_supplies_project_name(self) -> None:
        observation = self._observe(
            {"phase": "idle", "running": False},
            status={"cwd": "C:\\src\\warehouse-tool"},
        )

        self.assertEqual(observation.project, "project")

    def test_managed_connection_reads_port_and_token(self) -> None:
        with self.subTest("valid files"):
            with mock.patch.object(Path, "read_text", side_effect=["8787", "secret"]):
                connection = reasonix._read_managed_connection(Path("port"), Path("token"))
            self.assertEqual(connection, ("http://127.0.0.1:8787", "secret"))

    def test_configured_project_name_wins(self) -> None:
        with mock.patch.dict(os.environ, {"VIBE_STICK_PROJECT_NAME": "Configured"}):
            observation = self._observe(
                {"phase": "idle", "running": False},
                status={"cwd": "C:\\src\\ignored"},
            )

        self.assertEqual(observation.project, "Configured")

    def _observe(
        self,
        runtime: dict,
        *,
        prompts: list | None = None,
        status: dict | None = None,
    ):
        payload = {
            "epoch": "epoch-1",
            "revision": 1,
            "sessions": [
                {
                    "current": True,
                    "sessionPath": "session.jsonl",
                    "state": runtime,
                }
            ],
        }
        return reasonix.observation_from_payloads(
            payload,
            status or {},
            prompts or [],
            project_root=self.root,
            observed_at=self.now,
        )


if __name__ == "__main__":
    unittest.main()
