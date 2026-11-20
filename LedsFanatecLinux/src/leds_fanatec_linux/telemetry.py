"""Lectura validada de puentes reales de telemetría para Assetto Corsa."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
import time

from .models import AC_FLAG_MAP, Telemetry, TelemetryDataError

MAX_SNAPSHOT_BYTES = 256 * 1024
MAX_FEED_AGE = 1.5


def default_feed_paths() -> tuple[tuple[str, Path], ...]:
    rivals_override = os.environ.get("FANATEC_RIVALS_TELEMETRY_PATH")
    tres_override = os.environ.get("TRES_TELEMETRY_PATH")
    steam_roots = (
        Path.home() / ".local/share/Steam/steamapps/common/assettocorsa",
        Path.home() / ".steam/steam/steamapps/common/assettocorsa",
    )
    candidates: list[tuple[str, Path]] = []
    for root in steam_roots:
        candidates.append(
            (
                "Fanatec Rivals bridge",
                Path(rivals_override)
                if rivals_override
                else root / "apps/python/FanatecRivals/rivals.json",
            )
        )
        candidates.append(
            (
                "T-ReS bridge",
                Path(tres_override)
                if tres_override
                else root / "apps/python/TReS/telemetry.json",
            )
        )
    unique: list[tuple[str, Path]] = []
    seen: set[Path] = set()
    for name, path in candidates:
        resolved = path.expanduser()
        if resolved not in seen:
            seen.add(resolved)
            unique.append((name, resolved))
    return tuple(unique)


def _number(data: dict, key: str, minimum: float, maximum: float) -> float | None:
    value = data.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TelemetryDataError(f"{key} no es numérico.")
    value = float(value)
    if not math.isfinite(value) or not minimum <= value <= maximum:
        raise TelemetryDataError(f"{key} está fuera de rango.")
    return value


def _boolean(data: dict, key: str) -> bool | None:
    value = data.get(key)
    if value is None:
        return None
    if type(value) is not bool:
        raise TelemetryDataError(f"{key} no es booleano.")
    return value


def _read_json(path: Path, now: float) -> tuple[dict, float]:
    with path.open("rb") as file:
        stat = os.fstat(file.fileno())
        if stat.st_size > MAX_SNAPSHOT_BYTES:
            raise TelemetryDataError("El snapshot excede el tamaño permitido.")
        payload = file.read(MAX_SNAPSHOT_BYTES + 1)
    if len(payload) > MAX_SNAPSHOT_BYTES:
        raise TelemetryDataError("El snapshot excede el tamaño permitido.")
    age = time.time() - stat.st_mtime
    if age < -2 or age > MAX_FEED_AGE:
        raise TelemetryDataError("El snapshot está obsoleto.")
    raw = json.loads(payload)
    if not isinstance(raw, dict):
        raise TelemetryDataError("La raíz del snapshot debe ser un objeto JSON.")
    return raw, now


def _sample(
    *,
    source: str,
    player: dict,
    simulator: str,
    received_at: float,
    flags_field: str | None,
    has_tres_protocol: bool,
) -> Telemetry:
    if has_tres_protocol:
        published = _number(player, "_published_at", 0, time.time() + 2)
        if published is None or time.time() - published > MAX_FEED_AGE:
            raise TelemetryDataError("El snapshot de T-ReS está obsoleto.")

    raw_max_rpm = player.get("max_rpm")
    if raw_max_rpm is not None and (
        type(raw_max_rpm) is not int or not 1000 <= raw_max_rpm <= 30000
    ):
        raise TelemetryDataError("max_rpm debe ser un entero entre 1000 y 30000.")
    max_rpm = raw_max_rpm
    flags_available = flags_field is not None
    active_flags = frozenset()
    if flags_field is not None:
        if flags_field in player:
            raw_flag = player[flags_field]
            if type(raw_flag) is not int or not 0 <= raw_flag <= 6:
                raise TelemetryDataError("El valor de bandera de Assetto Corsa no es válido.")
            flag_name = AC_FLAG_MAP.get(raw_flag)
            if flag_name:
                active_flags = frozenset({flag_name})
        else:
            flags_available = False

    raw_gear = player.get("gear")
    if raw_gear is not None and (type(raw_gear) is not int or not -1 <= raw_gear <= 10):
        raise TelemetryDataError("gear debe ser un entero entre -1 y 10.")

    return Telemetry(
        simulator=simulator,
        source=source,
        received_at=received_at,
        rpm=_number(player, "rpm", 0, 30000),
        max_rpm=max_rpm,
        speed_kmh=_number(player, "speed_kmh", 0, 600),
        gear=raw_gear,
        throttle=_number(player, "throttle", 0, 1),
        brake=_number(player, "brake", 0, 1),
        is_in_pit_lane=_boolean(player, "is_in_pit_lane"),
        pit_limiter_on=_boolean(player, "pit_limiter_on"),
        active_flags=active_flags,
        flags_available=flags_available,
    )


def parse_rivals_snapshot(raw: dict, source: str, received_at: float) -> Telemetry:
    if raw.get("version") != 4:
        raise TelemetryDataError("Versión de Fanatec Rivals no compatible.")
    player = raw.get("player_telemetry")
    if not isinstance(player, dict):
        raise TelemetryDataError("Fanatec Rivals no publicó player_telemetry.")
    return _sample(
        source=source,
        player=player,
        simulator="assetto_corsa_2014",
        received_at=received_at,
        flags_field="flags",
        has_tres_protocol=False,
    )


def parse_tres_snapshot(raw: dict, source: str, received_at: float) -> Telemetry:
    if raw.get("protocol_version") != 1 or raw.get("simulator") != "assetto_corsa_2014":
        raise TelemetryDataError("Formato de snapshot T-ReS no compatible.")
    player = raw.get("player")
    if not isinstance(player, dict):
        raise TelemetryDataError("T-ReS no publicó los datos del piloto.")
    published_at = raw.get("published_at_unix_s")
    if isinstance(published_at, bool) or not isinstance(published_at, (int, float)):
        raise TelemetryDataError("T-ReS no publicó una fecha de actualización válida.")
    player_with_timestamp = dict(player)
    player_with_timestamp["_published_at"] = published_at
    return _sample(
        source=source,
        player=player_with_timestamp,
        simulator="assetto_corsa_2014",
        received_at=received_at,
        flags_field=None,
        has_tres_protocol=True,
    )


class AssettoCorsaTelemetryReader:
    """Prefiere el feed completo; usa T-ReS solo como fuente secundaria parcial."""

    def __init__(self, feeds: tuple[tuple[str, Path], ...] | None = None) -> None:
        self.feeds = feeds if feeds is not None else default_feed_paths()
        self.last_error: str | None = None

    def read(self) -> Telemetry | None:
        errors: list[str] = []
        now = time.monotonic()
        for name, path in self.feeds:
            try:
                raw, received_at = _read_json(path, now)
                if name == "Fanatec Rivals bridge":
                    sample = parse_rivals_snapshot(raw, name, received_at)
                elif name == "T-ReS bridge":
                    sample = parse_tres_snapshot(raw, name, received_at)
                else:
                    raise TelemetryDataError(f"Adaptador desconocido: {name}.")
                self.last_error = None
                return sample
            except FileNotFoundError:
                continue
            except (OSError, json.JSONDecodeError, TelemetryDataError, TypeError, ValueError) as error:
                errors.append(f"{name}: {error}")
        self.last_error = "; ".join(errors) if errors else None
        return None
