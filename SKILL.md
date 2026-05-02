---
name: pet-care
description: Analyze pet camera feeds or user-provided pet videos, extract privacy-protected screenshots, assess pet state through OpenClaw multimodal reasoning, and optionally coordinate safe hardware interaction for anxious, bored, alert, resting, or calm pets.
---

# Pet Care

## Purpose

Use this skill to run a safe pet-care loop:

```text
video acquisition -> data processing -> state assessment -> remote interaction
```

Prefer user-provided video when a path is supplied. Use a camera only when no video path is supplied. If no path is supplied and no camera is available, stop and ask the user for a video path.

## Resource Map

- `config.yaml`: default runtime settings for capture, frame extraction, privacy, state thresholds, and safety.
- `hardware_registry.yaml`: hardware inventory and call mapping. It is intentionally empty until real devices are connected.
- `video-acquisition/`: camera or video-source handling.
- `data-processing/`: frame extraction and privacy-preserving pet-focused blur.
- `state-assessment/`: OpenClaw prompt template and JSON normalization.
- `remote-interaction/`: safety policy, hardware dispatch, and drivers.

Read the module `guide.md` only when working in that module. Run scripts from the skill root unless a guide says otherwise.

## Workflow

1. Resolve input.
   - If the user gives `video_path`, validate that file and do not open the camera.
   - If no `video_path` is given, run `video-acquisition/capture_video.py`.
   - If camera capture fails because no camera is available, ask the user for a video path.

2. Process video.
   - Run `data-processing/extract_and_blur_frames.py` on the selected video.
   - Keep only the pet region clear. Blur everything else.
   - Produce a frame manifest with timestamps, file paths, privacy status, and pet-box metadata.

3. Assess state with OpenClaw.
   - Load `state-assessment/prompt_template.md`.
   - Inspect the processed screenshots and output only the required JSON shape.
   - Normalize or validate the model JSON with `state-assessment/aggregate_state.py`.

4. Interact safely.
   - Read `remote-interaction/interaction_policy.yaml`.
   - Read `hardware_registry.yaml`.
   - If no enabled hardware matches the recommended action, tell the user the assessment and skip execution.
   - Execute hardware only when explicitly allowed for the run.

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
- Never force hardware interaction for `resting`, `calm`, `unknown`, or high-risk `alert` states.
- Require explicit hardware enablement before executing real devices.
- Respect cooldown, duration, and intensity limits in `interaction_policy.yaml`.
- Stop or skip interaction when a device returns an error, a pet is near moving machinery, or the action may startle the pet.
- Never expose unblurred home screenshots unless the user specifically supplied them for direct inspection.
