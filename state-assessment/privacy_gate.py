import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.config_loader import default_config_path, load_config, section


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, payload):
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def unknown_state_result(message, evidence=None):
    return {
        "schema_version": "1.0",
        "created_at": utc_now(),
        "state": "unknown",
        "confidence": 0.0,
        "evidence": evidence or [message],
        "risk_level": "unknown",
        "recommended_action": "observe",
        "should_interact": False,
        "human_message": message,
        "safety_notes": [
            "No privacy-safe frames were available for assessment.",
            "This is behavioral observation, not veterinary diagnosis.",
            "Hardware execution requires explicit runtime permission.",
        ],
    }


def is_safe_frame(frame, minimum_confidence, require_existing_files):
    if frame.get("privacy_status") != "protected":
        return False, "privacy_status_not_protected"
    if frame.get("share_allowed") is not True:
        return False, "share_not_allowed"

    try:
        confidence = float(frame.get("pet_box_confidence", 0.0))
    except Exception:
        confidence = 0.0
    if confidence < minimum_confidence:
        return False, "pet_box_confidence_below_threshold"

    frame_path = frame.get("processed_frame_path")
    if require_existing_files and (not frame_path or not Path(frame_path).exists()):
        return False, "processed_frame_missing"

    return True, "safe"


def build_assessment_manifest(args):
    source = load_json(args.frames_manifest)
    frames = source.get("frames", [])
    safe_frames = []
    blocked_frames = []

    for frame in frames:
        safe, reason = is_safe_frame(
            frame,
            args.minimum_pet_box_confidence,
            not args.skip_file_existence_check,
        )
        item = dict(frame)
        item["privacy_gate_reason"] = reason
        if safe:
            safe_frames.append(item)
        else:
            blocked_frames.append(item)

    status = "ok" if safe_frames else "blocked"
    output = {
        "schema_version": "1.0",
        "created_at": utc_now(),
        "status": status,
        "source_frames_manifest": str(Path(args.frames_manifest).resolve()),
        "minimum_pet_box_confidence": args.minimum_pet_box_confidence,
        "safe_frame_count": len(safe_frames),
        "blocked_frame_count": len(blocked_frames),
        "frames": safe_frames,
        "blocked_frames": blocked_frames,
    }

    if safe_frames:
        output["message"] = "Privacy-safe frames are available for state assessment."
    else:
        message = "No privacy-safe frames were available for assessment."
        output["message"] = message
        if args.fallback_state_json:
            write_json(args.fallback_state_json, unknown_state_result(message))
            output["fallback_state_json"] = str(Path(args.fallback_state_json).resolve())

    write_json(args.output_manifest, output)
    print(json.dumps(output, indent=2))
    return 0


def parse_args(argv=None):
    base_parser = argparse.ArgumentParser(add_help=False)
    base_parser.add_argument("--config", default=str(default_config_path(__file__)))
    known, _ = base_parser.parse_known_args(argv)
    config = load_config(known.config)
    defaults = section(config, "state_assessment")

    parser = argparse.ArgumentParser(
        description="Gate processed frames before multimodal pet state assessment.",
        parents=[base_parser],
    )
    parser.add_argument("--frames-manifest", required=True)
    parser.add_argument(
        "--output-manifest",
        default=defaults.get("assessment_input_manifest", "runs/latest/assessment_input_manifest.json"),
        help="Manifest containing only frames allowed for state assessment.",
    )
    parser.add_argument(
        "--fallback-state-json",
        default=defaults.get("output_json", "runs/latest/state_result.json"),
        help="Unknown state result to write when no privacy-safe frames exist.",
    )
    parser.add_argument(
        "--minimum-pet-box-confidence",
        type=float,
        default=defaults.get("minimum_pet_box_confidence_for_assessment", 0.8),
        help="Minimum confidence required for a frame to reach OpenClaw.",
    )
    parser.add_argument(
        "--skip-file-existence-check",
        action="store_true",
        help="Do not require processed_frame_path files to exist locally.",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    try:
        return build_assessment_manifest(args)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
