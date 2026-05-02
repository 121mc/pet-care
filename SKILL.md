---
name: pet-care
description: Analyze pet camera feeds or user-provided pet videos, automatically detect pet regions, output only privacy-redacted pet frames or reject videos with too few valid detections, assess pet state through OpenClaw multimodal reasoning only from safe frames, and optionally coordinate safe hardware interaction for anxious, bored, alert, resting, or calm pets.
---

# Pet Care

## Purpose

Use this skill to run a safe pet-care loop:

```text
video acquisition -> data processing -> state assessment -> remote interaction
```

Prefer user-provided video when a path is supplied. Use a camera only when no video path is supplied. If no path is supplied and no camera is available, stop and ask the user for a video path.

## Resource Map

- `config.yaml`: default runtime settings for capture, frame extraction, privacy gate thresholds, state thresholds, and safety.
- `hardware_registry.yaml`: hardware inventory and call mapping. It is intentionally empty until real devices are connected.
- `video-acquisition/`: camera or video-source handling.
- `data-processing/`: automatic pet detection, frame resampling, irreversible redaction, and reject handling.
- `state-assessment/`: OpenClaw prompt template and JSON normalization.
- `remote-interaction/`: safety policy, hardware dispatch, and drivers.

Read the module `guide.md` only when working in that module. Run scripts from the skill root unless a guide says otherwise. Scripts read `config.yaml` for defaults; command-line flags may override those defaults for a single run.

## Workflow

1. Resolve input.
   - If the user gives `video_path`, validate that file and do not open the camera.
   - If no `video_path` is given, run `video-acquisition/capture_video.py`.
   - If camera capture fails because no camera is available, ask the user for a video path.

2. Process video.
   - Run `data-processing/extract_and_blur_frames.py` on the selected video.
   - Use automatic pet detection only. Do not use manual boxes, motion-only boxes, or center fallback.
   - Discard frames where no pet is detected; do not write them as output images.
   - If too few usable frames are found, resample the video at different offsets for up to three passes.
   - If the usable frame count is still below the configured minimum, reject the video and tell the user a clearer pet video is needed.
   - On success, output only privacy-redacted frames with detected pet regions visible.

3. Assess state with OpenClaw.
   - Continue only when `frames_manifest.json` has `status: ok`.
   - If data processing returns `status: rejected`, report that message to the user and do not call OpenClaw.
   - Send only frames listed in the successful `frames_manifest.json`.
   - Load `state-assessment/prompt_template.md`.
   - Inspect only the processed privacy-redacted screenshots and output only the required JSON shape.
   - Normalize or validate the model JSON with `state-assessment/aggregate_state.py`.

4. Interact safely.
   - Read `remote-interaction/interaction_policy.yaml`.
   - Read `hardware_registry.yaml`.
   - If no enabled hardware matches the recommended action, tell the user the assessment and skip execution.
   - Execute hardware only when explicitly allowed for the run with `--allow-hardware`.
   - Enforce cooldown, action duration, intensity, and driver-error handling before calling a device driver.

5. Report to the user.
   - Include the state, confidence, key visual evidence, recommended action, and whether hardware ran.
   - Do not claim medical diagnosis. Treat output as behavioral observation and companion-care guidance.

## State Labels

Use only these labels unless the user explicitly requests another taxonomy:

- `calm`: relaxed, normal activity, no intervention.
- `resting`: sleeping or lying quietly, avoid disturbance.
- `bored`: low stimulation, repetitive wandering, seeking play.
- `anxious`: pacing, scratching, repeated calls, unsettled posture.
- `alert`: focused on a door, window, noise, stranger, or possible hazard.
- `unknown`: insufficient or ambiguous visual evidence.

## JSON Contract

OpenClaw state assessment must produce JSON compatible with:

```json
{
  "state": "calm|resting|bored|anxious|alert|unknown",
  "confidence": 0.0,
  "evidence": ["short observable reason"],
  "risk_level": "low|medium|high|unknown",
  "recommended_action": "none|observe|soothing_voice|soft_light|short_play|notify_owner",
  "should_interact": false,
  "human_message": "brief user-facing explanation"
}
```

## Safety Rules

- Default to observation and reporting when evidence is weak.
- Reject videos with too few automatically detected pet frames.
- Never use center crop or motion-only fallback as a privacy-safe pet region.
- Never force hardware interaction for `resting`, `calm`, `unknown`, or high-risk `alert` states.
- Require explicit hardware enablement before executing real devices.
- Respect cooldown, duration, and intensity limits in `interaction_policy.yaml`.
- Stop or skip interaction when a device returns an error, a pet is near moving machinery, or the action may startle the pet.
- Never expose unredacted home screenshots unless the user specifically supplied them for direct inspection.
- Never send discarded, partial, uncertain, or rejected frames to OpenClaw or another external model.
