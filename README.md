# Simulador de procesos de un sistema operativo

Aplicación de escritorio local en Python, inspirada en las referencias compartidas. No utiliza navegador, servidor ni servicios externos. La interfaz usa Tkinter, incluido con muchas instalaciones de Python.

## Requisitos y ejecución

- Python 3.10 o posterior.
- Tkinter. En Debian/Ubuntu, si no está instalado: `sudo apt install python3-tk`.

Desde una terminal abierta en esta carpeta:

```bash
python3 app.py
```

También se puede abrir la carpeta en Visual Studio Code y ejecutar `app.py`.

## Uso

1. Configura la memoria y el almacenamiento en MB, y el intervalo de cada pasada de CPU en segundos.
2. Crea procesos con nombre, tamaño, recursos, prioridad y cantidad de pasadas por CPU.
3. La planificación sigue el orden de llegada. Al crearse, un proceso entra a Listo y toma la CPU inmediatamente si está libre. En cada pasada, si aún le queda trabajo vuelve al final de la cola; al completar todas sus pasadas termina y libera memoria y almacenamiento.
4. Pausa la CPU o avanza una pasada manualmente. Las acciones de bloqueo, desbloqueo, suspensión y reanudación permiten explorar las transiciones restantes del modelo.
5. Consulta las asignaciones y estados en las pestañas de memoria, almacenamiento y modelo de 7 estados.

La prioridad se guarda y se muestra, pero no altera el orden de llegada. La memoria se asigna en bloques contiguos de 1 MB; el almacenamiento conserva la asignación del proceso hasta que termina.

## Pruebas del motor

```bash
python3 -m unittest -v
```
