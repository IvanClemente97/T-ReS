# LedsFanatecLinux

Aplicación independiente para Linux que controla las 9 zonas RGB de RPM, las 6 zonas de banderas y la pantalla numérica de un volante Fanatec compatible con `hid_fanatec`. Incluye un servicio de usuario persistente y una GUI separada para perfiles.

## Estado de compatibilidad real

| Sistema | Estado | Fuente de datos |
|---|---|---|
| Assetto Corsa original (2014) | Adaptador funcional en Linux, con el puente del juego habilitado | **Fanatec Rivals** lee Shared Memory dentro del proceso Python de AC y publica un snapshot JSON real con RPM, corte de RPM, velocidad, marcha, pedales, pit y bandera. Este servicio consume ese snapshot; no captura directamente el puerto UDP. |
| Assetto Corsa original con T-ReS | Adaptador secundario parcial | `TReS/telemetry.json` incluye RPM, velocidad, marcha y pedales; en la versión inspeccionada no publica corte de RPM ni banderas de carrera. |
| Assetto Corsa Competizione | No implementado ni validado | Requiere un adaptador ACC y configuración de su API UDP de broadcasting. |
| F1 25/26 | No implementado ni validado | Requiere adaptar y validar los paquetes UDP de la versión concreta del juego. |
| Le Mans Ultimate | No implementado ni validado | Requiere un adaptador LMU y comprobar la interfaz de telemetría instalada. |
| macOS | Sin control de hardware | La interfaz actual depende de sysfs y de los módulos del kernel Linux `hid_fanatec`/`led_class_multicolor`; macOS no proporciona esa interfaz. |

No se generan datos ficticios. Si el snapshot deja de actualizarse durante más de 1,5 segundos, el servicio apaga las zonas y borra la pantalla. Los estados de bandera no disponibles se dejan apagados.

## Requisitos

- Linux con Python 3.11 o posterior, `systemd --user` y PySide6 para abrir la GUI.
- Un volante compatible expuesto por el driver `hid_fanatec` bajo `/sys/class/ftec_wheel`; el driver `led_class_multicolor` proporciona la interfaz RGB usada por el kernel.
- El usuario debe poder escribir las zonas. En el entorno inspeccionado las zonas son `root:games` con permiso de grupo y el usuario ya pertenece a `games`; no se necesita ejecutar la aplicación con `sudo`.
- Para Assetto Corsa, el puente **Fanatec Rivals** debe estar habilitado como app Python dentro del juego para disponer de los datos completos. T-ReS sirve como alternativa parcial. El servicio no requiere que esté abierta la GUI de escritorio de T-ReS.

El servicio busca los snapshots en las rutas habituales de Steam. Se pueden indicar otras rutas mediante `FANATEC_RIVALS_TELEMETRY_PATH` y `TRES_TELEMETRY_PATH` en el entorno de systemd.

## Instalación y uso

Desde esta carpeta:

```bash
./scripts/install-service.sh
./scripts/run-gui.sh
```

La instalación comprueba Python 3.11 o posterior, instala la unidad `leds-fanatec-linux.service` de usuario y la habilita. También solicita `loginctl enable-linger` para que systemd mantenga el servicio activo aunque no haya una sesión gráfica abierta; si el sistema no autoriza ese ajuste, avisa y el servicio arrancará al iniciar sesión. La GUI necesita PySide6 (`pip install '.[gui]'` o el paquete equivalente de la distribución); el servicio usa solo la biblioteca estándar. No modifica los proyectos hermanos ni instala reglas de kernel/udev. El servicio se ejecuta sin `sudo`.

Comandos útiles:

```bash
systemctl --user status leds-fanatec-linux.service
journalctl --user -u leds-fanatec-linux.service -f
PYTHONPATH=src python3 -m leds_fanatec_linux.diagnose
./scripts/uninstall-service.sh
```

El diagnóstico es de solo lectura: informa del hardware, permisos aparentes y última muestra de telemetría; no cambia colores.

## Perfiles

La GUI con tema carbón, degradados y acentos naranjas comparte el lenguaje visual de T-ReS, sin logotipos de terceros. Permite crear, activar, borrar, importar y exportar perfiles JSON. La pestaña de banderas muestra cada señal con sus tres LED izquierdos y tres derechos en cápsulas, siguiendo la disposición visual de MOZA Pit House. La ventana omite los valores detallados de telemetría y solo indica si la edición está permitida. Cada perfil contiene nueve colores RPM, nueve colores independientes RPM MAX, secuencia de encendido y periodo de blink RPM MAX (100–4000 ms; 500 ms = 2 Hz). Al cambiar un color se guarda inmediatamente; si el perfil está activo y el coche detenido, el servicio lo aplica al volante. Los perfiles viven en `~/.config/LedsFanatecLinux/profiles/`. Los esquemas v1/v2 se migran a v3 al leerlos: el antiguo color único de cambio se copia a las nueve zonas RPM MAX, se ignoran los ajustes de banderas (ahora fijos) y el blink comienza en 500 ms.

Los colores de banderas conservan el código existente y ya no se editan por perfil. La amarilla normal ilumina las seis zonas; la doble amarilla alterna ambos grupos de tres LED; la amarilla local desplaza un LED amarillo por las seis posiciones. Como el puente actual solo publica una bandera amarilla genérica, las animaciones de doble/local están disponibles para prueba y para adaptadores futuros, pero no se infieren de la telemetría de AC. Cada bandera tiene un botón de prueba; también hay pruebas independientes para RPM y RPM MAX. Las pruebas las ejecuta el servicio (único proceso que escribe en sysfs), duran tres segundos y **se pueden lanzar con el simulador cerrado**, siempre que el servicio detecte el volante. Si la telemetría está conectada, las pruebas se bloquean mientras el vehículo se mueve.

El límite de RPM nunca se configura manualmente: procede exclusivamente del campo `max_rpm` de la telemetría. Si falta o no es válido, las nueve RPM quedan apagadas y no se sustituye por un valor supuesto. Cada RPM normal se enciende al alcanzar su umbral lineal (1/9 a 9/9 del `max_rpm`); la secuencia elegida solo define el orden físico. Al alcanzar el límite se muestran intermitentemente los nueve colores RPM MAX con el periodo configurado. La edición de perfiles y activación se bloquean si la velocidad supera 1 km/h o si la telemetría activa no incluye velocidad; a 1 km/h o menos se permite editar, incluso con el juego pausado. Sin telemetría se considera que el coche no está en marcha. La pantalla muestra `int(speed_kmh)`, truncando los km/h, y solo escribe un número de 0 a 999.

## Arquitectura

- `telemetry.py`: lee snapshots atómicos y recientes de Fanatec Rivals o T-ReS; valida rangos y mantiene desconocidos los campos que el juego no publica.
- `patterns.py`: calcula los 9 LED de RPM y los 6 LED de banderas sin depender del sistema operativo.
- `hardware.py`: detecta VID/PID `0EB7:0004`, comprueba las 15 zonas y escribe RGB/display en sysfs.
- `service.py`: proceso persistente desacoplado de la GUI; conserva solo el estado más reciente, consume comandos de prueba locales y deja el volante apagado al perder telemetría o desconectarse.
- `gui.py` y `profiles.py`: interfaz PySide6 y persistencia/migración de perfiles, independientes del ciclo del servicio.

El servicio existente `fanatec-leds.service` se comprueba durante la instalación para evitar que dos procesos escriban simultáneamente al volante; si estuviera activo, la instalación se detiene y pide cerrarlo primero.

## Verificación realizada

- En el equipo objetivo se detectó una base Fanatec `0EB7:0004` con las 15 zonas RGB y pantalla numérica; el usuario actual tiene permiso de escritura por el grupo `games`.
- Se comprobó que la app Fanatec Rivals publicaba en vivo un snapshot de AC con `rpm=3`, `max_rpm=15000`, `speed_kmh≈0`, marcha, pedales, estado de pit y bandera sin activar. El adaptador de esta aplicación lee ese archivo y valida su antigüedad.
- Se instaló, habilitó y reinició el nuevo servicio systemd de usuario. Mientras AC publicaba muestras en movimiento, la GUI mostró velocidad/RPM/pedales en vivo; sysfs confirmó el patrón RGB en las zonas del volante. El servicio permanece activo y `linger` está habilitado en este equipo.
- T-ReS publicó un snapshot fresco de AC con pedales, RPM, velocidad, marcha y posición, pero sin `max_rpm` ni bandera de carrera; se documenta como fuente parcial.
- ACC, F1 25/26 y LMU no se declaran compatibles hasta disponer de adaptadores para sus protocolos y validación con cada juego.
- La pantalla `display` del driver es de solo escritura; el servicio la actualizó sin errores y una prueba automatizada verifica el truncado de `88.9` a `88`, pero el valor no se puede leer de vuelta desde sysfs.
- La GUI migrada y las nuevas pruebas RPM/MAX y de banderas se verifican en modo Qt sin pantalla; las escrituras de prueba siguen mediadas por el servicio y requieren el volante conectado. El bloqueo durante el movimiento se basa en velocidad telemétrica (>1 km/h), no en un indicador explícito de pausa/carrera, ya que el puente disponible no publica ese estado.

Pruebas locales:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```
