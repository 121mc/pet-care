import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.config_loader import csv_value, default_config_path, load_config, section


PET_CLASS_NAMES = {"cat", "dog", "bird", "horse", "sheep", "cow"}


class DetectorUnavailable(RuntimeError):
    pass


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def load_cv2_and_numpy():
    try:
        import cv2  # type: ignore
        import numpy as np  # type: ignore
    except Exception as exc:
        raise RuntimeError("Install opencv-python and numpy before processing videos.") from exc
    return cv2, np


def odd_kernel(value):
    value = max(3, int(value))
    return value if value % 2 else value + 1


def parse_color(value):
    parts = [part.strip() for part in str(value).split(",")]
    if len(parts) != 3:
        raise ValueError("--redaction-color must be three comma-separated BGR values.")
    return [max(0, min(255, int(part))) for part in parts]


def parse_class_names(value):
    names = {part.strip().lower() for part in str(value).split(",") if part.strip()}
    if not names:
        raise ValueError("--pet-class-names must include at least one class name.")
    return names


def clamp_box(box, width, height):
    x, y, w, h = [int(round(v)) for v in box]
    x = max(0, min(x, width - 1))
    y = max(0, min(y, height - 1))
    w = max(1, min(w, width - x))
    h = max(1, min(h, height - y))
    return [x, y, w, h]


def expand_box(box, width, height, padding_ratio):
    x, y, w, h = clamp_box(box, width, height)
    pad_x = int(round(w * padding_ratio))
    pad_y = int(round(h * padding_ratio))
    return clamp_box([x - pad_x, y - pad_y, w + pad_x * 2, h + pad_y * 2], width, height)


def pixelate_frame(cv2, frame, block_size):
    height, width = frame.shape[:2]
    block_size = max(4, int(block_size))
    small_width = max(1, width // block_size)
    small_height = max(1, height // block_size)
    small = cv2.resize(frame, (small_width, small_height), interpolation=cv2.INTER_LINEAR)
    return cv2.resize(small, (width, height), interpolation=cv2.INTER_NEAREST)


def redact_frame(cv2, np, frame, clear_box, mode, block_size, redaction_color):
    height, width = frame.shape[:2]
    if mode == "solid":
        redacted = np.zeros_like(frame)
        redacted[:, :] = redaction_color
    elif mode == "pixelate":
        redacted = pixelate_frame(cv2, frame, block_size)
    else:
        raise ValueError(f"Unsupported redaction mode: {mode}")

    x, y, w, h = clamp_box(clear_box, width, height)
    redacted[y : y + h, x : x + w] = frame[y : y + h, x : x + w]
    return redacted


class UltralyticsPetDetector:
    def __init__(self, model_name, confidence_threshold, pet_class_names):
        try:
            from ultralytics import YOLO  # type: ignore
        except Exception as exc:
            raise DetectorUnavailable(
                "Ultralytics is required for automatic pet detection. "
                "Install dependencies with `pip install -r requirements.txt`."
            ) from exc

        self.model_name = model_name
        self.confidence_threshold = confidence_threshold
        self.pet_class_names = pet_class_names
        try:
            self.model = YOLO(model_name)
        except Exception as exc:
            raise DetectorUnavailable(f"Could not load pet detector model {model_name}: {exc}") from exc

    @property
    def metadata(self):
        return {
            "backend": "ultralytics",
            "model": self.model_name,
            "pet_class_names": sorted(self.pet_class_names),
            "confidence_threshold": self.confidence_threshold,
        }

    def detect(self, frame, source_frame_index=None):
        results = self.model.predict(source=frame, verbose=False, conf=self.confidence_threshold)
        detections = []
        names = getattr(self.model, "names", {}) or {}
        for result in results:
            boxes = getattr(result, "boxes", None)
            if boxes is None:
                continue
            for box in boxes:
                class_id = int(box.cls[0])
                label = str(names.get(class_id, class_id)).lower()
                confidence = float(box.conf[0])
                if label not in self.pet_class_names or confidence < self.confidence_threshold:
                    continue
                x1, y1, x2, y2 = [float(value) for value in box.xyxy[0]]
                detections.append(
                    {
                        "box": [x1, y1, x2 - x1, y2 - y1],
                        "confidence": confidence,
                        "label": label,
                    }
                )
        detections.sort(key=lambda item: item["confidence"], reverse=True)
        return detections


def create_detector(args):
    class_names = parse_class_names(args.pet_class_names)
    return UltralyticsPetDetector(
        args.detector_model,
        args.detection_confidence_threshold,
        class_names,
    )


def clear_frame_outputs(output_dir):
    for path in output_dir.glob("frame_*.jpg"):
        path.unlink()


def frame_indices_for_pass(frame_count, step, sampling_pass, sampling_passes):
    if frame_count <= 0:
        return []
    offset = int(round((step * sampling_pass) / max(sampling_passes, 1)))
    offset = min(max(offset, 0), max(frame_count - 1, 0))
    return range(offset, frame_count, step)


def write_manifest(output_dir, manifest):
    manifest_path = output_dir / "frames_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(str(manifest_path))
    return manifest_path


def rejected_manifest(video_path, output_dir, reason, message, detector_metadata=None):
    clear_frame_outputs(output_dir)
    manifest = {
        "status": "rejected",
        "source_video_path": str(video_path),
        "created_at": utc_now(),
        "reject_reason": reason,
        "message": message,
        "frames": [],
        "detector": detector_metadata,
    }
    write_manifest(output_dir, manifest)
    return 0


def process_video(args, detector=None):
    cv2, np = load_cv2_and_numpy()
    video_path = Path(args.video_path).expanduser().resolve()
    if not video_path.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    clear_frame_outputs(output_dir)

    try:
        detector = detector or create_detector(args)
    except DetectorUnavailable as exc:
        return rejected_manifest(
            video_path,
            output_dir,
            "pet_detector_unavailable",
            str(exc),
            None,
        )

    detector_metadata = getattr(detector, "metadata", {"backend": detector.__class__.__name__})

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    step = max(1, int(round(fps * float(args.frame_interval_seconds))))
    block_size = odd_kernel(args.redaction_block_size)
    redaction_color = parse_color(args.redaction_color)
    min_usable_frames = max(1, int(args.min_usable_frames))
    max_frames = max(min_usable_frames, int(args.max_frames))
    sampling_passes = max(1, int(args.sampling_passes))

    manifest = {
        "status": "ok",
        "source_video_path": str(video_path),
        "created_at": utc_now(),
        "frame_interval_seconds": args.frame_interval_seconds,
        "max_frames": max_frames,
        "min_usable_frames": min_usable_frames,
        "sampling_passes_requested": sampling_passes,
        "sampling_passes_completed": 0,
        "discarded_frame_count": 0,
        "usable_frame_count": 0,
        "detector": detector_metadata,
        "privacy_policy": {
            "redaction_mode": args.redaction_mode,
            "only_detected_pet_regions_are_visible": True,
            "frames_without_pet_detection_are_discarded": True,
        },
        "frames": [],
        "discarded_frame_samples": [],
    }

    seen_indices = set()
    output_index = 0

    try:
        for sampling_pass in range(sampling_passes):
            manifest["sampling_passes_completed"] = sampling_pass + 1
            for source_frame_index in frame_indices_for_pass(
                frame_count, step, sampling_pass, sampling_passes
            ):
                if output_index >= max_frames:
                    break
                if source_frame_index in seen_indices:
                    continue
                seen_indices.add(source_frame_index)

                cap.set(cv2.CAP_PROP_POS_FRAMES, source_frame_index)
                ok, frame = cap.read()
                if not ok or frame is None:
                    manifest["discarded_frame_count"] += 1
                    continue

                detections = detector.detect(frame, source_frame_index)
                if not detections:
                    manifest["discarded_frame_count"] += 1
                    if len(manifest["discarded_frame_samples"]) < 20:
                        manifest["discarded_frame_samples"].append(
                            {
                                "source_frame_index": int(source_frame_index),
                                "timestamp_seconds": round(source_frame_index / fps, 3),
                                "reason": "no_pet_detected",
                            }
                        )
                    continue

                detection = detections[0]
                height, width = frame.shape[:2]
                pet_box = expand_box(detection["box"], width, height, args.box_padding_ratio)
                processed = redact_frame(
                    cv2,
                    np,
                    frame,
                    pet_box,
                    args.redaction_mode,
                    block_size,
                    redaction_color,
                )
                frame_name = f"frame_{output_index:04d}.jpg"
                frame_path = output_dir / frame_name
                cv2.imwrite(str(frame_path), processed)

                manifest["frames"].append(
                    {
                        "frame_index": output_index,
                        "source_frame_index": int(source_frame_index),
                        "timestamp_seconds": round(source_frame_index / fps, 3),
                        "processed_frame_path": str(frame_path.resolve()),
                        "pet_box": pet_box,
                        "pet_box_method": "detector",
                        "pet_box_confidence": float(detection["confidence"]),
                        "pet_label": detection.get("label", "pet"),
                        "privacy_status": "protected",
                        "share_allowed": True,
                        "privacy": "non_pet_regions_redacted",
                        "redaction_mode": args.redaction_mode,
                    }
                )
                output_index += 1

            manifest["usable_frame_count"] = len(manifest["frames"])
            if manifest["usable_frame_count"] >= min_usable_frames:
                break
            if output_index >= max_frames:
                break
    finally:
        cap.release()

    manifest["usable_frame_count"] = len(manifest["frames"])
    if manifest["usable_frame_count"] < min_usable_frames:
        partial_count = manifest["usable_frame_count"]
        clear_frame_outputs(output_dir)
        manifest["status"] = "rejected"
        manifest["reject_reason"] = "not_enough_detected_pet_frames"
        manifest["message"] = (
            f"Only {partial_count} privacy-safe pet frame(s) were detected after "
            f"{manifest['sampling_passes_completed']} sampling pass(es); "
            f"{min_usable_frames} are required. Ask the user for a clearer pet video."
        )
        manifest["partial_usable_frame_count"] = partial_count
        manifest["frames"] = []
        manifest["usable_frame_count"] = 0
    else:
        manifest["message"] = "Privacy-safe pet frames were extracted successfully."

    write_manifest(output_dir, manifest)
    return 0


def parse_args(argv=None):
    base_parser = argparse.ArgumentParser(add_help=False)
    base_parser.add_argument("--config", default=str(default_config_path(__file__)))
    known, _ = base_parser.parse_known_args(argv)
    config = load_config(known.config)
    defaults = section(config, "data_processing")

    parser = argparse.ArgumentParser(
        description="Extract only automatically detected, privacy-redacted pet frames.",
        parents=[base_parser],
    )
    parser.add_argument("--video-path", required=True)
    parser.add_argument("--output-dir", default=defaults.get("output_dir", "runs/latest/processed_frames"))
    parser.add_argument(
        "--frame-interval-seconds",
        type=float,
        default=defaults.get("frame_interval_seconds", 1.0),
    )
    parser.add_argument("--max-frames", type=int, default=defaults.get("max_frames", 30))
    parser.add_argument(
        "--min-usable-frames",
        type=int,
        default=defaults.get("min_usable_frames", 3),
    )
    parser.add_argument(
        "--sampling-passes",
        type=int,
        default=defaults.get("sampling_passes", 3),
    )
    parser.add_argument("--detector-model", default=defaults.get("detector_model", "yolov8n.pt"))
    parser.add_argument(
        "--detection-confidence-threshold",
        type=float,
        default=defaults.get("detection_confidence_threshold", 0.35),
    )
    parser.add_argument(
        "--pet-class-names",
        default=csv_value(defaults.get("pet_class_names"), "cat,dog,bird,horse,sheep,cow"),
    )
    parser.add_argument(
        "--box-padding-ratio",
        type=float,
        default=defaults.get("box_padding_ratio", 0.08),
    )
    parser.add_argument(
        "--redaction-block-size",
        type=int,
        default=defaults.get("redaction_block_size", 61),
    )
    parser.add_argument(
        "--redaction-mode",
        choices=["solid", "pixelate"],
        default=defaults.get("redaction_mode", "solid"),
        help="How to make non-pet regions unreadable.",
    )
    parser.add_argument(
        "--redaction-color",
        default=defaults.get("redaction_color", "0,0,0"),
        help="BGR color used by solid redaction mode.",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    try:
        return process_video(args)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
