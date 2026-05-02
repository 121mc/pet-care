import json
from urllib import request


def send_action(device, action):
    base_url = str(device.get("base_url", "")).rstrip("/")
    if not base_url:
        raise ValueError("HTTP device requires base_url.")

    endpoints = device.get("endpoints", {})
    endpoint = endpoints.get(action["id"]) or action.get("endpoint") or "/action"
    url = base_url + "/" + str(endpoint).lstrip("/")
    method = str(action.get("method", "POST")).upper()
    timeout = float(device.get("timeout_seconds", 5.0))
    payload = action.get(
        "payload",
        {
            "action": action["id"],
            "intensity": action.get("intensity"),
            "max_duration_seconds": action.get("max_duration_seconds"),
        },
    )

    data = None
    headers = {"Content-Type": "application/json"}
    if method in {"POST", "PUT", "PATCH"}:
        data = json.dumps(payload).encode("utf-8")

    req = request.Request(url=url, data=data, headers=headers, method=method)
    with request.urlopen(req, timeout=timeout) as response:
        body = response.read().decode("utf-8", errors="replace")

    return {
        "status": "sent",
        "protocol": "http",
        "url": url,
        "action": action["id"],
        "response_status": response.status,
        "response_body": body[:500],
    }
