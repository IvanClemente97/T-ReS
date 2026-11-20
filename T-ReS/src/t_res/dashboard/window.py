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
    QTabWidget,
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
        central.setObjectName("dashboard")
        outer = QVBoxLayout(central)
        outer.setContentsMargins(20, 16, 20, 16)
        outer.setSpacing(14)
        self.setCentralWidget(central)

        toolbar = QHBoxLayout()
        heading = QVBoxLayout()
        title = QLabel("T-ReS")
        title.setObjectName("title")
        subtitle = QLabel("TELEMETRÍA DE COMPETICIÓN")
        subtitle.setObjectName("subtitle")
        heading.addWidget(title)
        heading.addWidget(subtitle)
        toolbar.addLayout(heading)
        toolbar.addSpacing(20)
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
        self.snapshot_button = QPushButton("Elegir fuente")
        self.snapshot_button.clicked.connect(self._choose_snapshot)
        toolbar.addWidget(self.snapshot_button)
        self.maps_button = QPushButton("Circuitos")
        self.maps_button.clicked.connect(self._choose_tracks_root)
        toolbar.addWidget(self.maps_button)
        outer.addLayout(toolbar)

        stats = QHBoxLayout()
        self.track_label = QLabel("Circuito: —")
        self.track_label.setObjectName("meta")
        stats.addWidget(self.track_label)
        stats.addStretch(1)
        outer.addLayout(stats)

        self.pages = QTabWidget()
        race_page = QWidget()
        race_page.setObjectName("page")
        content = QGridLayout(race_page)
        content.setContentsMargins(0, 10, 0, 0)
        content.setHorizontalSpacing(14)
        content.setVerticalSpacing(12)
        self.map_widget = RaceMapWidget()
        self.map_widget.setObjectName("panel")
        self.map_widget.set_track_root(self.tracks_root)
        self.leaderboard = LeaderboardWidget()
        self.leaderboard.setObjectName("panel")
        self.chart = TelemetryTraceWidget()
        self.chart.setObjectName("panel")
        content.addWidget(self._section("MAPA EN VIVO", self.map_widget), 0, 0)
        content.addWidget(self._section("CLASIFICACIÓN", self.leaderboard), 0, 1)
        content.setColumnStretch(0, 3)
        content.setColumnStretch(1, 2)
        content.setRowStretch(0, 1)
        self.pages.addTab(race_page, "Carrera")

        lap_page = QWidget()
        lap_page.setObjectName("page")
        lap_layout = QVBoxLayout(lap_page)
        lap_layout.setContentsMargins(0, 10, 0, 0)
        lap_layout.setSpacing(10)
        lap_layout.addWidget(
            self._section("TRAZAS DE LA VUELTA ACTUAL", self.chart), 1
        )
        self.pages.addTab(lap_page, "Vuelta")
        outer.addWidget(self.pages, 1)

        self.footer = QLabel(
            "Solo se muestran datos reales publicados por el simulador."
        )
        self.footer.setObjectName("footer")
        outer.addWidget(self.footer)

        self.setStyleSheet("""
            QMainWindow, QWidget#dashboard { background: #0B0D11; color: #F1F3F5; }
            QWidget#page { background: transparent; }
            QWidget#panel {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #191E25, stop:1 #12151A);
                border: 1px solid #2B313A; border-radius: 10px;
            }
            QLabel#title { font-size: 29px; font-weight: 800; color: #F5F6F7; }
            QLabel#subtitle { color: #FF7A1A; font-size: 9px; font-weight: 700;
                               letter-spacing: 2px; }
            QLabel#connection { color: #FACC15; font-weight: 700; background: #262117;
                                border: 1px solid #51401A; border-radius: 7px;
                                padding: 7px 11px; }
            QLabel#meta { background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                stop:0 #1C2229, stop:1 #14181D);
                          border: 1px solid #2D333C; border-radius: 7px;
                          padding: 9px 13px; font-size: 13px; }
            QLabel#section { font-size: 12px; font-weight: 750; color: #D2D7DE;
                             letter-spacing: 1.2px; padding: 3px 4px; }
            QLabel#footer { color: #8F98A3; padding-top: 2px; }
            QPushButton { background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                              stop:0 #272D35, stop:1 #1A1F26);
                          border: 1px solid #3A424D; border-radius: 6px;
                          padding: 8px 11px; color: #E7E9EC; font-weight: 600; }
            QPushButton:hover { border-color: #FF6A00; color: #FFFFFF; }
            QComboBox { background: #171B21; border: 1px solid #353C46; border-radius: 6px;
                        padding: 7px 9px; min-width: 150px; }
            QTabWidget::pane { border: 1px solid #2B313A; border-radius: 9px;
                               background: #0F1216; top: -1px; }
            QTabBar::tab { background: #171B21; color: #9BA3AD; padding: 10px 24px;
                           margin-right: 5px; border: 1px solid #2B313A;
                           border-top-left-radius: 7px; border-top-right-radius: 7px;
                           font-weight: 700; }
            QTabBar::tab:selected { color: #FFFFFF; border-color: #FF6A00;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #71320F, stop:1 #25201D); }
            QTableWidget { background: #15191F; gridline-color: #2C333C;
                           alternate-background-color: #1B2027; border: 0; }
            QHeaderView::section { background: #20252C; color: #D8DDE4;
                                   border: 0; padding: 7px 5px; font-weight: 700; }
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
        full_bridge = bool(snapshot.cars)
        self.connection_label.setText(
            f"Conectado · {self.adapter_registration.display_name} + telemetría completa"
            if full_bridge
            else f"Conectado · {self.adapter_registration.display_name}, datos parciales"
        )
        self.connection_label.setStyleSheet(
            "color: #86EFAC; font-weight: 700; background: #17251C; "
            "border: 1px solid #265237; border-radius: 7px; padding: 7px 11px;"
        )
        self.map_widget.set_snapshot(snapshot)
        player_car = next((car for car in snapshot.cars if car.is_player), None)
        if player_car is not None:
            self.map_widget.add_player_position(
                player_car, snapshot.player.current_sector_index
            )
        self.leaderboard.set_snapshot(snapshot, self.map_widget.track_length_m)
        self.chart.set_snapshot(snapshot)
        if full_bridge:
            self.footer.setText(
                f"Sesión: {snapshot.session_type or 'no disponible'} · "
                "Vuelta rápida y vueltas restantes en el mapa"
            )
        else:
            self.footer.setText(
                "La fuente actual no proporciona clasificación ni posiciones de rivales."
            )

    def _on_source_error(self, message: str) -> None:
        self._latest = None
        self.connection_label.setText("Esperando telemetría válida")
        self.connection_label.setStyleSheet("")
        self.track_label.setText("Circuito: —")
        self.map_widget.set_snapshot(None)
        self.leaderboard.set_snapshot(None)
        self.chart.set_snapshot(None)
        self.footer.setText(message)

    def closeEvent(self, event) -> None:
        self.worker.stop()
        super().closeEvent(event)
