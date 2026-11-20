# Contrato de adaptadores T-ReS

T-ReS separa la ventana, los modelos de dominio y las fuentes de telemetría.
Cada adaptador implementa `TelemetryAdapter` (`simulator_id`, `display_name`
y `read()`) y devuelve un `TelemetrySnapshot` validado. El registro contiene
solo integraciones que realmente están implementadas; un nombre en la futura
matriz no crea una fuente simulada ni la hace aparecer en el selector.

## Snapshot normalizado

- `simulator` identifica el juego. El parser común acepta identificadores
  neutrales; cada adaptador valida que el snapshot corresponda a su propio
  identificador.
- Velocidad, acelerador, freno, marcha, RPM, vueltas y tiempos usan unidades
  explícitas del modelo. Los campos ausentes permanecen `None`.
- Cada coche puede incluir posición, piloto, vuelta y coordenadas del circuito.
  Solo se dibujan posiciones y clasificación entregadas por el juego.
- Las vueltas restantes requieren un total de vueltas comunicado por la
  sesión. La vuelta rápida requiere tiempos válidos para toda la parrilla.
- Los colores de sectores se asignan solo con tiempos reales y referencias
  personales/de sesión válidas. No se infieren sectores o coordenadas a partir
  de señales que no proporcionen esa información.
- Las muestras llevan versión y marca de tiempo; snapshots malformados,
  incompatibles o caducados se rechazan.

Las fixtures sintéticas se limitan a pruebas unitarias/protocolo y nunca se
presentan como telemetría de una sesión real.

## Transporte y configuración

El contrato no presupone UDP, memoria compartida ni archivos. Cada adaptador
elige el transporte documentado por el juego y normaliza sus datos al modelo
común. La configuración específica se guarda por identificador de simulador
mediante `QSettings`, que usa almacenamiento nativo del sistema operativo.
Rutas desconocidas se pueden seleccionar desde el dashboard.

El dashboard y el parser común no deben depender de rutas de Steam ni de APIs
particulares de un juego. La detección automática de instalaciones y cualquier
puente local pertenecen al adaptador correspondiente.

## Añadir un adaptador

1. Verificar y documentar el protocolo/API oficial, su versión y sus opciones
   de habilitación en el juego.
2. Implementar una clase que cumpla `TelemetryAdapter` y registrarla con un
   identificador/display name estables.
3. Decodificar solo campos realmente presentes; documentar datos no
   disponibles y los requisitos de red, permisos y plataforma.
4. Añadir fixtures de protocolo y pruebas para versiones, paquetes truncados,
   datos ausentes, unidades, timestamps y orden de coches.
5. Probar primero el transporte con loopback. La compatibilidad en vivo solo se
   declara después de validar contra una ejecución real del juego.
6. Si el juego usa otro formato de mapa o coordenadas, proveer una conversión
   con datos oficiales del circuito o mostrar que el mapa no está disponible;
   no reutilizar coordenadas de otro simulador.
