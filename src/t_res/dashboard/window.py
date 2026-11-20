"""Main PySide6 dashboard window."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import threading

from PySide6.QtCore import QSettings, QThread, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from t_res.adapters.protocol import TelemetryAdapter
from t_res.adapters.registry import (
    AdapterRegistration,
    adapter_registration,
    available_adapters,
    create_adapter,
)
from t_res.dashboard.widgets import LeaderboardWidget, RaceMapWidget, TelemetryTraceWidget
from t_res.domain.models import SIMULATOR_ID, TelemetrySnapshot


class SnapshotWorker(QThread):
    snapshot_ready = Signal(object)
    source_error = Signal(str)

    def __init__(self, adapter: TelemetryAdapter, parent=None) -> None:
        super().__init__(parent)
        self._adapter = adapter
        self._stop_requested = threading.Event()

    def set_adapter(self, adapter: TelemetryAdapter) -> None:
        self._stop_requested.set()
        self.wait(1000)
        self._adapter = adapter
        self._stop_requested.clear()
        if not self.isRunning():
            self.start()

    def stop(self) -> None:
        self._stop_requested.set()
        self.wait(1500)

    def run(self) -> None:
        last_publication: float | None = None
        last_error: str | None = None
        while not self._stop_requested.is_set():
            try:
                snapshot = self._adapter.read()
                if snapshot.published_at != last_publication:
                    self.snapshot_ready.emit(snapshot)
                    last_publication = snapshot.published_at
                last_error = None
            except (OSError, ValueError) as error:
                message = str(error)
                if message != last_error:
                    self.source_error.emit(message)
                    last_error = message
            self._stop_requested.wait(0.025)


class TReSWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("T-ReS | Telemetry RaceStudio")
        self.resize(1440, 900)
        self.settings = QSettings("T-ReS", "Telemetry RaceStudio")
        self.adapter_registrations = available_adapters()
        if not self.adapter_registrations:
            raise RuntimeError("T-ReS has no telemetry adapters registered.")
        saved_adapter_id = self.settings.value(
            "telemetry/simulator_id", self.adapter_registrations[0].simulator_id, str
        )
        self.adapter_id = next(
            (
                registration.simulator_id
                for registration in self.adapter_registrations
                if registration.simulator_id == saved_adapter_id
            ),
            self.adapter_registrations[0].simulator_id,
        )
        self.adapter_registration = adapter_registration(self.adapter_id)
        self.snapshot_path = self._load_path_setting(
            "snapshot_path",
            self.adapter_registration.default_snapshot_path,
            self._legacy_path_key("snapshot_path"),
        )
        self.tracks_root = self._load_path_setting(
            "tracks_root",
            self.adapter_registration.default_tracks_root,
            self._legacy_path_key("tracks_root"),
        )
        self.adapter = self._create_adapter()
        self._latest: TelemetrySnapshot | None = None
        self._last_lap_count: int | None = None

        central = QWidget(self)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(18, 14, 18, 14)
        outer.setSpacing(12)
        self.setCentralWidget(central)

        toolbar = QHBoxLayout()
        title = QLabel("T-ReS")
        title.setObjectName("title")
        toolbar.addWidget(title)
        toolbar.addWidget(QLabel("Simulador:"))
        self.adapter_selector = QComboBox()
        for registration in self.adapter_registrations:
            self.adapter_selector.addItem(
                registration.display_name, registration.simulator_id
            )
        self.adapter_selector.setCurrentIndex(
            self.adapter_selector.findData(self.adapter_id)
        )
        toolbar.addWidget(self.adapter_selector)
        toolbar.addStretch(1)
        self.connection_label = QLabel("Esperando al simulador")
        self.connection_label.setObjectName("connection")
        toolbar.addWidget(self.connection_label)
        self.snapshot_button = QPushButton("Elegir telemetría")
        self.snapshot_button.clicked.connect(self._choose_snapshot)
        toolbar.addWidget(self.snapshot_button)
        self.maps_button = QPushButton("Carpeta de mapas")
        self.maps_button.clicked.connect(self._choose_tracks_root)
        toolbar.addWidget(self.maps_button)
        outer.addLayout(toolbar)

        stats = QHBoxLayout()
        self.track_label = QLabel("Circuito: —")
        self.laps_label = QLabel("Vueltas restantes: —")
        self.speed_label = QLabel("Velocidad: —")
        self.gear_label = QLabel("Marcha: —")
        self.rpm_label = QLabel("RPM: —")
        for label in (self.track_label, self.laps_label, self.speed_label,
                      self.gear_label, self.rpm_label):
            label.setObjectName("stat")
            stats.addWidget(label)
        outer.addLayout(stats)

        content = QGridLayout()
        content.setHorizontalSpacing(12)
        content.setVerticalSpacing(12)
        self.map_widget = RaceMapWidget()
        self.map_widget.setObjectName("panel")
        self.map_widget.set_track_root(self.tracks_root)
        self.leaderboard = LeaderboardWidget()
        self.leaderboard.setObjectName("panel")
        self.chart = TelemetryTraceWidget()
        self.chart.setObjectName("panel")
        content.addWidget(self._section("Mapa del circuito", self.map_widget), 0, 0)
        content.addWidget(self._section("Clasificación", self.leaderboard), 0, 1)
        content.addWidget(self._section("Telemetría de la vuelta", self.chart), 1, 0, 1, 2)
        content.setColumnStretch(0, 3)
        content.setColumnStretch(1, 2)
        content.setRowStretch(0, 3)
        content.setRowStretch(1, 2)
        outer.addLayout(content, 1)

        self.footer = QLabel(
            "Sin datos ficticios: las señales aparecen cuando el puente del juego publica telemetría válida."
        )
        self.footer.setObjectName("footer")
        outer.addWidget(self.footer)

        self.setStyleSheet("""
            QMainWindow, QWidget { background: #11151B; color: #E7ECF2; }
            QWidget#panel { background: #171D25; border: 1px solid #2A3440; border-radius: 8px; }
            QLabel#title { font-size: 24px; font-weight: 700; color: #F7FAFC; }
            QLabel#connection { color: #FACC15; font-weight: 600; }
            QLabel#stat { background: #171D25; border-radius: 6px; padding: 9px 12px; }
            QLabel#section { font-size: 15px; font-weight: 650; color: #C7D2DE; padding: 2px 3px; }
            QLabel#footer { color: #9AA7B5; padding-top: 2px; }
            QPushButton { background: #263241; border: 1px solid #394858; border-radius: 5px;
                          padding: 7px 10px; }
            QPushButton:hover { background: #344356; }
            QTableWidget { background: #171D25; gridline-color: #303B48; alternate-background-color: #1D2530; }
            QHeaderView::section { background: #202A36; color: #D8E0E8; border: 0; padding: 5px; }
        """)

        self.worker = SnapshotWorker(self.adapter, self)
        self.worker.snapshot_ready.connect(self._on_snapshot)
        self.worker.source_error.connect(self._on_source_error)
        self.worker.start()
        self.adapter_selector.currentIndexChanged.connect(self._on_adapter_selected)

    @staticmethod
    def _section(title: str, child: QWidget) -> QWidget:
        section = QWidget()
        section.setObjectName("panel")
        layout = QVBoxLayout(section)
        layout.setContentsMargins(9, 8, 9, 9)
        heading = QLabel(title)
        heading.setObjectName("section")
        layout.addWidget(heading)
        layout.addWidget(child, 1)
        return section

    def _load_path_setting(
        self,
        name: str,
        default_provider: Callable[[], Path | None],
        legacy_key: str | None,
    ) -> Path | None:
        key = f"adapters/{self.adapter_id}/{name}"
        value = self.settings.value(key, "", str)
        if not value and legacy_key is not None:
            value = self.settings.value(legacy_key, "", str)
            if value:
                self.settings.setValue(key, value)
        return Path(value) if value else default_provider()

    def _legacy_path_key(self, name: str) -> str | None:
        return f"assetto_corsa/{name}" if self.adapter_id == SIMULATOR_ID else None

    def _create_adapter(self) -> TelemetryAdapter:
        options = {
            "snapshot_path": str(self.snapshot_path) if self.snapshot_path else "",
        }
        return create_adapter(self.adapter_id, options)

    def _on_adapter_selected(self, _index: int) -> None:
        simulator_id = self.adapter_selector.currentData()
        if not isinstance(simulator_id, str) or simulator_id == self.adapter_id:
            return
        self.adapter_id = simulator_id
        self.settings.setValue("telemetry/simulator_id", simulator_id)
        self.adapter_registration = adapter_registration(simulator_id)
        self.snapshot_path = self._load_path_setting(
            "snapshot_path",
            self.adapter_registration.default_snapshot_path,
            self._legacy_path_key("snapshot_path"),
        )
        self.tracks_root = self._load_path_setting(
            "tracks_root",
            self.adapter_registration.default_tracks_root,
            self._legacy_path_key("tracks_root"),
        )
        self.map_widget.set_track_root(self.tracks_root)
        self.adapter = self._create_adapter()
        self.worker.set_adapter(self.adapter)

    def _choose_snapshot(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar snapshot T-ReS", str(self.snapshot_path or Path.home()),
            "Telemetría T-ReS (telemetry.json);;JSON (*.json)",
        )
        if not path:
            return
        self.snapshot_path = Path(path)
        self.settings.setValue(f"adapters/{self.adapter_id}/snapshot_path", path)
        self.adapter = self._create_adapter()
        self.worker.set_adapter(self.adapter)

    def _choose_tracks_root(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, "Seleccionar content/tracks de Assetto Corsa",
            str(self.tracks_root or Path.home()),
        )
        if not path:
            return
        self.tracks_root = Path(path)
        self.settings.setValue(f"adapters/{self.adapter_id}/tracks_root", path)
        self.map_widget.set_track_root(self.tracks_root)

    def _on_snapshot(self, snapshot: TelemetrySnapshot) -> None:
        self._latest = snapshot
        laps = snapshot.player.completed_laps
        if self._last_lap_count is not None and laps is not None and laps != self._last_lap_count:
            self.map_widget.clear_trace()
            self.chart.clear()
        if laps is not None:
            self._last_lap_count = laps
        track = snapshot.track or "desconocido"
        if snapshot.layout:
            track += f" · {snapshot.layout}"
        self.track_label.setText(f"Circuito: {track}")
        remaining = snapshot.laps_remaining
        self.laps_label.setText(
            f"Vueltas restantes: {remaining}" if remaining is not None
            else "Vueltas restantes: no disponible"
        )
        speed = snapshot.player.speed_kmh
        self.speed_label.setText(
            f"Velocidad: {speed:.0f} km/h" if speed is not None else "Velocidad: no disponible"
        )
        gear = snapshot.player.gear
        gear_text = "R" if gear == -1 else ("N" if gear == 0 else str(gear))
        self.gear_label.setText(
            f"Marcha: {gear_text}" if gear is not None else "Marcha: no disponible"
        )
        rpm = snapshot.player.rpm
        self.rpm_label.setText(f"RPM: {rpm}" if rpm is not None else "RPM: no disponible")
        full_bridge = bool(snapshot.cars)
        self.connection_label.setText(
            f"Conectado · {self.adapter_registration.display_name} + telemetría completa"
            if full_bridge
            else f"Conectado · {self.adapter_registration.display_name}, datos parciales"
        )
        self.connection_label.setStyleSheet("color: #22C55E; font-weight: 600;")
        self.map_widget.set_snapshot(snapshot)
        player_car = next((car for car in snapshot.cars if car.is_player), None)
        if player_car is not None:
            self.map_widget.add_player_position(
                player_car, snapshot.player.current_sector_index
            )
        self.leaderboard.set_snapshot(snapshot)
        self.chart.set_snapshot(snapshot)
        if full_bridge:
            self.footer.setText(
                f"Sesión: {snapshot.session_type or 'no disponible'} · "
                f"Mejor vuelta: {self._fastest_lap_status(snapshot)}"
            )
        else:
            self.footer.setText(
                "La fuente actual no proporciona clasificación ni posiciones de rivales."
            )

    @staticmethod
    def _fastest_lap_status(snapshot: TelemetrySnapshot) -> str:
        car_id = snapshot.fastest_lap_car_id
        if car_id is None:
            return "tiempos por piloto no disponibles"
        car = next((entry for entry in snapshot.cars if entry.car_id == car_id), None)
        if car is None:
            return "no disponible"
        from t_res.dashboard.widgets import _format_lap_time
        name = car.driver_name or ("Jugador" if car.is_player else "Piloto")
        return f"{name} · {_format_lap_time(car.best_lap_time_ms)}"

    def _on_source_error(self, message: str) -> None:
        self._latest = None
        self.connection_label.setText("Esperando telemetría válida")
        self.connection_label.setStyleSheet("color: #FACC15; font-weight: 600;")
        self.track_label.setText("Circuito: —")
        self.laps_label.setText("Vueltas restantes: —")
        self.speed_label.setText("Velocidad: —")
        self.gear_label.setText("Marcha: —")
        self.rpm_label.setText("RPM: —")
        self.map_widget.set_snapshot(None)
        self.leaderboard.set_snapshot(None)
        self.chart.set_snapshot(None)
        self.footer.setText(message)

    def closeEvent(self, event) -> None:
        self.worker.stop()
        super().closeEvent(event)
