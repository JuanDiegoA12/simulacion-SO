### 1 el modelo de 7 estados podra pausarse, reanudar o ejecutar un paso por cpu
### 2 si un proceso no tiene un recurso asignado pasara a el estado de ejecucion
### 3 si un proceso tiene un recurso asignado y puede hacer uso de el pasa al estado de ejecucion, en caso de no tenerlo disponible pasa por ejecucion y directamente se va al estado bloqueado sin haber descontado ningun tiempo de cpu 
### 4 el proceso que tenga un recurso y se este ejecutando cada vez q termine su turno aleatorieamente se va a definir si suelta el recurso, si suelta el recurso debera pasar a bloqueado hasta la liberacion del recurso, en caso de que no lo suelte volvera a la cola de listo
### 5 si varios procesos llegan al mismo tiempo a la cola, la prioridad es la siguiente, 1ro el proceso que venga del estado ejecutando, 2do el proceso que venga del estado bloqueado y por el ultimo la llegada de un proceso nuevo
### 6 solo puede haber un proceso en el estado de ejecucion los demas estaran esperando en el estado listo, bloqueado y los demas dependiendo de su estado actual
### 7 una vez hayan cumplido todos sus tiempos de paso por cpu dicho proceso pasara al estado de finalizado
