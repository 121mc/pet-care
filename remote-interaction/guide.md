# Remote Interaction

Use hardware only after state assessment and safety filtering.

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
  --state-json runs/latest/state_result.json \
  --registry hardware_registry.yaml \
  --policy remote-interaction/interaction_policy.yaml
```

Real hardware execution requires:

```bash
python remote-interaction/execute_interaction.py \
  --state-json runs/latest/state_result.json \
  --registry hardware_registry.yaml \
  --policy remote-interaction/interaction_policy.yaml \
  --allow-hardware
```
