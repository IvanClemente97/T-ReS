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
limitada por vueltas. El leaderboard selecciona una sola fuente de posiciones
para toda la parrilla: prefiere las posiciones en tiempo real cuando están
completas y son únicas; si no, usa la clasificación oficial y oculta rangos
duplicados. La vuelta rápida global solo se anuncia cuando hay un tiempo válido
para todos los coches conectados.

## Interfaz de carrera y vuelta

La vista se divide en dos pestañas: **Carrera** reúne mapa y clasificación;
**Vuelta** ocupa el espacio con las trazas de pedales, velocidad y marcha.
Se quitaron las tarjetas numéricas independientes de velocidad, marcha y RPM;
las señales gráficas se mantienen. El tema usa carbón, degradados y acentos
naranjas sin logotipos de terceros.

En el mapa, los marcadores muestran la posición del piloto. Cuando todos los
coches tienen la misma clase conocida (o la misma marca si falta esa clase),
se usa blanco; en carreras multiclase se asigna un color estable por clase.
La tabla usa el nombre legible de `ui_car.json` cuando está disponible. Su
leaderboard presenta una tabla independiente por categoría, con posiciones
recalculadas dentro de cada clase; no mezcla GT, LMP ni coches sin clase
conocida. La columna GAP expresa metros/kilómetros derivados del progreso
normalizado y la longitud oficial del layout en `ui_track.json`; al líder de
cada clase se le muestra `—`. También distingue coches que siguen en carrera y
coches que ya finalizaron cuando el juego proporciona ese estado. Las vueltas
restantes y el tiempo de la vuelta rápida se apilan en una columna fija en la
esquina superior izquierda del panel del mapa; el mapa se ajusta al espacio
restante y no queda cubierto por esos indicadores. El nombre del piloto con la
vuelta rápida válida se resalta en morado, sin repetirlo en el indicador de
tiempo.
En simuladores F1, el color
de escudería se muestra solo si el adaptador publica un `team_color` válido.
La integración actual de Assetto Corsa lee marca/clase y equipo de los archivos
locales del coche/skin, pero esos archivos no suelen definir un color de equipo.
Los aros se calculan con datos reales: azul para coches con menos vueltas que
el jugador; verde lima solo para un coche con al menos una vuelta de ventaja,
cerca por posición normalizada y con mayor velocidad. Este último es un
indicador aproximado, no una predicción de tiempo/distancia exactos.

F1 25/26, ACC y LMU aún no tienen adaptador en esta versión. Por tanto, sus
colores de escudería y categorías solo aparecerán cuando exista una integración
que proporcione esos metadatos; no se deducen ni se sustituyen por valores
inventados.

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
