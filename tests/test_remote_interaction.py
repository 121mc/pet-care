import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXECUTE_SCRIPT = ROOT / "remote-interaction" / "execute_interaction.py"


class RemoteInteractionTests(unittest.TestCase):
    def run_cmd(self, *args, expected_returncode=0):
        result = subprocess.run(
            [sys.executable, str(EXECUTE_SCRIPT), *map(str, args)],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            result.returncode,
            expected_returncode,
            msg=f"Command failed: {result.args}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
        )
        return result

    def write_fixture_files(self, root):
        state_json = root / "state.json"
        registry_yaml = root / "registry.yaml"
        policy_yaml = root / "policy.yaml"
        log_json = root / "interaction_log.json"
        config_yaml = root / "config.yaml"

        state_json.write_text(
            json.dumps(
                {
                    "state": "bored",
                    "confidence": 0.92,
                    "recommended_action": "short_play",
                    "should_interact": True,
                }
            ),
            encoding="utf-8",
        )
        registry_yaml.write_text(
            "\n".join(
                [
                    "devices:",
                    "  - id: mock-toy",
                    "    name: Mock toy",
                    "    enabled: true",
                    "    protocol: mock",
                    "    capabilities: [short_play]",
                    "    allowed_intensities: [medium]",
                    "    max_action_duration_seconds: 8",
                ]
            ),
            encoding="utf-8",
        )
        policy_yaml.write_text(
            "\n".join(
                [
                    "safety:",
                    "  require_explicit_hardware_enable: true",
                    "  global_cooldown_seconds: 120",
                    "  max_action_duration_seconds: 30",
                    "  stop_on_driver_error: true",
                    "states:",
                    "  bored:",
                    "    should_interact: true",
                    "    actions: [short_play]",
                    "actions:",
                    "  short_play:",
                    "    required_capability: short_play",
                    "    intensity: medium",
                    "    max_duration_seconds: 15",
                ]
            ),
            encoding="utf-8",
        )
        config_yaml.write_text(
            "\n".join(
                [
                    "remote_interaction:",
                    f"  registry: {registry_yaml}",
                    f"  policy: {policy_yaml}",
                    f"  log_path: {log_json}",
                    "  allow_hardware_by_default: false",
                    "  dry_run_by_default: true",
                    "  global_cooldown_seconds: 120",
                ]
            ),
            encoding="utf-8",
        )
        return state_json, registry_yaml, policy_yaml, log_json, config_yaml

    def test_requires_explicit_hardware_enable(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_json, _, _, log_json, config_yaml = self.write_fixture_files(Path(tmp))

            self.run_cmd("--config", config_yaml, "--state-json", state_json)

            log = json.loads(log_json.read_text(encoding="utf-8"))
            self.assertFalse(log["executed"])
            self.assertEqual(log["selection_reason"], "explicit_hardware_enable_required")

    def test_allow_hardware_executes_with_duration_and_intensity_limits(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_json, _, _, log_json, config_yaml = self.write_fixture_files(Path(tmp))

            self.run_cmd("--config", config_yaml, "--state-json", state_json, "--allow-hardware")

            log = json.loads(log_json.read_text(encoding="utf-8"))
            self.assertTrue(log["executed"])
            self.assertEqual(log["selection_reason"], "executed")
            self.assertEqual(log["action"]["intensity"], "medium")
            self.assertEqual(log["action"]["max_duration_seconds"], 8)
            self.assertEqual(log["driver_result"]["intensity"], "medium")
            self.assertEqual(log["driver_result"]["max_duration_seconds"], 8)

    def test_global_cooldown_blocks_second_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_json, _, _, log_json, config_yaml = self.write_fixture_files(Path(tmp))

            self.run_cmd("--config", config_yaml, "--state-json", state_json, "--allow-hardware")
            self.run_cmd("--config", config_yaml, "--state-json", state_json, "--allow-hardware")

            log = json.loads(log_json.read_text(encoding="utf-8"))
            self.assertFalse(log["executed"])
            self.assertEqual(log["selection_reason"], "global_cooldown_active")
            self.assertGreater(log["cooldown_remaining_seconds"], 0)


if __name__ == "__main__":
    unittest.main()
