import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.config_loader import default_config_path, load_config, section


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def write_manifest(output_dir, data):
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "acquisition_manifest.json"
    manifest_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return manifest_path


def load_cv2():
    try:
        import cv2  # type: ignore
    except Exception as exc:
        raise RuntimeError(
            "OpenCV is required for camera capture. Install opencv-python or provide --video-path."
        ) from exc
    return cv2


def use_existing_video(video_path, output_dir):
    resolved = Path(video_path).expanduser().resolve()
    if not resolved.exists() or not resolved.is_file():
        raise FileNotFoundError(f"Video file not found: {resolved}")

    manifest = {
        "status": "ok",
        "source_type": "file",
        "video_path": str(resolved),
        "captured_video_path": None,
        "created_at": utc_now(),
        "message": "Using user-provided video. Camera was not opened.",
    }
    manifest_path = write_manifest(output_dir, manifest)
    print(str(manifest_path))
    return 0


def capture_from_camera(output_dir, camera_index, duration_seconds, fps):
    cv2 = load_cv2()
    output_dir.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(camera_index)

    if not cap.isOpened():
        manifest = {
            "status": "needs_user_input",
            "source_type": "camera",
            "camera_index": camera_index,
            "video_path": None,
            "created_at": utc_now(),
            "message": "No camera was available. Ask the user to provide a video path.",
        }
        manifest_path = write_manifest(output_dir, manifest)
        print(str(manifest_path), file=sys.stderr)
        return 2

    ok, frame = cap.read()
    if not ok or frame is None:
        cap.release()
        manifest = {
            "status": "needs_user_input",
            "source_type": "camera",
            "camera_index": camera_index,
            "video_path": None,
            "created_at": utc_now(),
            "message": "Camera opened but returned no frames. Ask the user to provide a video path.",
        }
        manifest_path = write_manifest(output_dir, manifest)
        print(str(manifest_path), file=sys.stderr)
        return 2

    height, width = frame.shape[:2]
    output_video = output_dir / "camera_capture.mp4"
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(output_video), fourcc, float(fps), (width, height))

    frame_count = 0
    start = time.monotonic()
    frame_delay = 1.0 / max(float(fps), 1.0)

    try:
        while time.monotonic() - start < duration_seconds:
            if frame is not None:
                writer.write(frame)
                frame_count += 1
            time.sleep(frame_delay)
            ok, frame = cap.read()
            if not ok:
                break
    finally:
        writer.release()
        cap.release()

    if frame_count == 0:
        manifest = {
            "status": "needs_user_input",
            "source_type": "camera",
            "camera_index": camera_index,
            "video_path": None,
            "created_at": utc_now(),
            "message": "No frames were captured. Ask the user to provide a video path.",
        }
        manifest_path = write_manifest(output_dir, manifest)
        print(str(manifest_path), file=sys.stderr)
        return 2

    manifest = {
        "status": "ok",
        "source_type": "camera",
        "camera_index": camera_index,
        "video_path": str(output_video.resolve()),
        "captured_video_path": str(output_video.resolve()),
        "duration_seconds": duration_seconds,
        "fps": fps,
        "frame_count": frame_count,
        "created_at": utc_now(),
    }
    manifest_path = write_manifest(output_dir, manifest)
    print(str(manifest_path))
    return 0


def parse_args(argv=None):
    base_parser = argparse.ArgumentParser(add_help=False)
    base_parser.add_argument("--config", default=str(default_config_path(__file__)))
    known, _ = base_parser.parse_known_args(argv)
    config = load_config(known.config)
    defaults = section(config, "video_acquisition")

    parser = argparse.ArgumentParser(
        description="Resolve or capture a pet-care video source.",
        parents=[base_parser],
    )
    parser.add_argument("--video-path", default=None, help="Existing video path. Skips camera capture.")
    parser.add_argument("--output-dir", default=defaults.get("output_dir", "runs/latest/acquisition"))
    parser.add_argument(
        "--camera-index",
        type=int,
        default=defaults.get("default_camera_index", 0),
    )
    parser.add_argument(
        "--duration-seconds",
        type=float,
        default=defaults.get("default_duration_seconds", 20.0),
    )
    parser.add_argument("--fps", type=int, default=defaults.get("default_fps", 15))
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    output_dir = Path(args.output_dir)
    try:
        if args.video_path:
            return use_existing_video(args.video_path, output_dir)
        return capture_from_camera(output_dir, args.camera_index, args.duration_seconds, args.fps)
    except Exception as exc:
        manifest = {
            "status": "error",
            "source_type": "file" if args.video_path else "camera",
            "video_path": args.video_path,
            "created_at": utc_now(),
            "message": str(exc),
        }
        write_manifest(output_dir, manifest)
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
