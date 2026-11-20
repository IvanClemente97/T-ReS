# T-ReS y LedsFanatecLinux

Monorepo independiente para telemetría de carreras y control de los LED de
volantes Fanatec. La versión publicada es **0.1.0**. Cada aplicación puede
instalarse y ejecutarse por separado:

```text
├── T-ReS/             Dashboard de telemetría
└── LedsFanatecLinux/  Servicio y GUI para el volante Fanatec
```

No se generan sesiones ni valores ficticios: cuando una fuente no proporciona
un dato, la aplicación lo deja como no disponible.

## Qué hace cada aplicación

**T-ReS** es un dashboard externo con dos vistas: **Carrera** muestra el mapa
y la clasificación; **Vuelta** presenta trazas de pedales, velocidad y marcha.
El mapa usa la posición y los metadatos de los coches que envía el simulador.
En esta versión solo está implementado el adaptador de Assetto Corsa original
(2014). ACC, F1 25/26 y Le Mans Ultimate aún no están integrados.

**LedsFanatecLinux** mantiene un servicio `systemd --user` que lee telemetría y
controla las zonas RGB y la pantalla del volante. Su GUI sirve para gestionar
perfiles, cambiar los colores de RPM/RPM MAX y probar LED y banderas. El
servicio es el único proceso que escribe en el hardware y puede seguir activo
sin la GUI abierta. La fuente completa de Assetto Corsa es el snapshot de
Fanatec Rivals; el snapshot de T-ReS es una alternativa parcial y no aporta el
límite de RPM ni las banderas.

## Requisitos y compatibilidad

| Aplicación | Requisitos principales | Compatibilidad verificada |
|---|---|---|
| T-ReS | Python 3.10+ y PySide6 | Assetto Corsa original en Linux/Proton |
| LedsFanatecLinux | Linux, Python 3.11+, `systemd --user`, PySide6 para la GUI y volante reconocido por `hid_fanatec` | Assetto Corsa original mediante Fanatec Rivals y driver Linux |

T-ReS está diseñado para Windows, Linux y macOS, pero la disponibilidad de
telemetría depende del juego, el adaptador y el sistema; fuera de la
configuración indicada no se declara validación en vivo. El control de hardware
de LedsFanatecLinux depende de los módulos Linux `hid_fanatec` y
`led_class_multicolor`, y de permisos de escritura del usuario en la interfaz
sysfs del volante. No requiere `sudo` cuando esos permisos ya están
configurados. En macOS no existe este backend de hardware. Consulta los
README de cada aplicación para sus matrices y limitaciones completas.

## Instalar y arrancar T-ReS

Linux y macOS:

```bash
cd T-ReS
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
./run.sh
```

En Windows, crea y activa el entorno con `py -m venv .venv` y
`.venv\Scripts\Activate.ps1`, instala con `python -m pip install -e .` y
ejecuta `run.bat`. También puedes arrancarlo con `python -m t_res` después de
instalarlo.

### Conectar Assetto Corsa original

Para telemetría del jugador en Linux/Proton, T-ReS puede leer la Shared Memory
del juego. Para recibir rivales, posiciones, clasificación y datos completos del
mapa, instala el puente Python del juego:

1. Copia `T-ReS/integrations/assetto_corsa/TReS.py` y
   `T-ReS/integrations/assetto_corsa/t_res_ac_shared_memory.py` a una carpeta
   `apps/python/TReS/` dentro de la instalación de Assetto Corsa.
2. Activa `[TRES] ACTIVE=1` en `cfg/python.ini`, reinicia el juego y abre
   **T-ReS Telemetry** desde la barra de apps Python.
3. En T-ReS, selecciona el archivo `telemetry.json` generado por el puente y
   la carpeta `content/tracks` de Assetto Corsa.

La aplicación de escritorio no modifica la instalación del juego. En
Windows, configura el puente según
[`T-ReS/integrations/assetto_corsa/README.md`](T-ReS/integrations/assetto_corsa/README.md).

## Instalar y arrancar LedsFanatecLinux

En Linux, con el driver y los permisos del volante ya configurados:

```bash
cd LedsFanatecLinux
python3 -m pip install -e '.[gui]'
./scripts/install-service.sh
./scripts/run-gui.sh
```

El instalador registra y habilita el servicio de usuario y trata de habilitar
`linger`, para que el servicio continúe al cerrar la sesión gráfica. La GUI
puede cerrarse sin detener el servicio. Para comprobarlo:

```bash
systemctl --user status leds-fanatec-linux.service
journalctl --user -u leds-fanatec-linux.service -f
```

En Assetto Corsa, habilita la app Python **Fanatec Rivals** para que publique
el snapshot completo que consume el servicio. Si solo tienes el puente T-ReS,
el servicio usa lo disponible y mantiene apagadas las RPM cuando falta
`max_rpm`; no sustituye datos ausentes por valores supuestos. Los perfiles se
guardan en `~/.config/LedsFanatecLinux/profiles/`. Para desinstalar el servicio
de usuario ejecuta `./scripts/uninstall-service.sh`.

## Pruebas

Desde la raíz del repositorio:

```bash
# T-ReS
(cd T-ReS && PYTHONPATH=src python -m unittest discover -s tests -v)
(cd T-ReS && python -m compileall -q src integrations/assetto_corsa)

# LedsFanatecLinux
(cd LedsFanatecLinux && PYTHONPATH=src python3 -m unittest discover -s tests -v)
(cd LedsFanatecLinux && python3 -m compileall -q src scripts)
```

La compatibilidad en vivo y los requisitos específicos se detallan en
[`T-ReS/README.md`](T-ReS/README.md) y
[`LedsFanatecLinux/README.md`](LedsFanatecLinux/README.md).
