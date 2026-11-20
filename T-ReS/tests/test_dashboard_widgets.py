import os
import json
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication

from t_res.dashboard.widgets import (
    COLORS,
    LeaderboardWidget,
    RaceMapWidget,
    _gap_labels,
    _lap_ring_color,
    _map_car_color,
    _ranking_positions,
    _track_length_from_ui_track,
)
from t_res.domain.models import parse_snapshot


def _snapshot(
    cars, *, simulator="assetto_corsa_2014", lap_times_complete=False,
    **player_updates
):
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
        "lap_times_complete": lap_times_complete,
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
        "display_name": None,
        "lap_count": 3,
        "official_position": car_id + 1,
        "realtime_position": car_id + 1,
        "best_lap_time_ms": None,
        "finished": None,
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

        self.assertEqual(target.width(), 438)
        self.assertEqual(target.height(), 219)
        self.assertEqual(target.center().x(), 405)
        self.assertEqual(target.center().y(), 240)

    def test_map_status_cards_stack_at_left_without_covering_the_map(self):
        widget = RaceMapWidget()
        widget.resize(640, 480)

        laps_card, fastest_card = widget._status_overlay_rects()
        map_bounds = widget._map_bounds()

        self.assertEqual(laps_card.left(), fastest_card.left())
        self.assertGreater(fastest_card.top(), laps_card.bottom())
        self.assertLess(laps_card.right(), map_bounds.left())
        self.assertLess(fastest_card.right(), map_bounds.left())

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

    def test_positions_use_one_complete_unique_source_for_the_whole_field(self):
        snapshot = _snapshot([
            _car(0, realtime_position=1, official_position=1),
            _car(1, realtime_position=1, official_position=2),
            _car(2, realtime_position=None, official_position=3),
        ])

        self.assertEqual(
            _ranking_positions(snapshot.cars), {0: 1, 1: 2, 2: 3}
        )

    def test_gap_is_derived_from_progress_and_official_track_length(self):
        snapshot = _snapshot([
            _car(0, official_position=1, realtime_position=None,
                 lap_count=4, track_position=0.25),
            _car(1, official_position=2, realtime_position=None,
                 lap_count=4, track_position=0.225),
            _car(2, official_position=3, realtime_position=None,
                 lap_count=3, track_position=0.20),
        ])
        positions = _ranking_positions(snapshot.cars)

        self.assertEqual(
            _gap_labels(snapshot.cars, positions, 4000.0),
            {0: "—", 1: "+100 m", 2: "+1 V"},
        )
        self.assertEqual(_gap_labels(snapshot.cars, positions, None)[1], "—")

    def test_leaderboard_shows_display_names_gap_and_finished_state(self):
        snapshot = _snapshot([
            _car(0, is_player=True, official_position=1, realtime_position=1,
                 display_name="Ferrari SF15-T", best_lap_time_ms=90000,
                 lap_count=4, track_position=0.25, finished=True,
                 vehicle_class="GT3"),
            _car(1, official_position=2, realtime_position=1,
                 display_name="Mercedes AMG GT3", best_lap_time_ms=91000,
                 lap_count=4, track_position=0.225, finished=False,
                 vehicle_class="GT3"),
        ], lap_times_complete=True)
        leaderboard = LeaderboardWidget()

        leaderboard.set_snapshot(snapshot, 4000.0)

        table = leaderboard.class_tables["gt3"]
        self.assertEqual(table.horizontalHeaderItem(3).text(), "Vueltas")
        self.assertEqual(table.horizontalHeaderItem(4).text(), "GAP")
        self.assertEqual(table.item(0, 0).text(), "P1  ✓")
        self.assertEqual(table.item(0, 2).text(), "Ferrari SF15-T")
        self.assertEqual(table.item(0, 4).text(), "—")
        self.assertEqual(table.item(1, 0).text(), "P2  ▶")
        self.assertEqual(table.item(1, 2).text(), "Mercedes AMG GT3")
        self.assertEqual(table.item(1, 4).text(), "+100 m")
        self.assertEqual(
            table.item(0, 1).foreground().color().name(),
            COLORS["purple"].lower(),
        )
        self.assertNotEqual(
            table.item(0, 2).foreground().color().name(),
            COLORS["purple"].lower(),
        )

    def test_leaderboard_gives_each_vehicle_class_an_independent_ranking(self):
        snapshot = _snapshot([
            _car(0, official_position=1, realtime_position=1,
                 vehicle_class="LMP1", lap_count=3),
            _car(1, official_position=2, realtime_position=2,
                 vehicle_class="GT3", lap_count=3),
            _car(2, official_position=3, realtime_position=3,
                 vehicle_class="GT2", lap_count=3),
            _car(3, official_position=4, realtime_position=4,
                 vehicle_class="GT3", lap_count=2),
        ])
        leaderboard = LeaderboardWidget()

        leaderboard.set_snapshot(snapshot, 4000.0)

        tables = leaderboard.class_tables
        self.assertEqual(list(tables), ["lmp1", "gt3", "gt2"])
        self.assertEqual(tables["lmp1"].item(0, 0).text(), "P1")
        self.assertEqual(tables["gt2"].item(0, 0).text(), "P1")
        self.assertEqual(tables["gt3"].rowCount(), 2)
        self.assertEqual(tables["gt3"].item(0, 0).text(), "P1")
        self.assertEqual(tables["gt3"].item(1, 0).text(), "P2")
        self.assertEqual(tables["gt3"].item(0, 3).text(), "3")
        self.assertEqual(tables["gt3"].item(1, 3).text(), "2")

    def test_leaderboard_refresh_does_not_detach_tables_into_windows(self):
        snapshot = _snapshot([
            _car(0, official_position=1, realtime_position=1,
                 display_name="Car A", vehicle_class="GT3", lap_count=3),
            _car(1, official_position=2, realtime_position=2,
                 display_name="Car B", vehicle_class="GT3", lap_count=2),
        ])
        updated_snapshot = _snapshot([
            _car(0, official_position=1, realtime_position=2,
                 display_name="Car A", vehicle_class="GT3", lap_count=4),
            _car(1, official_position=2, realtime_position=1,
                 display_name="Car B", vehicle_class="GT3", lap_count=3),
        ])
        leaderboard = LeaderboardWidget()
        leaderboard.set_snapshot(snapshot)
        table = leaderboard.class_tables["gt3"]

        leaderboard.set_snapshot(updated_snapshot)

        self.assertIs(leaderboard.class_tables["gt3"], table)
        self.assertFalse(table.isWindow())
        self.assertEqual(table.item(0, 2).text(), "Car B")
        self.assertEqual(table.item(0, 3).text(), "3")

    def test_track_length_comes_from_layout_ui_metadata(self):
        from pathlib import Path
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            metadata = Path(directory) / "ks_barcelona" / "ui" / "layout_moto"
            metadata.mkdir(parents=True)
            (metadata / "ui_track.json").write_text(
                '{"length":"4727"}', encoding="utf-8"
            )

            self.assertEqual(
                _track_length_from_ui_track(
                    Path(directory), "ks_barcelona", "layout_moto"
                ),
                4727.0,
            )


if __name__ == "__main__":
    unittest.main()
