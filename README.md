# Plan: T-ReS, dashboard independiente de telemetría

## Problema y enfoque

Crear `Projects/T-ReS` como aplicación independiente, multiplataforma y ejecutable, sin modificar ni importar código de los proyectos hermanos. La primera integración real será **Assetto Corsa original (2014)**. La aplicación no generará muestras ni rellenará datos que el juego no entregue: mostrará un estado de espera o «no disponible» cuando falte telemetría.

La arquitectura separará el dashboard, el contrato normalizado de telemetría, los adaptadores por simulador/plataforma y el puente que corre dentro del juego. La interfaz desktop será Python/PySide6; la comunicación del puente con el dashboard usará un protocolo local versionado con escritura atómica y detección de datos obsoletos. La ejecución y empaquetado serán por plataforma; el entorno actual permite validar Linux, mientras que la validación del binario Windows requerirá una máquina o runner Windows.

## Entrega inicial propuesta

- Aplicación externa con una sola ventana: estado/conexión, vueltas restantes cuando la sesión sea por vueltas, mapa con jugador y rivales, clasificación, y gráficos de velocidad, acelerador, freno y marcha.
- Trazas de acelerador y freno con eje porcentual 0–100 %, acelerador verde y freno rojo. Mostrar velocidad y marcha como canales con sus unidades/escala adecuadas; eje horizontal por distancia de vuelta si está disponible y, en caso contrario, por tiempo de vuelta.
- El mapa usará la imagen y geometría instaladas del circuito y coordenadas reales del juego. La línea de la vuelta actual se coloreará por sector: morado para mejor sector de sesión cuando el juego proporcione una referencia fiable, verde para mejor sector personal y amarillo para un sector más lento que el mejor personal. Se limpiará al iniciar la vuelta siguiente. Sin posición/sector válidos, no se pintará una línea inventada.
- La clasificación mostrará posición, piloto y vuelta actual a partir de datos del juego. Se destacará la vuelta rápida únicamente si el adaptador obtiene y valida tiempos por piloto; no se inferirá desde posiciones ni desde el tiempo del jugador.
- Sin telemetría real se mostrará una pantalla vacía de «esperando al simulador», no un modo demo que pueda confundirse con una sesión real.

## Arquitectura y componentes previstos

Dentro de `T-ReS/`:

- `pyproject.toml`, `README.md`: dependencias, instrucciones de instalación/ejecución y limitaciones de compatibilidad.
- `src/t_res/domain/`: modelos comunes, unidades, procedencia, timestamps y estados de disponibilidad.
- `src/t_res/adapters/assetto_corsa/`: lector/validador del protocolo local, normalizador y puente Python instalable para la app integrada de AC.
- `src/t_res/dashboard/`: ventana PySide6, mapa, tabla de carrera e instrumentos/gráficos; la GUI consumirá snapshots y no abrirá conexiones del juego.
- `tests/`: pruebas aisladas de protocolo, normalización, datos ausentes/obsoletos, segmentación de vueltas y presentación; fixtures sintéticos etiquetados solo para pruebas.
- Configuración y empaquetado ejecutable por sistema operativo; no requiere volante ni hardware Fanatec.

El puente de Assetto Corsa consultará la API Python del juego para coches conectados, posición oficial/real-time, vueltas, nombres y coordenadas mundiales X/Z, y accederá a Shared Memory para telemetría del jugador y tiempos/sectores. Publicará snapshots versionados y reemplazados atómicamente. El dashboard verificará versión, rangos, antigüedad y circuito/layout antes de mostrarlos. Los mapas se resolverán en la instalación del propio AC; si no existen o el usuario no ha instalado/activado el puente, esa parte se marcará como no disponible.

La app desktop podrá funcionar tanto en Windows como Linux, pero los mecanismos de ejecución del juego son específicos de cada plataforma. En Linux/Proton, la evidencia del proyecto existente indica que el puente dentro del juego puede leer la Shared Memory nativa de AC y escribir el snapshot a archivo; no se debe asumir que los nombres de Shared Memory de Windows aparecen como archivos Linux. En Windows se validará la carga de la app integrada y la ubicación/permisos del snapshot. La creación del paquete final para cada sistema se validará en ese sistema.

## Cobertura real y límites

| Simulador/requisito | Primera entrega |
|---|---|
| Assetto Corsa original (2014) | Adaptador objetivo: jugador (velocidad, pedales, marcha, vueltas/tiempos/sectores) y, con el puente activo, rivales, clasificación y coordenadas. |
| Vueltas restantes | Disponible en carreras limitadas por vueltas cuando total y completadas sean válidos; sesiones por tiempo o valor total desconocido mostrarán «no disponible», no un cálculo supuesto. |
| Mapa y posiciones | Requiere puente activo, coordenadas X/Z válidas y `map.png`/`map.ini` del circuito/layout instalado. La spline por sí sola no se tratará como geometría del circuito. |
| Sectores verde/morado/amarillo | Depende de muestras de posición y tiempos de sector. Morado requiere una referencia de mejor sector de sesión fiable; si la API no la entrega, no se proclamará un récord de sesión. Cada vuelta nueva limpia el recorrido previo. |
| Vuelta rápida del leaderboard | Condicional a verificar que la API integrada entregue un mejor/último tiempo por cada piloto. El puente visible en el entorno hoy no publica esos tiempos, por lo que habrá que comprobar y probar esa capacidad; si no existe, la fila no se marcará como vuelta rápida. |
| Assetto Corsa Competizione, F1 25/26 y Le Mans Ultimate | Sin adaptadores detectados en el entorno. No se anunciarán como compatibles en la primera entrega; quedan como integraciones futuras que requieren investigar y validar la API/protocolo de cada juego. |

Las referencias de diseño revisadas son documentación y código de telemetría de los proyectos hermanos; `T-ReS` tendrá su propio código, configuración, dependencias, pruebas y documentación. No se escribirán archivos fuera de `Projects/T-ReS` durante la implementación.

## Tareas

1. Crear la estructura independiente, contrato de datos, instrucciones de instalación y lanzamiento.
2. Implementar y probar el puente/adaptador de Assetto Corsa original; verificar de forma aislada y con juego disponible qué campos multi-piloto (en especial tiempos por piloto) expone realmente.
3. Implementar el dashboard externo, estados explícitos de disponibilidad, mapa, clasificación y gráficas conectados solo al contrato normalizado.
4. Probar sin juego que no se fabrican datos, y validar build/ejecución Linux; documentar y preparar validación/paquete Windows separada.

## Consideraciones

- El plan asume que el usuario acepta una primera versión con AC original y que ACC, F1 y LMU quedan fuera hasta contar con adaptadores probados. La elección multiplataforma se aplica a la aplicación externa; las integraciones con juegos dependen de sus APIs y entornos.
- La app integrada de AC debe instalarse y activarse dentro del juego. El mapa depende de los recursos locales del circuito.
- La validación unitaria no equivale a una carrera real. El comportamiento de la API por piloto, la compatibilidad con versiones de juego y los instaladores se deben probar con el simulador disponible.
