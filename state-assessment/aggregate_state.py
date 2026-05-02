import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.config_loader import default_config_path, load_config, section


ALLOWED_STATES = {"calm", "resting", "bored", "anxious", "alert", "unknown"}
ALLOWED_RISKS = {"low", "medium", "high", "unknown"}
ACTION_BY_STATE = {
    "calm": "none",
    "resting": "none",
    "bored": "short_play",
    "anxious": "soothing_voice",
    "alert": "notify_owner",
    "unknown": "observe",
}
INTERACT_STATES = {"bored", "anxious"}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def parse_jsonish(path):
    text = Path(path).read_text(encoding="utf-8").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def as_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def normalize(data, minimum_confidence):
    state = str(data.get("state", "unknown")).strip().lower()
    if state not in ALLOWED_STATES:
        state = "unknown"

    confidence = max(0.0, min(1.0, as_float(data.get("confidence", 0.0))))
    risk_level = str(data.get("risk_level", "unknown")).strip().lower()
    if risk_level not in ALLOWED_RISKS:
        risk_level = "unknown"

    evidence = data.get("evidence", [])
    if isinstance(evidence, str):
        evidence = [evidence]
    if not isinstance(evidence, list):
        evidence = []
    evidence = [str(item) for item in evidence[:6]]

    recommended_action = str(data.get("recommended_action") or ACTION_BY_STATE[state]).strip()
    requested_interaction = bool(data.get("should_interact", False))
    should_interact = (
        requested_interaction
        and state in INTERACT_STATES
        and confidence >= minimum_confidence
        and risk_level != "high"
    )

    if not should_interact and state in INTERACT_STATES and confidence >= minimum_confidence:
        recommended_action = ACTION_BY_STATE[state]

    human_message = str(
        data.get("human_message")
        or f"Pet state appears to be {state} with confidence {confidence:.2f}."
    )

    return {
        "schema_version": "1.0",
        "created_at": utc_now(),
        "state": state,
        "confidence": confidence,
        "evidence": evidence,
        "risk_level": risk_level,
        "recommended_action": recommended_action,
        "should_interact": should_interact,
        "human_message": human_message,
        "safety_notes": [
            "This is behavioral observation, not veterinary diagnosis.",
            "Hardware execution requires explicit runtime permission.",
        ],
    }


def parse_args(argv=None):
    base_parser = argparse.ArgumentParser(add_help=False)
    base_parser.add_argument("--config", default=str(default_config_path(__file__)))
    known, _ = base_parser.parse_known_args(argv)
    config = load_config(known.config)
    defaults = section(config, "state_assessment")

    parser = argparse.ArgumentParser(
        description="Normalize OpenClaw pet state JSON.",
        parents=[base_parser],
    )
    parser.add_argument("--model-json", required=True)
    parser.add_argument("--output-json", default=defaults.get("output_json", "runs/latest/state_result.json"))
    parser.add_argument(
        "--minimum-confidence",
        type=float,
        default=defaults.get("minimum_confidence_for_interaction", 0.65),
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    try:
        data = parse_jsonish(args.model_json)
        result = normalize(data, args.minimum_confidence)
        output_path = Path(args.output_json)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(str(output_path))
        return 0
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
