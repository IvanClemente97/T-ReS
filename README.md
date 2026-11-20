# T-ReS — Telemetry RaceStudio

Aplicación desktop independiente para visualizar telemetría real de
simuladores. El contrato de datos y el registro de fuentes son independientes
del simulador; los adaptadores se incorporan de forma individual. Consulta la
[matriz de compatibilidad](docs/support-matrix.md): por ahora, el único
adaptador implementado es **Assetto Corsa original (2014)**.

El dashboard está diseñado para Windows, Linux y macOS con PySide6. Cada
paquete ejecutable debe construirse en su sistema operativo destino y el
soporte de un simulador depende además de que su juego y su API de telemetría
estén disponibles en ese sistema. Solo se ha verificado en vivo en Linux con
Assetto Corsa ejecutándose bajo Proton.

## Ejecutar

Requiere Python 3.10+ y PySide6. Desde esta carpeta:

```bash
./run.sh
```

En Windows, usa `run.bat`. Si prefieres instalar el comando de usuario:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .
t-res
```

En Windows, activa el entorno con `.venv\Scripts\activate` y ejecuta `t-res`.
También puede iniciarse con `python -m t_res` tras instalar el proyecto.

Para crear un ejecutable autónomo en el sistema donde se construye:

```bash
python -m pip install -e '.[build]'
pyinstaller --noconfirm --windowed --name T-ReS --paths src src/t_res/__main__.py
```

Los ejecutables de Windows y macOS deben construirse y probarse en sus
respectivos sistemas; un binario creado en Linux no se considera portable.
Las rutas/configuración de T-ReS usan mecanismos nativos de Qt y permiten
seleccionar manualmente la telemetría y los datos de pista.

## Conectar Assetto Corsa original

Sigue [las instrucciones del puente](integrations/assetto_corsa/README.md).
En Linux/Proton, el adaptador intenta leer directamente la Shared Memory
`/dev/shm/acpmf_*` para mostrar telemetría real del jugador, sin instalar el
puente. Para rivales, clasificación, posiciones y mapa se necesita la
aplicación Python dentro del juego. En Windows, usa el puente para publicar
datos al dashboard. Las instalaciones habituales de Steam se detectan en los
sistemas compatibles; también puedes elegir las rutas desde la ventana si el
juego está instalado en otra ubicación. Consulta el [contrato de adaptadores](docs/adapter-architecture.md)
antes de añadir una integración nueva.

El panel no simula sesiones. Si el juego no está publicando muestras nuevas,
faltan campos o el mapa no está instalado, se muestra el estado correspondiente.
Las vueltas restantes solo se presentan cuando el juego comunica una sesión
limitada por vueltas. La clasificación solo marca vuelta rápida si hubiera un
tiempo válido para cada coche; el puente actual no tiene esa cobertura.

## Datos y limitaciones

- Los pedales son las señales `gas` y `brake` del juego (0–1), no lecturas de
  un volante o pedalera USB.
- El mapa requiere `map.png`, `data/map.ini` y coordenadas mundiales válidas.
- El trazado colorea sectores completados con los colores permitidos:
  morado (mejor de sesión), verde (mejor personal) y amarillo (más lento).
  Esta versión calcula verde/amarillo con tiempos reales del jugador; no
  dispone de tiempos de sector de toda la sesión para afirmar morado.
- La señal del juego se integra mediante un protocolo JSON local versionado.
  Los campos ausentes permanecen ausentes; no se deducen posiciones desde la
  spline ni se completan tiempos.
- No requiere hardware Fanatec ni importa código de otros proyectos.

Las pruebas usan snapshots sintéticos solo como fixtures aisladas. No se
utilizan para presentar telemetría en la aplicación.

## Pruebas

Sin instalar ni abrir un simulador:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
python -m compileall -q src integrations/assetto_corsa
```
