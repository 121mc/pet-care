# Video Acquisition

Resolve the video source before touching the camera.

## Decision Flow

1. If the user supplies a video path, validate it and return an acquisition manifest. Do not call the camera.
2. If no path is supplied, try the configured camera index.
3. If camera access fails or OpenCV is unavailable, stop and ask the user for a video path.

## Script

Run from the skill root:

```bash
python video-acquisition/capture_video.py --output-dir runs/latest/acquisition
```

Use an existing video:

```bash
python video-acquisition/capture_video.py --video-path path/to/pet.mp4 --output-dir runs/latest/acquisition
```

The script writes `acquisition_manifest.json` with the resolved source and selected video path.
