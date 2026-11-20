# Assetto Corsa original (2014) bridge

The bridge runs inside the game's Python app runtime and writes a real,
versioned snapshot beside itself. It reads the player's Shared Memory and uses
the game's API for connected-car positions and leaderboard ranks.

1. Copy `TReS.py` and `t_res_ac_shared_memory.py` into a new
   `apps/python/TReS/` directory in the Assetto Corsa installation. The
   directory name must match the `TReS.py` module name for AC's app loader.
2. Enable `[TRES] ACTIVE=1` in `cfg/python.ini` using the game's normal Python-app
   configuration, restart the game, and open **T-ReS Telemetry** from the
   in-game Python apps bar.
3. In the desktop dashboard, choose the generated
   `apps/python/TReS/telemetry.json` file and the circuit `content/tracks`
   folder.

The desktop app does not edit the game installation. Review the destination
and copy the bridge manually. The bridge only publishes while Shared Memory
reports a live, stable player sample. A stopped or unsupported source is
reported as unavailable by the desktop reader.

Assetto Corsa original's player Shared Memory provides player lap/sector times,
but the bridge does not have a verified best-sector feed for the whole field
or a verified best-lap time for every rival. In this version it therefore
does not claim purple session-best sectors and does not declare a fastest
driver. It colors completed player sectors green when they set a new observed
personal best and yellow when slower than that personal best. Missing rank,
position, timing, or track geometry remains unavailable.

The bridge also reads `ui_car.json` and the selected skin's `ui_skin.json` from
the installed car content for optional brand, class, and team-name metadata.
It publishes a team color only when the skin file explicitly contains a valid
`team_color` value; it does not guess colors from the car model or team name.
Per-car speed and normalized track position are included for the dashboard's
nearby-lapping indicator. To use these fields, manually copy the updated bridge
files into the game's `apps/python/TReS/` directory and restart the game.
