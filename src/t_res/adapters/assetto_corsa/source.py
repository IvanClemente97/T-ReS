"""Read the atomic snapshot written by the in-game T-ReS bridge."""

from __future__ import annotations

import json
import math
from pathlib import Path
import struct
import time

from t_res.domain.models import (
    SIMULATOR_ID,
    TelemetrySnapshot,
    TelemetryValidationError,
    parse_snapshot,
)


_PHYSICS_SIZE = 348
_GRAPHICS_SIZE = 280
_LIVE_STATUS = 2


def read_snapshot(path: Path) -> TelemetrySnapshot:
    """Read one bounded-size snapshot and reject stale or malformed data."""
    try:
        if path.stat().st_size > 256 * 1024:
            raise ValueError("T-ReS snapshot exceeds 256 KiB.")
        payload = path.read_bytes()
    except FileNotFoundError as error:
        raise FileNotFoundError(f"Telemetry snapshot not found: {path}") from error
    if len(payload) > 256 * 1024:
        raise ValueError("T-ReS snapshot exceeds 256 KiB.")
    try:
        raw = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return parse_snapshot(payload, expected_simulator=SIMULATOR_ID)
    if isinstance(raw, dict):
        player = raw.get("player")
        cars = raw.get("cars")
        if (
            isinstance(player, dict)
            and not player.get("source")
            and all(
                isinstance(player.get(key), int)
                and not isinstance(player.get(key), bool)
                and player[key] >= 0
                for key in ("physics_packet_id", "graphics_packet_id")
            )
            and isinstance(cars, list)
            and any(
                isinstance(car, dict)
                and car.get("is_player") is True
                and car.get("source") == "assetto_corsa_python_api"
                for car in cars
            )
        ):
            normalized = dict(raw)
            normalized_player = dict(player)
            normalized_player["source"] = "assetto_corsa_shared_memory"
            normalized["player"] = normalized_player
            payload = json.dumps(normalized, separators=(",", ":")).encode("utf-8")
    return parse_snapshot(payload)


class AssettoCorsaSharedMemorySource:
    """Read player-only telemetry exposed by Assetto Corsa on Linux/Proton."""

    def __init__(self, root: Path = Path("/dev/shm"), stale_after: float = 1.0) -> None:
        self.root = root
        self.stale_after = stale_after
        self._last_packet_ids: tuple[int, int] | None = None
        self._last_change_monotonic: float | None = None

    def _read_stable_pages(self) -> tuple[bytes, bytes, int, int]:
        physics_path = self.root / "acpmf_physics"
        graphics_path = self.root / "acpmf_graphics"
        for attempt in range(10):
            physics_first = physics_path.read_bytes()
            graphics_first = graphics_path.read_bytes()
            physics = physics_path.read_bytes()
            graphics = graphics_path.read_bytes()
            if len(physics) < _PHYSICS_SIZE or len(graphics) < _GRAPHICS_SIZE:
                raise TelemetryValidationError("Assetto Corsa Shared Memory page is truncated.")
            physics_id = struct.unpack_from("<i", physics, 0)[0]
            graphics_id = struct.unpack_from("<i", graphics, 0)[0]
            if (physics_id == struct.unpack_from("<i", physics_first, 0)[0]
                    and graphics_id == struct.unpack_from("<i", graphics_first, 0)[0]):
                return physics, graphics, physics_id, graphics_id
            if attempt < 9:
                time.sleep(0.001)
        raise TelemetryValidationError("Could not read stable Shared Memory pages.")

    @staticmethod
    def _unit(value: float) -> float | None:
        return float(value) if math.isfinite(value) and 0 <= value <= 1 else None

    @staticmethod
    def _lap_time(value: int) -> int | None:
        return value if 0 < value <= 600000 else None

    def read(self) -> TelemetrySnapshot:
        physics, graphics, physics_id, graphics_id = self._read_stable_pages()
        if struct.unpack_from("<i", graphics, 4)[0] != _LIVE_STATUS:
            raise TelemetryValidationError("Assetto Corsa is not in a live session.")

        packet_ids = (physics_id, graphics_id)
        now_monotonic = time.monotonic()
        if packet_ids != self._last_packet_ids:
            self._last_packet_ids = packet_ids
            self._last_change_monotonic = now_monotonic
        elif (self._last_change_monotonic is None
              or now_monotonic - self._last_change_monotonic > self.stale_after):
            raise TelemetryValidationError("Assetto Corsa Shared Memory is stale.")

        throttle = self._unit(struct.unpack_from("<f", physics, 4)[0])
        brake = self._unit(struct.unpack_from("<f", physics, 8)[0])
        speed = struct.unpack_from("<f", physics, 28)[0]
        rpm = struct.unpack_from("<i", physics, 20)[0]
        gear = struct.unpack_from("<i", physics, 16)[0] - 1
        completed_laps = struct.unpack_from("<i", graphics, 132)[0]
        total_laps = struct.unpack_from("<i", graphics, 172)[0]
        track_position = self._unit(struct.unpack_from("<f", graphics, 248)[0])
        current_lap = struct.unpack_from("<i", graphics, 140)[0]
        last_lap = struct.unpack_from("<i", graphics, 144)[0]
        best_lap = struct.unpack_from("<i", graphics, 148)[0]
        sector = struct.unpack_from("<i", graphics, 164)[0]
        last_sector = struct.unpack_from("<i", graphics, 168)[0]

        player = {
            "source": "assetto_corsa_shared_memory",
            "speed_kmh": float(speed) if math.isfinite(speed) and 0 <= speed <= 600 else None,
            "throttle": throttle,
            "brake": brake,
            "gear": gear if -1 <= gear <= 10 else None,
            "rpm": rpm if 0 <= rpm <= 30000 else None,
            "completed_laps": completed_laps if 0 <= completed_laps <= 10000 else None,
            "total_laps": total_laps if 0 <= total_laps <= 1000 else None,
            "track_position": track_position,
            "current_lap_time_ms": self._lap_time(current_lap),
            "last_lap_time_ms": self._lap_time(last_lap),
            "best_lap_time_ms": self._lap_time(best_lap),
            "current_sector_index": sector if 0 <= sector < 16 else None,
            "last_sector_time_ms": self._lap_time(last_sector),
            "sector_colors": [],
            "availability": {},
        }
        for name in (
                "speed_kmh", "throttle", "brake", "gear", "rpm",
                "completed_laps", "total_laps", "track_position",
                "current_lap_time_ms", "last_lap_time_ms",
                "best_lap_time_ms", "current_sector_index",
                "last_sector_time_ms"):
            player["availability"][name] = (
                "available" if player[name] is not None else "unavailable"
            )

        packet = {
            "protocol_version": 1,
            "simulator": SIMULATOR_ID,
            "published_at_unix_s": time.time(),
            "track": None,
            "layout": None,
            "session_type": None,
            "lap_times_complete": False,
            "player": player,
            "cars": [],
        }
        return parse_snapshot(
            json.dumps(packet), stale_after=2.0, expected_simulator=SIMULATOR_ID
        )


class AssettoCorsaAdapter:
    """Combine the AC bridge snapshot with its player-only Shared Memory fallback."""

    simulator_id = SIMULATOR_ID
    display_name = "Assetto Corsa original (2014)"

    def __init__(self, snapshot_path: Path | None = None) -> None:
        self.snapshot_path = snapshot_path
        self._shared_memory = AssettoCorsaSharedMemorySource()

    def read(self) -> TelemetrySnapshot:
        if self.snapshot_path is None:
            return self._shared_memory.read()
        try:
            return read_snapshot(self.snapshot_path)
        except (OSError, ValueError):
            return self._shared_memory.read()
