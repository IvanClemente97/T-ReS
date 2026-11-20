# -*- coding: utf-8 -*-
"""Small Shared Memory reader for Assetto Corsa's embedded Python runtime."""
import math
import mmap
import struct


_PHYSICS_SIZE = 348
_GRAPHICS_SIZE = 280
_STATIC_SIZE = 512


class ACSharedMemoryReader(object):
    def __init__(self):
        self._physics = None
        self._graphics = None
        self._static = None

    def _open(self):
        if self._physics is None:
            self._physics = mmap.mmap(0, _PHYSICS_SIZE, "acpmf_physics")
        if self._graphics is None:
            self._graphics = mmap.mmap(0, _GRAPHICS_SIZE, "acpmf_graphics")
        if self._static is None:
            self._static = mmap.mmap(0, _STATIC_SIZE, "acpmf_static")

    @staticmethod
    def _read(mapping, size):
        mapping.seek(0)
        return mapping.read(size)

    @staticmethod
    def _valid_time(value):
        return value if 0 < value <= 600000 else None

    @staticmethod
    def _unit(value):
        return float(value) if math.isfinite(value) and 0.0 <= value <= 1.0 else None

    def read(self):
        self._open()
        physics_first = self._read(self._physics, _PHYSICS_SIZE)
        graphics_first = self._read(self._graphics, _GRAPHICS_SIZE)
        physics = self._read(self._physics, _PHYSICS_SIZE)
        graphics = self._read(self._graphics, _GRAPHICS_SIZE)
        static = self._read(self._static, _STATIC_SIZE)
        physics_id = struct.unpack_from("<i", physics, 0)[0]
        graphics_id = struct.unpack_from("<i", graphics, 0)[0]
        if (physics_id != struct.unpack_from("<i", physics_first, 0)[0]
                or graphics_id != struct.unpack_from("<i", graphics_first, 0)[0]):
            return None
        if struct.unpack_from("<i", graphics, 4)[0] != 2:
            return None

        throttle = struct.unpack_from("<f", physics, 4)[0]
        brake = struct.unpack_from("<f", physics, 8)[0]
        gear = struct.unpack_from("<i", physics, 16)[0] - 1
        rpm = struct.unpack_from("<i", physics, 20)[0]
        speed = struct.unpack_from("<f", physics, 28)[0]
        completed_laps = struct.unpack_from("<i", graphics, 132)[0]
        total_laps = struct.unpack_from("<i", graphics, 172)[0]
        track_position = struct.unpack_from("<f", graphics, 248)[0]
        current_lap = struct.unpack_from("<i", graphics, 140)[0]
        last_lap = struct.unpack_from("<i", graphics, 144)[0]
        best_lap = struct.unpack_from("<i", graphics, 148)[0]
        sector = struct.unpack_from("<i", graphics, 164)[0]
        last_sector = struct.unpack_from("<i", graphics, 168)[0]
        car_model = static[68:134].decode("utf-16-le", "replace").split("\0", 1)[0].strip()

        if (not math.isfinite(speed) or not 0 <= speed <= 600
                or not 0 <= rpm <= 30000 or not -1 <= gear <= 10
                or completed_laps < 0 or not 0 <= sector < 16
                or not car_model):
            return None

        player = {
            "source": "assetto_corsa_shared_memory",
            "speed_kmh": float(speed),
            "throttle": self._unit(throttle),
            "brake": self._unit(brake),
            "gear": gear,
            "rpm": rpm,
            "completed_laps": completed_laps,
            "total_laps": total_laps if 0 <= total_laps <= 1000 else None,
            "track_position": self._unit(track_position),
            "current_lap_time_ms": self._valid_time(current_lap),
            "last_lap_time_ms": self._valid_time(last_lap),
            "best_lap_time_ms": self._valid_time(best_lap),
            "current_sector_index": sector,
            "last_sector_time_ms": self._valid_time(last_sector),
            "car_model": car_model,
        }
        player["availability"] = {}
        for name in (
                "speed_kmh", "throttle", "brake", "gear", "rpm",
                "completed_laps", "total_laps", "track_position",
                "current_lap_time_ms", "last_lap_time_ms",
                "best_lap_time_ms", "current_sector_index",
                "last_sector_time_ms"):
            player["availability"][name] = (
                "available" if player[name] is not None else "unavailable")
        return player

    def close(self):
        for mapping in (self._physics, self._graphics, self._static):
            if mapping is not None:
                try:
                    mapping.close()
                except Exception:
                    pass
        self._physics = self._graphics = self._static = None
