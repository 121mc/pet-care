# Data Processing

Extract privacy-safe pet screenshots from a video using automatic pet detection only.

## Contract

- Input is only a video path.
- Output is either:
  - `status: ok` plus processed frames where only detected pet regions remain visible, or
  - `status: rejected` plus a user-facing reason when there are not enough valid pet frames.
- Do not use manual boxes, center fallback, motion-only boxes, or unchecked frames.
- Frames with no pet detection are discarded and never written as output images.
- If too few usable frames are found, resample the video with different offsets for up to three passes.
- If the final usable count is still below `min_usable_frames`, remove any partial frame outputs and reject the video.

## Script

Run from the skill root:

```bash
python data-processing/extract_and_blur_frames.py \
  --video-path path/to/pet.mp4 \
  --output-dir runs/latest/processed_frames
```

Defaults are read from the `data_processing` section of `config.yaml`. Command-line flags override those defaults for one run.

The script uses Ultralytics YOLO by default:

```bash
python data-processing/extract_and_blur_frames.py \
  --video-path path/to/pet.mp4 \
  --detector-model yolov8n.pt \
  --detection-confidence-threshold 0.35 \
  --min-usable-frames 3 \
  --sampling-passes 3
```

`requirements.txt` includes `ultralytics`. If the detector cannot be loaded, write a rejected manifest instead of attempting a weaker fallback.

## Sampling Behavior

The first pass samples frames at the configured interval. If fewer than `min_usable_frames` are accepted, subsequent passes revisit the video at different offsets, so they inspect different frames instead of repeating the same cuts.

Default behavior:

- `frame_interval_seconds`: `1.0`
- `min_usable_frames`: `3`
- `sampling_passes`: `3`
- `max_frames`: `30`

## Privacy Behavior

For each detected pet frame:

- Expand the detector box slightly with `--box-padding-ratio`.
- Redact everything outside the pet box using `solid` or `pixelate`.
- Save only the processed frame.
- Record `privacy_status: protected` and `share_allowed: true`.

For rejected videos:

- Do not keep partial processed frame outputs.
- Keep only `frames_manifest.json`.
- Report `reject_reason: not_enough_detected_pet_frames` or `pet_detector_unavailable`.

`frames_manifest.json` records:

- `status`: `ok` or `rejected`
- `usable_frame_count`
- `discarded_frame_count`
- `sampling_passes_completed`
- `frames`: protected output frame metadata when successful
- `message`: what to tell the user when rejected
