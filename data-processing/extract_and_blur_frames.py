import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


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


def clamp_box(box, width, height):
    x, y, w, h = [int(v) for v in box]
    x = max(0, min(x, width - 1))
    y = max(0, min(y, height - 1))
    w = max(1, min(w, width - x))
    h = max(1, min(h, height - y))
    return [x, y, w, h]


def center_box(width, height):
    w = int(width * 0.55)
    h = int(height * 0.65)
    x = int((width - w) / 2)
    y = int((height - h) / 2)
    return [x, y, w, h]


def detect_motion_box(cv2, frame, previous_gray, min_area_ratio):
    if previous_gray is None:
        return None, "fallback_center"

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    diff = cv2.absdiff(gray, previous_gray)
    _, thresh = cv2.threshold(diff, 24, 255, cv2.THRESH_BINARY)
    thresh = cv2.medianBlur(thresh, 5)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    height, width = gray.shape[:2]
    min_area = width * height * float(min_area_ratio)
    candidates = []
    for contour in contours:
        area = cv2.contourArea(contour)
        if area >= min_area:
            x, y, w, h = cv2.boundingRect(contour)
            candidates.append((area, [x, y, w, h]))

    if not candidates:
        return None, "fallback_center"

    candidates.sort(key=lambda item: item[0], reverse=True)
    return clamp_box(candidates[0][1], width, height), "motion_contour"


def blur_outside_box(cv2, np, frame, box, blur_kernel):
    height, width = frame.shape[:2]
    x, y, w, h = clamp_box(box, width, height)
    blurred = cv2.GaussianBlur(frame, (blur_kernel, blur_kernel), 0)
    mask = np.zeros((height, width), dtype=np.uint8)
    mask[y : y + h, x : x + w] = 255
    return np.where(mask[:, :, None] == 255, frame, blurred)


def load_boxes(path):
    if not path:
        return {}
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {int(k): v for k, v in data.items()}


def process_video(args):
    cv2, np = load_cv2_and_numpy()
    video_path = Path(args.video_path).expanduser().resolve()
    if not video_path.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    boxes = load_boxes(args.pet_boxes_json)

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(1, int(round(fps * float(args.frame_interval_seconds))))
    blur_kernel = odd_kernel(args.blur_kernel_size)

    manifest = {
        "status": "ok",
        "source_video_path": str(video_path),
        "created_at": utc_now(),
        "frame_interval_seconds": args.frame_interval_seconds,
        "max_frames": args.max_frames,
        "frames": [],
    }

    previous_gray = None
    source_frame_index = -1
    output_index = 0

    try:
        while output_index < args.max_frames:
            ok, frame = cap.read()
            if not ok or frame is None:
                break
            source_frame_index += 1

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            should_extract = source_frame_index == 0 or source_frame_index % step == 0
            if not should_extract:
                previous_gray = gray
                continue

            height, width = frame.shape[:2]
            if source_frame_index in boxes:
                box = clamp_box(boxes[source_frame_index], width, height)
                method = "manual"
            else:
                box, method = detect_motion_box(cv2, frame, previous_gray, args.min_pet_box_area_ratio)
                if box is None:
                    box = center_box(width, height)

            processed = blur_outside_box(cv2, np, frame, box, blur_kernel)
            frame_name = f"frame_{output_index:04d}.jpg"
            frame_path = output_dir / frame_name
            cv2.imwrite(str(frame_path), processed)

            manifest["frames"].append(
                {
                    "frame_index": output_index,
                    "source_frame_index": source_frame_index,
                    "timestamp_seconds": round(source_frame_index / fps, 3),
                    "processed_frame_path": str(frame_path.resolve()),
                    "pet_box": box,
                    "pet_box_method": method,
                    "privacy": "non_pet_regions_blurred",
                }
            )
            output_index += 1
            previous_gray = gray
    finally:
        cap.release()

    if not manifest["frames"]:
        manifest["status"] = "error"
        manifest["message"] = "No frames were extracted."

    manifest_path = output_dir / "frames_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(str(manifest_path))
    return 0 if manifest["status"] == "ok" else 1


def main():
    parser = argparse.ArgumentParser(description="Extract and privacy-blur pet video frames.")
    parser.add_argument("--video-path", required=True)
    parser.add_argument("--output-dir", default="runs/latest/processed_frames")
    parser.add_argument("--frame-interval-seconds", type=float, default=1.0)
    parser.add_argument("--max-frames", type=int, default=30)
    parser.add_argument("--blur-kernel-size", type=int, default=61)
    parser.add_argument("--min-pet-box-area-ratio", type=float, default=0.03)
    parser.add_argument("--pet-boxes-json", default=None)
    args = parser.parse_args()

    try:
        return process_video(args)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
