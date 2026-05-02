def send_action(device, action):
    return {
        "status": "simulated",
        "protocol": "mock",
        "device_id": device.get("id", "mock-device"),
        "action": action["id"],
        "intensity": action.get("intensity"),
        "max_duration_seconds": action.get("max_duration_seconds"),
    }
