"""Comandos locales de prueba entre la GUI y el servicio propietario del volante."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
import tempfile
import time
import uuid

from .models import FLAG_NAMES

STATE_ROOT = Path.home() / ".local/state/LedsFanatecLinux"
COMMAND_PATH = STATE_ROOT / "command.json"
TEST_ACTIONS = {"test_rpm", "test_rpm_max", "test_flag"}
COMMAND_MAX_AGE = 5.0


def send_test_command(
    action: str, flag: str | None = None, *, path: Path = COMMAND_PATH
) -> str:
    if action not in TEST_ACTIONS:
        raise ValueError(f"Acción de prueba no válida: {action}")
    if action == "test_flag" and flag not in FLAG_NAMES:
        raise ValueError("La prueba requiere una bandera conocida.")
    if action != "test_flag" and flag is not None:
        raise ValueError("Solo la prueba de bandera admite un nombre de bandera.")
    path.parent.mkdir(parents=True, exist_ok=True)
    command_id = str(uuid.uuid4())
    payload = {
        "id": command_id,
        "action": action,
        "flag": flag,
        "created_at": time.time(),
    }
    fd, temporary_name = tempfile.mkstemp(
        prefix=".command.", dir=path.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary_name, path)
    except BaseException:
        Path(temporary_name).unlink(missing_ok=True)
        raise
    return command_id


def read_test_command(path: Path = COMMAND_PATH) -> dict[str, object] | None:
    try:
        if path.stat().st_size > 4096:
            raise ValueError("El comando de prueba excede el tamaño permitido.")
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    if not isinstance(data, dict):
        raise ValueError("El comando de prueba debe ser un objeto JSON.")
    command_id = data.get("id")
    action = data.get("action")
    created_at = data.get("created_at")
    flag = data.get("flag")
    if not isinstance(command_id, str) or not isinstance(action, str):
        raise ValueError("Identificador o acción del comando no válidos.")
    try:
        uuid.UUID(command_id)
    except (ValueError, TypeError, AttributeError) as error:
        raise ValueError("El identificador del comando de prueba no es válido.") from error
    if action not in TEST_ACTIONS:
        raise ValueError("Acción de prueba no reconocida.")
    if action == "test_flag" and (
        not isinstance(flag, str) or flag not in FLAG_NAMES
    ):
        raise ValueError("Bandera de prueba no reconocida.")
    if action != "test_flag" and flag is not None:
        raise ValueError("Una prueba RPM no puede contener una bandera.")
    if (
        isinstance(created_at, bool)
        or not isinstance(created_at, (int, float))
        or not math.isfinite(created_at)
        or time.time() - created_at < -2
        or time.time() - created_at > COMMAND_MAX_AGE
    ):
        return None
    return {"id": command_id, "action": action, "flag": flag}
