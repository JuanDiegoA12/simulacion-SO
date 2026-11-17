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
2. Crea procesos con nombre, tamaño, uno o varios recursos (separados por comas), la marca de prioridad (checkbox "Prioritario") y la cantidad de pasadas por CPU.
3. La planificación sigue el orden de llegada (turno rotatorio), pero la prioridad manda sobre él. Al crearse, un proceso entra a Listo y toma la CPU si está libre. Si requiere recursos y alguno lo retiene otro proceso, pasa por Listo → Ejecución → Bloqueado sin consumir CPU (adquisición todo-o-nada: solo entra a Ejecución cuando tiene disponibles todos sus recursos); se desbloquea cuando dispone de todos de nuevo. Al terminar cada pasada, un proceso que retiene recursos disputados puede soltar (de forma aleatoria) solo los que otro proceso necesita y pasar a Bloqueado hasta recuperarlos, o conservarlos y volver a Listo. Al completar todas sus pasadas termina y libera memoria, almacenamiento y recursos.
4. Pausa la CPU o avanza una pasada manualmente. Las acciones de bloqueo, desbloqueo, suspensión y reanudación permiten explorar las transiciones restantes del modelo.
5. Consulta las asignaciones y estados en las pestañas de memoria, almacenamiento, estado de recursos y modelo de 7 estados.

La prioridad es booleana (Prioritario / No prioritario) y manda sobre el orden de llegada: los procesos Prioritarios se atienden antes y, al llegar o desbloquearse, desalojan de la CPU a un No prioritario que esté en Ejecución (este vuelve a Listo sin perder su pasada). Entre procesos de la misma prioridad sigue mandando el orden de llegada. Cuando varios llegan a la cola en el mismo instante se desempatan por origen: primero los que vienen de Ejecución, luego los que vienen de Bloqueado y por último los nuevos. La memoria se asigna en bloques contiguos de 1 MB; el almacenamiento conserva la asignación del proceso hasta que termina.

## Pruebas del motor

```bash
python3 -m unittest -v
```
