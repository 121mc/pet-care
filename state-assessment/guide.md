# State Assessment

Use OpenClaw multimodal reasoning only after data processing has produced accepted privacy-redacted pet frames, then normalize the result.

## Steps

1. Read `runs/latest/processed_frames/frames_manifest.json`.
2. If `status` is `rejected`, stop. Tell the user the manifest `message` and do not call OpenClaw.
3. If `status` is `ok`, attach or reference only the processed frames listed in `frames`.
4. Optionally run the privacy gate as a defensive validation step:

```bash
python state-assessment/privacy_gate.py \
  --frames-manifest runs/latest/processed_frames/frames_manifest.json \
  --output-manifest runs/latest/assessment_input_manifest.json \
  --fallback-state-json runs/latest/state_result.json
```

5. If the gate returns `status: blocked`, stop. Use the generated `unknown` state result and do not call OpenClaw.
6. Load `prompt_template.md`.
7. Ask OpenClaw to return only the JSON contract from `SKILL.md`.
8. Save the model output to `runs/latest/model_state.json`.
9. Run:

```bash
python state-assessment/aggregate_state.py \
  --model-json runs/latest/model_state.json \
  --output-json runs/latest/state_result.json
```

If the screenshots are ambiguous, set `state` to `unknown`, `confidence` below `0.5`, and `should_interact` to `false`.

Never attach frames from a rejected manifest, discarded frame sample, partial failed run, or any frame where `privacy_status` is not `protected`.

Defaults are read from the `state_assessment` section of `config.yaml`. Command-line flags override those defaults for one run.
