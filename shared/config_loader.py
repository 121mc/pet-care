from pathlib import Path


def repo_root_from(script_file):
    return Path(script_file).resolve().parents[1]


def default_config_path(script_file):
    return repo_root_from(script_file) / "config.yaml"


def load_yaml(path):
    try:
        import yaml  # type: ignore
    except Exception as exc:
        raise RuntimeError("Install PyYAML before loading YAML configuration.") from exc

    config_path = Path(path)
    if not config_path.exists():
        return {}
    with config_path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def load_config(path):
    return load_yaml(path)


def section(config, name):
    value = config.get(name, {})
    return value if isinstance(value, dict) else {}


def csv_value(value, default):
    if value is None:
        return default
    if isinstance(value, (list, tuple)):
        return ",".join(str(item) for item in value)
    return str(value)


def bool_value(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default
