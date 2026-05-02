import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def load_yaml(path):
    try:
        import yaml  # type: ignore
    except Exception as exc:
        raise RuntimeError("Install PyYAML before running remote interaction.") from exc
    with Path(path).open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def select_action(state_result, policy):
    state = state_result.get("state", "unknown")
    state_policy = policy.get("states", {}).get(state, {})
    if not state_result.get("should_interact", False):
        return None, "state_result_disallows_interaction"
    if not state_policy.get("should_interact", False):
        return None, "policy_disallows_interaction"

    recommended = state_result.get("recommended_action")
    actions = state_policy.get("actions", [])
    if recommended in actions:
        return recommended, "recommended"
    if actions:
        return actions[0], "policy_default"
    return None, "no_action_for_state"


def find_device(devices, action_def):
    required = action_def.get("required_capability")
    if not required or required == "none":
        return None
    for device in devices:
        if not device.get("enabled", False):
            continue
        capabilities = set(device.get("capabilities", []))
        if required in capabilities:
            return device
    return None


def run_driver(device, action):
    protocol = device.get("protocol")
    if protocol == "serial":
        from drivers.serial_driver import send_action

        return send_action(device, action)
    if protocol == "http":
        from drivers.http_driver import send_action

        return send_action(device, action)
    if protocol == "mock":
        from drivers.mock_driver import send_action

        return send_action(device, action)
    raise RuntimeError(f"Unsupported device protocol: {protocol}")


def write_log(path, payload):
    log_path = Path(path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Run safe pet-care hardware interaction.")
    parser.add_argument("--state-json", required=True)
    parser.add_argument("--registry", default="hardware_registry.yaml")
    parser.add_argument("--policy", default="remote-interaction/interaction_policy.yaml")
    parser.add_argument("--log-path", default="runs/latest/interaction_log.json")
    parser.add_argument("--allow-hardware", action="store_true")
    args = parser.parse_args()

    try:
        state_result = load_json(args.state_json)
        registry = load_yaml(args.registry)
        policy = load_yaml(args.policy)
        action_id, reason = select_action(state_result, policy)

        log = {
            "created_at": utc_now(),
            "state": state_result.get("state"),
            "confidence": state_result.get("confidence"),
            "selected_action": action_id,
            "selection_reason": reason,
            "hardware_allowed": args.allow_hardware,
            "executed": False,
            "driver_result": None,
        }

        if not action_id:
            write_log(args.log_path, log)
            print(json.dumps(log, indent=2))
            return 0

        action_defs = policy.get("actions", {})
        action_def = dict(action_defs.get(action_id, {}))
        action_def["id"] = action_id

        devices = registry.get("devices", [])
        device = find_device(devices, action_def)
        if device is None:
            log["selection_reason"] = "no_enabled_device_for_action"
            write_log(args.log_path, log)
            print(json.dumps(log, indent=2))
            return 0

        log["device_id"] = device.get("id")
        log["device_protocol"] = device.get("protocol")

        if not args.allow_hardware:
            log["selection_reason"] = "dry_run_requires_allow_hardware"
            write_log(args.log_path, log)
            print(json.dumps(log, indent=2))
            return 0

        result = run_driver(device, action_def)
        log["executed"] = True
        log["driver_result"] = result
        write_log(args.log_path, log)
        print(json.dumps(log, indent=2))
        return 0
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
