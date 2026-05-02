# Remote Interaction

Use hardware only after state assessment and safety filtering. Runtime defaults come from `config.yaml`; the policy file remains the authority for safety limits.

## Hardware Registry

`hardware_registry.yaml` is empty by default:

```yaml
devices: []
```

When hardware is connected, add devices like:

```yaml
devices:
  - id: esp32-toy-01
    name: Servo toy
    enabled: true
    protocol: serial
    capabilities: [short_play]
    port: COM3
    baudrate: 115200
    commands:
      short_play: PLAY_SHORT
```

Supported protocols:

- `serial`: uses `drivers/serial_driver.py`.
- `http`: uses `drivers/http_driver.py`.
- `mock`: uses `drivers/mock_driver.py` for demos.

## Execution

Dry run:

```bash
python remote-interaction/execute_interaction.py \
  --state-json runs/latest/state_result.json
```

The script reads these defaults from `config.yaml`:

- `remote_interaction.registry`
- `remote_interaction.policy`
- `remote_interaction.log_path`
- `remote_interaction.dry_run_by_default`
- `remote_interaction.global_cooldown_seconds`

Override the config file when needed:

```bash
python remote-interaction/execute_interaction.py \
  --config config.yaml \
  --state-json runs/latest/state_result.json
```

Real hardware execution requires explicit runtime permission:

```bash
python remote-interaction/execute_interaction.py \
  --state-json runs/latest/state_result.json \
  --allow-hardware
```

If `interaction_policy.yaml` has `require_explicit_hardware_enable: true`, setting `allow_hardware_by_default: true` in `config.yaml` is not enough. The user must still pass `--allow-hardware` for that run.

## Safety Gates

Before a driver is called, `execute_interaction.py` must pass all gates:

- `state_result.should_interact` must be `true`.
- The state policy must allow interaction for that state.
- The selected action must exist in `interaction_policy.yaml`.
- An enabled device must provide the required capability.
- Explicit hardware permission must be present when required by policy.
- Dry run must be off; `--allow-hardware` turns it off for that invocation.
- Global cooldown must not be active based on the previous interaction log.
- Device intensity limits must allow the action intensity.

The effective action duration is the strictest positive limit from:

- the action's `max_duration_seconds`
- `safety.max_action_duration_seconds`
- the device's optional `max_action_duration_seconds`

The driver receives the resulting `intensity` and `max_duration_seconds`. Driver errors are logged; when `stop_on_driver_error` is `true`, the command exits non-zero.
