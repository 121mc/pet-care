# Data Processing

Extract a small, representative screenshot sequence and blur everything except the probable pet area.

## Principles

- Keep the original video local.
- Share processed frames with OpenClaw, not raw home footage.
- Prefer fewer high-signal frames over many redundant frames.
- If pet localization is uncertain, mark the frame as fallback instead of pretending high confidence.

## Script

```bash
python data-processing/extract_and_blur_frames.py \
  --video-path path/to/pet.mp4 \
  --output-dir runs/latest/processed_frames
```

Optional manual boxes:

```bash
python data-processing/extract_and_blur_frames.py \
  --video-path path/to/pet.mp4 \
  --pet-boxes-json boxes.json
```

`boxes.json` may map source frame indexes to `[x, y, width, height]`.
