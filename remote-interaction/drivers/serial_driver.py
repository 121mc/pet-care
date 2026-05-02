def send_action(device, action):
    try:
        import serial  # type: ignore
    except Exception as exc:
        raise RuntimeError("Install pyserial before using serial hardware.") from exc

    port = device.get("port")
    if not port:
        raise ValueError("Serial device requires a port.")

    baudrate = int(device.get("baudrate", 115200))
    commands = device.get("commands", {})
    command = commands.get(action["id"]) or action.get("command")
    if not command:
        raise ValueError(f"No serial command configured for action {action['id']}.")

    timeout = float(device.get("timeout_seconds", 2.0))
    with serial.Serial(port=port, baudrate=baudrate, timeout=timeout) as ser:
        payload = str(command).strip().encode("utf-8") + b"\n"
        ser.write(payload)
        ser.flush()

    return {
        "status": "sent",
        "protocol": "serial",
        "port": port,
        "action": action["id"],
    }
