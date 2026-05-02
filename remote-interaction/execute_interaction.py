import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.config_loader import bool_value, default_config_path, load_config, load_yaml, section


INTENSITY_ORDER = {"none": 0, "low": 1, "medium": 2, "high": 3}


def utc_now():
    return datetime.now(timezone.utc)


def utc_now_text():
    return utc_now().isoformat()


def parse_time(value):
    if not value:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_optional_json(path):
    log_path = Path(path)
    if not log_path.exists():
        return None
    try:
        return load_json(log_path)
    except Exception:
        return None


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


def intensity_allowed(device, intensity):
    allowed = device.get("allowed_intensities")
    if allowed and intensity not in set(str(item) for item in allowed):
        return False

    max_intensity = device.get("max_intensity")
    if max_intensity:
        return INTENSITY_ORDER.get(str(intensity), 99) <= INTENSITY_ORDER.get(str(max_intensity), -1)
    return True


def positive_numbers(*values):
    result = []
    for value in values:
        if value is None:
            continue
        try:
            number = float(value)
        except Exception:
            continue
        if number > 0:
            result.append(number)
    return result


def build_runtime_action(action_id, action_def, safety, device):
    intensity = str(action_def.get("intensity", "none"))
    duration_limits = positive_numbers(
        action_def.get("max_duration_seconds"),
        safety.get("max_action_duration_seconds"),
        device.get("max_action_duration_seconds"),
    )
    max_duration = min(duration_limits) if duration_limits else None

    runtime_action = dict(action_def)
    runtime_action["id"] = action_id
    runtime_action["intensity"] = intensity
    if max_duration is not None:
        runtime_action["max_duration_seconds"] = max_duration
    return runtime_action


def cooldown_status(previous_log, cooldown_seconds, now):
    if not previous_log or not previous_log.get("executed"):
        return False, 0
    last_time = parse_time(previous_log.get("completed_at") or previous_log.get("created_at"))
    if last_time is None:
        return False, 0
    elapsed = (now - last_time).total_seconds()
    remaining = max(0, int(round(float(cooldown_seconds) - elapsed)))
    return remaining > 0, remaining


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


def base_log(state_result, args, safety):
    return {
        "created_at": utc_now_text(),
        "state": state_result.get("state"),
        "confidence": state_result.get("confidence"),
        "selected_action": None,
        "selection_reason": None,
        "hardware_allowed": False,
        "dry_run": args.dry_run,
        "executed": False,
        "driver_result": None,
        "safety": {
            "require_explicit_hardware_enable": bool_value(
                safety.get("require_explicit_hardware_enable"), True
            ),
            "global_cooldown_seconds": float(safety.get("global_cooldown_seconds", 0) or 0),
            "max_action_duration_seconds": safety.get("max_action_duration_seconds"),
            "stop_on_driver_error": bool_value(safety.get("stop_on_driver_error"), True),
        },
    }


def execute(args):
    state_result = load_json(args.state_json)
    registry = load_yaml(args.registry)
    policy = load_yaml(args.policy)
    safety = dict(policy.get("safety", {}))
    if "global_cooldown_seconds" not in safety:
        safety["global_cooldown_seconds"] = args.global_cooldown_seconds

    log = base_log(state_result, args, safety)
    action_id, reason = select_action(state_result, policy)
    log["selected_action"] = action_id
    log["selection_reason"] = reason

    if not action_id:
        write_log(args.log_path, log)
        print(json.dumps(log, indent=2))
        return 0

    action_defs = policy.get("actions", {})
    if action_id not in action_defs:
        log["selection_reason"] = "no_action_definition"
        write_log(args.log_path, log)
        print(json.dumps(log, indent=2))
        return 0

    action_def = dict(action_defs[action_id])
    devices = registry.get("devices", [])
    device = find_device(devices, action_def)
    if device is None:
        log["selection_reason"] = "no_enabled_device_for_action"
        write_log(args.log_path, log)
        print(json.dumps(log, indent=2))
        return 0

    log["device_id"] = device.get("id")
    log["device_protocol"] = device.get("protocol")

    require_explicit = bool_value(safety.get("require_explicit_hardware_enable"), True)
    if require_explicit and not args.allow_hardware_explicit:
        log["selection_reason"] = "explicit_hardware_enable_required"
        write_log(args.log_path, log)
        print(json.dumps(log, indent=2))
        return 0

    if args.dry_run or not args.allow_hardware:
        log["selection_reason"] = "dry_run_requires_allow_hardware"
        write_log(args.log_path, log)
        print(json.dumps(log, indent=2))
        return 0

    runtime_action = build_runtime_action(action_id, action_def, safety, device)
    log["hardware_allowed"] = True
    log["action"] = {
        "id": runtime_action["id"],
        "intensity": runtime_action.get("intensity"),
        "max_duration_seconds": runtime_action.get("max_duration_seconds"),
    }

    if not intensity_allowed(device, runtime_action.get("intensity", "none")):
        log["selection_reason"] = "device_intensity_limit_blocks_action"
        write_log(args.log_path, log)
        print(json.dumps(log, indent=2))
        return 0

    previous_log = load_optional_json(args.log_path)
    cooldown_seconds = float(safety.get("global_cooldown_seconds", 0) or 0)
    active, remaining = cooldown_status(previous_log, cooldown_seconds, utc_now())
    if active:
        log["selection_reason"] = "global_cooldown_active"
        log["cooldown_remaining_seconds"] = remaining
        write_log(args.log_path, log)
        print(json.dumps(log, indent=2))
        return 0

    stop_on_driver_error = bool_value(safety.get("stop_on_driver_error"), True)
    try:
        result = run_driver(device, runtime_action)
    except Exception as exc:
        log["selection_reason"] = "driver_error"
        log["driver_error"] = str(exc)
        write_log(args.log_path, log)
        print(json.dumps(log, indent=2))
        return 1 if stop_on_driver_error else 0

    log["selection_reason"] = "executed"
    log["executed"] = True
    log["completed_at"] = utc_now_text()
    log["driver_result"] = result
    write_log(args.log_path, log)
    print(json.dumps(log, indent=2))
    return 0


def parse_args(argv=None):
    raw_args = list(sys.argv[1:] if argv is None else argv)
    base_parser = argparse.ArgumentParser(add_help=False)
    base_parser.add_argument("--config", default=str(default_config_path(__file__)))
    known, _ = base_parser.parse_known_args(raw_args)
    config = load_config(known.config)
    defaults = section(config, "remote_interaction")

    allow_hardware_explicit = "--allow-hardware" in raw_args
    dry_run_explicit = "--dry-run" in raw_args

    parser = argparse.ArgumentParser(
        description="Run safe pet-care hardware interaction.",
        parents=[base_parser],
    )
    parser.add_argument("--state-json", required=True)
    parser.add_argument("--registry", default=defaults.get("registry", "hardware_registry.yaml"))
    parser.add_argument(
        "--policy",
        default=defaults.get("policy", "remote-interaction/interaction_policy.yaml"),
    )
    parser.add_argument("--log-path", default=defaults.get("log_path", "runs/latest/interaction_log.json"))
    parser.add_argument(
        "--global-cooldown-seconds",
        type=float,
        default=defaults.get("global_cooldown_seconds", 0),
    )
    parser.add_argument(
        "--allow-hardware",
        action="store_true",
        default=bool_value(defaults.get("allow_hardware_by_default"), False),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=bool_value(defaults.get("dry_run_by_default"), True),
    )
    args = parser.parse_args(raw_args)

    if allow_hardware_explicit and not dry_run_explicit:
        args.dry_run = False
    args.allow_hardware_explicit = allow_hardware_explicit
    return args


def main(argv=None):
    args = parse_args(argv)
    try:
        return execute(args)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
