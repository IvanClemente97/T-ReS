# -*- coding: utf-8 -*-
"""Assetto Corsa in-game bridge. Compatible with its embedded Python 3 runtime."""
import json
import math
import os
import sys
import time

import ac
import acsys

from t_res_ac_shared_memory import ACSharedMemoryReader


PROTOCOL_VERSION = 1
SEND_INTERVAL = 1.0 / 40.0
MAX_CARS = 60
SNAPSHOT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "telemetry.json")

_app = None
_reader = None
_elapsed = 0.0
_last_log = {}
_last_lap = None
_last_sector = None
_last_track_key = None
_personal_best_sectors = [None] * 16
_sector_colors = [None] * 16


def _log_limited(key, message, interval=10.0):
    now = time.time()
    if now - _last_log.get(key, 0.0) >= interval:
        _last_log[key] = now
        ac.log("T-ReS bridge: " + message)


def _text(value):
    if value is None:
        return None
    try:
        value = str(value).strip()
    except Exception:
        return None
    return value[:96] if value else None


def _number(value, low=None, high=None):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result):
        return None
    if low is not None and result < low:
        return None
    if high is not None and result > high:
        return None
    return result


def _integer(value, low=None, high=None):
    try:
        if isinstance(value, bool):
            return None
        result = int(value)
    except (TypeError, ValueError):
        return None
    if low is not None and result < low:
        return None
    if high is not None and result > high:
        return None
    return result


def _car_value(car_id, state_name):
    state = getattr(acsys.CS, state_name, None)
    if state is None:
        return None
    try:
        return ac.getCarState(car_id, state)
    except Exception:
        return None


def _world_position(car_id):
    value = _car_value(car_id, "WorldPosition")
    try:
        if hasattr(value, "x") and hasattr(value, "z"):
            x, z = float(value.x), float(value.z)
        else:
            x, z = float(value[0]), float(value[2])
    except (TypeError, ValueError, IndexError, AttributeError):
        return None, None
    if not math.isfinite(x) or not math.isfinite(z) or abs(x) > 100000 or abs(z) > 100000:
        return None, None
    return x, z


def _position(car_id, method_name):
    method = getattr(ac, method_name, None)
    if method is None:
        return None
    try:
        return _integer(method(car_id), 1, MAX_CARS)
    except Exception:
        return None


def _update_sector_colors(player, track_key):
    global _last_lap, _last_sector, _last_track_key
    global _personal_best_sectors, _sector_colors
    lap = player.get("completed_laps")
    sector = player.get("current_sector_index")
    sector_time = player.get("last_sector_time_ms")
    if lap is None or sector is None:
        player["sector_colors"] = list(_sector_colors)
        return
    if track_key != _last_track_key:
        _last_track_key = track_key
        _last_lap = lap
        _last_sector = sector
        _personal_best_sectors = [None] * 16
        _sector_colors = [None] * 16
        player["sector_colors"] = list(_sector_colors)
        return
    if _last_lap is None:
        _last_lap = lap
        _last_sector = sector
        player["sector_colors"] = list(_sector_colors)
        return
    if lap > _last_lap and _last_sector is not None:
        _record_sector(_last_sector, sector_time, False)
    elif lap == _last_lap and _last_sector is not None and sector != _last_sector:
        crossed = sector == _last_sector + 1 or (sector == 0 and _last_sector > 0)
        if crossed:
            _record_sector(_last_sector, sector_time, True)
    if lap != _last_lap:
        if lap < _last_lap:
            _personal_best_sectors = [None] * 16
        _sector_colors = [None] * 16
        _last_lap = lap
    _last_sector = sector
    player["sector_colors"] = list(_sector_colors)


def _record_sector(sector, sector_time, paint):
    if sector_time is None or sector_time <= 0:
        return
    personal_best = _personal_best_sectors[sector]
    color = "green" if personal_best is None or sector_time <= personal_best else "yellow"
    if personal_best is None or sector_time < personal_best:
        _personal_best_sectors[sector] = sector_time
    if paint:
        _sector_colors[sector] = color


def _build_cars(player):
    cars = []
    try:
        count = max(0, min(int(ac.getCarsCount()), MAX_CARS))
    except Exception:
        return cars
    for car_id in range(count):
        try:
            if not ac.isConnected(car_id):
                continue
            lap_count = _integer(_car_value(car_id, "LapCount"), 0, 10000)
            spline = _number(_car_value(car_id, "NormalizedSplinePosition"), 0.0, 1.0)
            if lap_count is None:
                continue
            x, z = _world_position(car_id)
            cars.append({
                "car_id": car_id,
                "source": "assetto_corsa_python_api",
                "is_player": car_id == 0,
                "driver_name": _text(ac.getDriverName(car_id)),
                "car_name": _text(ac.getCarName(car_id)),
                "lap_count": lap_count,
                "official_position": _position(car_id, "getCarLeaderboardPosition"),
                "realtime_position": _position(car_id, "getCarRealTimeLeaderboardPosition"),
                "best_lap_time_ms": (
                    player.get("best_lap_time_ms") if car_id == 0 else None
                ),
                "world_x": x,
                "world_z": z,
                "track_position": spline,
            })
        except Exception as error:
            _log_limited("car-%d" % car_id, "could not read car %d: %s" % (car_id, error))
    return cars


def _write_snapshot(snapshot):
    temporary = SNAPSHOT_PATH + ".tmp"
    try:
        with open(temporary, "w") as output:
            json.dump(snapshot, output, separators=(",", ":"), ensure_ascii=True)
            output.flush()
        os.replace(temporary, SNAPSHOT_PATH)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def acMain(ac_version):
    global _app, _reader
    _reader = ACSharedMemoryReader()
    _app = ac.newApp("T-ReS Telemetry")
    ac.setSize(_app, 2, 2)
    ac.drawBorder(_app, 0)
    ac.setBackgroundOpacity(_app, 0)
    ac.log("T-ReS bridge loaded; Python %s; snapshot: %s" % (
        sys.version.split()[0], SNAPSHOT_PATH))
    return "T-ReS Telemetry"


def acUpdate(delta_t):
    global _elapsed
    if not isinstance(delta_t, (int, float)) or not math.isfinite(delta_t) or delta_t < 0:
        _log_limited("delta", "Assetto Corsa supplied an invalid update interval.")
        return
    _elapsed += delta_t
    if _elapsed < SEND_INTERVAL:
        return
    _elapsed %= SEND_INTERVAL
    try:
        player = _reader.read() if _reader is not None else None
    except Exception as error:
        _log_limited("shared-memory", "Shared Memory is unavailable: %s" % error)
        return
    if player is None:
        return
    try:
        track = _text(ac.getTrackName(0))
    except Exception:
        track = None
    try:
        layout = _text(ac.getTrackConfiguration(0))
    except Exception:
        layout = None
    _update_sector_colors(player, (track, layout))
    snapshot = {
        "protocol_version": PROTOCOL_VERSION,
        "simulator": "assetto_corsa_2014",
        "published_at_unix_s": time.time(),
        "track": track,
        "layout": layout,
        "session_type": None,
        "lap_times_complete": False,
        "player": player,
        "cars": _build_cars(player),
    }
    try:
        _write_snapshot(snapshot)
    except Exception as error:
        _log_limited("write", "could not write snapshot: %s" % error)


def acShutdown():
    global _reader
    if _reader is not None:
        _reader.close()
        _reader = None
