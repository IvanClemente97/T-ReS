import os
import json
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication

from t_res.dashboard.widgets import (
    COLORS,
    RaceMapWidget,
    _lap_ring_color,
    _map_car_color,
)
from t_res.domain.models import parse_snapshot


def _snapshot(cars, *, simulator="assetto_corsa_2014", **player_updates):
    player = {
        "source": "test",
        "speed_kmh": 100.0,
        "throttle": 0.5,
        "brake": 0.0,
        "gear": 4,
        "rpm": 6000,
        "completed_laps": 3,
        "total_laps": 10,
        "track_position": 0.5,
        "current_lap_time_ms": 50000,
        "last_lap_time_ms": None,
        "best_lap_time_ms": None,
        "current_sector_index": 1,
        "last_sector_time_ms": None,
        "sector_colors": [],
        "availability": {},
    }
    player.update(player_updates)
    return parse_snapshot(json.dumps({
        "protocol_version": 1,
        "simulator": simulator,
        "published_at_unix_s": 1000.0,
        "track": "test",
        "layout": None,
        "session_type": None,
        "lap_times_complete": False,
        "player": player,
        "cars": cars,
    }), now=1000.0)


def _car(car_id, **updates):
    car = {
        "car_id": car_id,
        "source": "test",
        "is_player": car_id == 0,
        "driver_name": "Driver",
        "car_name": "Car",
        "lap_count": 3,
        "official_position": car_id + 1,
        "realtime_position": car_id + 1,
        "best_lap_time_ms": None,
        "world_x": float(car_id),
        "world_z": float(car_id),
        "track_position": 0.5,
        "speed_kmh": 100.0,
    }
    car.update(updates)
    return car


class DashboardWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_map_target_rect_fits_pixmap_without_qsize_conversion_errors(self):
        widget = RaceMapWidget()
        widget.resize(640, 480)
        widget._pixmap = QPixmap(100, 50)

        target = widget._target_rect()

        self.assertEqual(target.width(), 608)
        self.assertEqual(target.height(), 304)
        self.assertEqual(target.center().x(), 320)
        self.assertEqual(target.center().y(), 240)

    def test_map_uses_white_for_single_class_and_distinct_colors_for_multiclass(self):
        single_class = _snapshot([
            _car(0, is_player=True, vehicle_class="GT3"),
            _car(1, is_player=False, vehicle_class="GT3"),
        ])
        self.assertEqual(
            _map_car_color(single_class, single_class.cars[1]), "#F1F3F5"
        )

        multiclass = _snapshot([
            _car(0, is_player=True, vehicle_class="GT3"),
            _car(1, is_player=False, vehicle_class="GT3"),
            _car(2, is_player=False, vehicle_class="LMP2"),
        ])
        self.assertNotEqual(
            _map_car_color(multiclass, multiclass.cars[1]),
            _map_car_color(multiclass, multiclass.cars[2]),
        )

    def test_map_does_not_infer_categories_when_metadata_is_missing(self):
        unknown = _snapshot([
            _car(0, is_player=True, brand="Brand A"),
            _car(1, is_player=False, brand="Brand B"),
        ])

        self.assertEqual(_map_car_color(unknown, unknown.cars[0]), "#AAB2BD")
        self.assertEqual(_map_car_color(unknown, unknown.cars[1]), "#AAB2BD")

    def test_f1_marker_uses_only_an_explicit_team_color(self):
        snapshot = _snapshot([
            _car(0, is_player=True, vehicle_class="F1", team_color="#C8102E"),
            _car(1, is_player=False, vehicle_class="F1", team_color="#00A3E0"),
        ], simulator="f1_25")

        self.assertEqual(_map_car_color(snapshot, snapshot.cars[0]), "#C8102E")
        self.assertEqual(_map_car_color(snapshot, snapshot.cars[1]), "#00A3E0")

    def test_map_ring_distinguishes_lapped_and_nearby_lapping_cars(self):
        snapshot = _snapshot([
            _car(0, is_player=True),
            _car(1, is_player=False, lap_count=2),
            _car(
                2, is_player=False, lap_count=4,
                track_position=0.49, speed_kmh=110.0,
            ),
        ])

        self.assertEqual(
            _lap_ring_color(snapshot, snapshot.cars[1]), COLORS["lapped"]
        )
        self.assertEqual(
            _lap_ring_color(snapshot, snapshot.cars[2]), COLORS["lapping_player"]
        )

        no_speed = _snapshot([
            _car(0, is_player=True),
            _car(1, is_player=False, lap_count=4, track_position=0.49, speed_kmh=None),
        ])
        self.assertIsNone(_lap_ring_color(no_speed, no_speed.cars[1]))

        distant = _snapshot([
            _car(0, is_player=True),
            _car(1, is_player=False, lap_count=4, track_position=0.4, speed_kmh=110.0),
        ])
        self.assertIsNone(_lap_ring_color(distant, distant.cars[1]))


if __name__ == "__main__":
    unittest.main()
