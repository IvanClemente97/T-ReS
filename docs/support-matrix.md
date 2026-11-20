# Matriz de compatibilidad

## Aplicación externa

| Sistema | Estado del dashboard |
| --- | --- |
| Linux | Ejecutado y probado en el entorno actual |
| Windows | Objetivo PySide6; no probado en este entorno |
| macOS | Objetivo PySide6; no probado en este entorno |

El binario debe construirse y probarse de forma nativa en cada sistema. Que el
dashboard pueda ejecutarse en un sistema no implica que todos los simuladores
estén disponibles allí.

## Simuladores

| Simulador | Adaptador | Datos / requisitos | Validación en juego |
| --- | --- | --- | --- |
| Assetto Corsa original (2014) | Implementado | Shared Memory para el jugador; app Python T-ReS para rivales, posiciones y clasificación | Validado en vivo en Linux/Proton |
| Assetto Corsa Competizione | No implementado | Pendiente verificar protocolo, versión, configuración y cobertura de campos | No disponible |
| F1 25 | No implementado | Pendiente verificar versión de paquetes y opciones UDP del juego | No disponible |
| F1 26 | No implementado | Pendiente verificar protocolo y versión concretos del juego | No disponible |
| Le Mans Ultimate | No implementado | Pendiente verificar API/transporte oficial y campos expuestos | No disponible |

Los adaptadores futuros se añadirán al selector solo tras implementar el
decodificador contra un protocolo documentado. Antes de validar una sesión
real, se marcarán como no verificados en juego. Si un protocolo no expone
posiciones mundiales, tiempos de todos los pilotos o geometría compatible, la
vista correspondiente indicará que no está disponible en vez de estimarla.
