# State Assessment

Use OpenClaw multimodal reasoning on processed screenshots, then normalize the result.

## Steps

1. Load `prompt_template.md`.
2. Attach or reference the processed frames listed in `frames_manifest.json`.
3. Ask OpenClaw to return only the JSON contract from `SKILL.md`.
4. Save the model output to `runs/latest/model_state.json`.
5. Run:

```bash
python state-assessment/aggregate_state.py \
  --model-json runs/latest/model_state.json \
  --output-json runs/latest/state_result.json
```

If the screenshots are ambiguous, set `state` to `unknown`, `confidence` below `0.5`, and `should_interact` to `false`.
