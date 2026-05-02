# Pet State Assessment Prompt

Inspect the privacy-protected pet screenshots as a short time sequence. Use only observable evidence from the screenshots and any provided timestamps.

Classify the pet into exactly one state:

- `calm`
- `resting`
- `bored`
- `anxious`
- `alert`
- `unknown`

Return only valid JSON:

```json
{
  "state": "calm",
  "confidence": 0.0,
  "evidence": ["observable visual cue"],
  "risk_level": "low",
  "recommended_action": "none",
  "should_interact": false,
  "human_message": "Brief explanation for the owner."
}
```

Rules:

- Use `unknown` when the pet is not visible or the evidence is weak.
- Use `resting` when the pet appears asleep or quietly lying down.
- Use `alert` when the pet is fixated on a doorway, window, sound source, stranger, or possible hazard.
- Use `anxious` for repeated pacing, scratching, agitation, unsettled posture, or visible distress.
- Use `bored` for low stimulation, repeated wandering, toy-seeking, or attention-seeking without distress.
- Set `should_interact` to `false` for `calm`, `resting`, `unknown`, and high-risk `alert`.
- Do not provide medical diagnosis.
