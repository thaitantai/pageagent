"""Integration tests for the agent Orchestrator.

Tests the full run_tick() flow with:
- Real Settings + AgentConfig wiring
- MockLLMClient (returns WAIT — no real LLM calls)
- Temp file-based LocalSheetStore (no real sheets)
- Patched tool dispatch and Telegram client (no real APIs)
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fanpage_agent.config import Settings


class OrchestratorIntegrationTest(unittest.TestCase):
    """Integration test for Orchestrator.run_tick() with mocked dependencies."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: self._cleanup(self.tmpdir))

        # Create minimal empty CSV files (LocalSheetStore needs them to exist)
        for name in [
            "post_history.csv",
            "post_metrics.csv",
            "comment_inbox.csv",
            "comment_triage.csv",
        ]:
            (self.tmpdir / name).write_text("", encoding="utf-8")

        # Copy sample brand profile so tools can load it
        sample_dir = Path(__file__).resolve().parents[1] / "data" / "sample"
        if sample_dir.exists():
            for fname in ["brand_profile.json", "brand_profile_ai.json"]:
                src = sample_dir / fname
                if src.exists():
                    (self.tmpdir / fname).write_text(src.read_text(), encoding="utf-8")

        # Settings using mock provider — no real LLM/Telegram/FB calls
        self.settings = Settings.from_env(
            env={
                "LLM_PROVIDER": "mock-local",
                "TELEGRAM_BOT_TOKEN": "test:fake-token",
                "TELEGRAM_CHAT_ID": "999",
                "FB_PAGE_ID": "test-page",
                "FB_PAGE_TOKEN": "test-token",
                "STORE_BACKEND": "local",
                "ARTIFACTS_DIR": str(self.tmpdir / "artifacts"),
            },
            root_dir=self.tmpdir,
        )

    # ── helpers ─────────────────────────────────────────────────

    @staticmethod
    def _cleanup(tmpdir: Path) -> None:
        import shutil

        if tmpdir.exists():
            shutil.rmtree(tmpdir, ignore_errors=True)

    def _make_agent_config(self, **overrides) -> MagicMock:
        """Build AgentConfig with sensible test defaults."""
        from dataclasses import dataclass

        from config import AgentConfig

        defaults = {
            "max_actions_per_tick": 5,
            "max_tick_calls": 10,
            "deliver_telegram": False,
        }
        defaults.update(overrides)
        return AgentConfig(**defaults)

    # ── test: basic tick with MockLLMClient (WAIT) ──────────────

    def test_tick_with_mock_llm_completes_successfully(self):
        """Orchestrator should complete one tick when LLM returns WAIT — no errors."""
        from agent import Orchestrator

        orchestrator = Orchestrator(self.settings, self._make_agent_config())
        result = orchestrator.run_tick()

        self.assertIn("timestamp", result)
        self.assertIn("elapsed_seconds", result)
        self.assertIsInstance(result["elapsed_seconds"], (int, float))
        self.assertEqual(result["total_tool_calls"], 0)
        self.assertEqual(len(result["errors"]), 0)
        self.assertIn("initial_state", result)

    # ── test: tick executes tool calls from mock LLM ────────────

    @patch("agent.dispatch_tool")
    @patch("agent.build_llm_client")
    def test_tick_executes_tool_call_from_llm(
        self, mock_build_llm: MagicMock, mock_dispatch: MagicMock
    ):
        """Orchestrator should execute tool calls when mock LLM returns them."""
        # Mock LLM: first call returns a tool call, second returns WAIT
        mock_client = MagicMock()
        mock_client.chat_with_tools.side_effect = [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "ops_status",
                            "arguments": {"reason": "test tick"},
                        },
                    }
                ],
            },
            {
                "role": "assistant",
                "content": json.dumps({"action": "WAIT", "reason": "all good"}),
            },
        ]
        mock_build_llm.return_value = mock_client
        mock_dispatch.return_value = {"status": "healthy", "pending": 0}

        from agent import Orchestrator

        orchestrator = Orchestrator(self.settings, self._make_agent_config())
        result = orchestrator.run_tick()

        # Should have called dispatch_tool exactly once
        self.assertEqual(mock_dispatch.call_count, 1)
        mock_dispatch.assert_called_with("ops_status", {"reason": "test tick"})

        # Summary should reflect the tool call
        self.assertEqual(result["total_tool_calls"], 1)
        self.assertEqual(len(result["errors"]), 0)

    # ── test: tick handles tool dispatch errors gracefully ──────

    @patch("agent.dispatch_tool")
    @patch("agent.build_llm_client")
    def test_tick_handles_tool_error_gracefully(
        self, mock_build_llm: MagicMock, mock_dispatch: MagicMock
    ):
        """Orchestrator should log tool errors and continue (not crash)."""
        mock_client = MagicMock()
        mock_client.chat_with_tools.side_effect = [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_err",
                        "type": "function",
                        "function": {
                            "name": "fetch_fb_comments",
                            "arguments": {},
                        },
                    }
                ],
            },
            {
                "role": "assistant",
                "content": json.dumps({"action": "WAIT", "reason": "error handled"}),
            },
        ]
        mock_build_llm.return_value = mock_client
        mock_dispatch.side_effect = RuntimeError("API rate limited")

        from agent import Orchestrator

        orchestrator = Orchestrator(self.settings, self._make_agent_config())
        result = orchestrator.run_tick()

        self.assertEqual(result["total_tool_calls"], 1)
        # The dispatch error should be captured, not crash the tick
        self.assertIn("error", result.get("history", [{}])[0].get("result", {}))

    # ── test: tick respects max_actions_per_tick ────────────────

    @patch("agent.dispatch_tool")
    @patch("agent.build_llm_client")
    def test_tick_respects_max_actions(
        self, mock_build_llm: MagicMock, mock_dispatch: MagicMock
    ):
        """Orchestrator should stop after max_actions_per_tick iterations."""
        mock_client = MagicMock()
        # Always return a tool call — forces the loop to max out
        mock_client.chat_with_tools.return_value = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_repeat",
                    "type": "function",
                    "function": {"name": "ops_status", "arguments": {"reason": "loop"}},
                }
            ],
        }
        mock_build_llm.return_value = mock_client
        mock_dispatch.return_value = {"status": "ok"}

        from agent import Orchestrator

        orchestrator = Orchestrator(
            self.settings,
            self._make_agent_config(max_actions_per_tick=3, max_tick_calls=10),
        )
        result = orchestrator.run_tick()

        # Should have stopped at max_actions_per_tick (3), not 10
        self.assertEqual(result["total_tool_calls"], 3)

    # ── test: run_daemon runs at least one tick ──────────────────

    @patch("agent.build_llm_client")
    def test_daemon_runs_one_tick_then_waits(self, mock_build_llm: MagicMock):
        """Daemon loop should execute at least one complete tick before sleeping."""
        import time

        mock_client = MagicMock()
        mock_client.chat_with_tools.return_value = {
            "role": "assistant",
            "content": json.dumps({"action": "WAIT", "reason": "nothing to do"}),
        }
        mock_build_llm.return_value = mock_client

        from agent import Orchestrator

        orchestrator = Orchestrator(
            self.settings,
            self._make_agent_config(
                deliver_telegram=False, tick_interval_seconds=1
            ),
        )

        # Run daemon in a thread and kill after 0.5s (just verifies start + sleep)
        import threading

        results = []
        thread = threading.Thread(
            target=lambda: results.append(orchestrator.run_daemon()),
            daemon=True,
        )
        thread.start()
        time.sleep(0.5)  # Let it run one tick + start sleeping

        # The thread should be alive (sleeping), meaning the tick completed
        self.assertTrue(thread.is_alive())

    # ── test: real settings wiring with temp LocalSheetStore ────

    def test_orchestrator_created_with_real_settings(self):
        """Orchestrator should initialize cleanly with real Settings + AgentConfig."""
        from agent import Orchestrator

        orchestrator = Orchestrator(self.settings, self._make_agent_config())
        self.assertIsNotNone(orchestrator)
        self.assertEqual(orchestrator.config.max_actions_per_tick, 5)
        self.assertEqual(orchestrator.config.deliver_telegram, False)


if __name__ == "__main__":
    unittest.main()
