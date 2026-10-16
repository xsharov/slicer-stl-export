import enum
import json


class Delivery(enum.Enum):
    SENT = "sent"
    REUSED = "reused"
    LAUNCHED = "launched"
    QUEUED = "queued"


class SlicerError(Exception):
    pass


def single_instance_enabled(config_path):
    try:
        with open(config_path, encoding="utf-8") as stream:
            lines = [line for line in stream if not line.lstrip().startswith("#")]
        app = json.loads("".join(lines)).get("app", {})
    except (OSError, ValueError, AttributeError):
        return False
    return app.get("single_instance") in (True, 1, "1", "true")
