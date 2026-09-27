from dataclasses import dataclass
from enum import Enum


class Estado(str, Enum):
    LISTO_SUSPENDIDO = "Listo suspendido"
    LISTO = "Listo"
    EJECUCION = "Ejecución"
    BLOQUEADO = "Bloqueado"
    BLOQUEADO_SUSPENDIDO = "Bloqueado suspendido"
    TERMINADO = "Terminado"


ESTADOS = (
    "Nuevo",
    Estado.LISTO_SUSPENDIDO.value,
    Estado.LISTO.value,
    Estado.EJECUCION.value,
    Estado.TERMINADO.value,
    Estado.BLOQUEADO.value,
    Estado.BLOQUEADO_SUSPENDIDO.value,
)


@dataclass
class Proceso:
    id: str
    nombre: str
    tamano_mb: int
    recursos: str
    prioridad: int
    pasadas_cpu: int
    restantes: int
    estado: Estado = Estado.LISTO


class Simulador:
    """Motor de procesos con asignación contigua de memoria y almacenamiento."""

    def __init__(self, memoria_mb=64, almacenamiento_mb=128):
        self._validar_capacidad(memoria_mb, "memoria")
        self._validar_capacidad(almacenamiento_mb, "almacenamiento")
        self.memoria_mb = memoria_mb
        self.almacenamiento_mb = almacenamiento_mb
        self.procesos = []
        self._memoria = [None] * memoria_mb
        self._almacenamiento = [None] * almacenamiento_mb
        self._cola_listos = []
        self._ejecutando = None
        self._siguiente_id = 1
        self.eventos = ["Simulación lista."]

    @staticmethod
    def _validar_capacidad(capacidad, nombre):
        if not isinstance(capacidad, int) or capacidad < 1:
            raise ValueError(f"La capacidad de {nombre} debe ser un entero mayor que cero.")

    def crear_proceso(self, nombre, tamano_mb, recursos, prioridad, pasadas_cpu):
        nombre = nombre.strip()
        if not nombre:
            raise ValueError("Escribe un nombre para el proceso.")
        if tamano_mb < 1:
            raise ValueError("El tamaño debe ser de al menos 1 MB.")
        if pasadas_cpu < 1:
            raise ValueError("Las pasadas por CPU deben ser al menos 1.")
        if prioridad < 1:
            raise ValueError("La prioridad debe ser al menos 1.")
        if tamano_mb > self.memoria_mb:
            raise ValueError(
                f"El proceso necesita {tamano_mb} MB, pero la memoria total es "
                f"de {self.memoria_mb} MB."
            )
        if tamano_mb > self.almacenamiento_mb:
            raise ValueError(
                f"El proceso necesita {tamano_mb} MB, pero el almacenamiento total es "
                f"de {self.almacenamiento_mb} MB."
            )

        pid = f"P{self._siguiente_id:03d}"
        inicio_memoria = self._buscar_espacio(self._memoria, tamano_mb)
        inicio_almacenamiento = self._buscar_espacio(
            self._almacenamiento, tamano_mb
        )
        if inicio_memoria is None:
            raise ValueError(
                "No hay un bloque contiguo suficiente en memoria para este proceso."
            )
        if inicio_almacenamiento is None:
            raise ValueError(
                "No hay un bloque contiguo suficiente en almacenamiento para este proceso."
            )

        self._asignar(self._memoria, inicio_memoria, tamano_mb, pid)
        self._asignar(
            self._almacenamiento, inicio_almacenamiento, tamano_mb, pid
        )
        proceso = Proceso(
            id=pid,
            nombre=nombre,
            tamano_mb=tamano_mb,
            recursos=recursos.strip() or "Ninguno",
            prioridad=prioridad,
            pasadas_cpu=pasadas_cpu,
            restantes=pasadas_cpu,
        )
        self.procesos.append(proceso)
        self._siguiente_id += 1
        self._cola_listos.append(pid)
        self.eventos.insert(0, f"{pid} ({nombre}) creado y agregado a Listo.")
        self._despachar()
        return proceso

    @staticmethod
    def _buscar_espacio(bloques, tamano):
        consecutivos = 0
        for indice, propietario in enumerate(bloques):
            consecutivos = consecutivos + 1 if propietario is None else 0
            if consecutivos == tamano:
                return indice - tamano + 1
        return None

    @staticmethod
    def _asignar(bloques, inicio, tamano, pid):
        bloques[inicio : inicio + tamano] = [pid] * tamano

    def _proceso(self, pid):
        for proceso in self.procesos:
            if proceso.id == pid:
                return proceso
        raise ValueError("No se encontró el proceso seleccionado.")

    def _despachar(self):
        if self._ejecutando is not None:
            return
        while self._cola_listos:
            pid = self._cola_listos.pop(0)
            proceso = self._proceso(pid)
            if proceso.estado == Estado.LISTO:
                proceso.estado = Estado.EJECUCION
                self._ejecutando = pid
                self.eventos.insert(0, f"{pid} ({proceso.nombre}) entra a Ejecución.")
                return

    def avanzar(self):
        """Consume una pasada de CPU y despacha el siguiente proceso en espera."""
        self._despachar()
        if self._ejecutando is None:
            return None
        proceso = self._proceso(self._ejecutando)
        proceso.restantes -= 1
        pid_ejecutado = proceso.id
        if proceso.restantes == 0:
            proceso.estado = Estado.TERMINADO
            self._liberar(self._memoria, pid_ejecutado)
            self._liberar(self._almacenamiento, pid_ejecutado)
            self._ejecutando = None
            self.eventos.insert(0, f"{pid_ejecutado} ({proceso.nombre}) terminó.")
        else:
            proceso.estado = Estado.LISTO
            self._cola_listos.append(pid_ejecutado)
            self._ejecutando = None
            self.eventos.insert(
                0,
                f"{pid_ejecutado} completó una pasada; vuelve al final de Listo.",
            )
        self._despachar()
        return proceso

    @property
    def proceso_ejecutando(self):
        if self._ejecutando is None:
            return None
        return self._proceso(self._ejecutando)

    @property
    def memoria_libre_mb(self):
        return self._memoria.count(None)

    @property
    def almacenamiento_libre_mb(self):
        return self._almacenamiento.count(None)

    def bloquear_ejecucion(self):
        if self._ejecutando is None:
            raise ValueError("No hay un proceso en ejecución para bloquear.")
        proceso = self._proceso(self._ejecutando)
        proceso.estado = Estado.BLOQUEADO
        self._ejecutando = None
        self.eventos.insert(0, f"{proceso.id} ({proceso.nombre}) pasó a Bloqueado.")
        self._despachar()
        return proceso

    def desbloquear(self, pid):
        proceso = self._proceso(pid)
        if proceso.estado != Estado.BLOQUEADO:
            raise ValueError("Selecciona un proceso que esté en estado Bloqueado.")
        proceso.estado = Estado.LISTO
        self._cola_listos.append(pid)
        self.eventos.insert(0, f"{pid} ({proceso.nombre}) volvió a Listo.")
        self._despachar()

    def suspender(self, pid):
        proceso = self._proceso(pid)
        if proceso.estado == Estado.LISTO:
            proceso.estado = Estado.LISTO_SUSPENDIDO
            estado_nuevo = Estado.LISTO_SUSPENDIDO.value
        elif proceso.estado == Estado.BLOQUEADO:
            proceso.estado = Estado.BLOQUEADO_SUSPENDIDO
            estado_nuevo = Estado.BLOQUEADO_SUSPENDIDO.value
        else:
            raise ValueError(
                "Solo se pueden suspender procesos Listos o Bloqueados."
            )
        if pid in self._cola_listos:
            self._cola_listos.remove(pid)
        self._liberar(self._memoria, pid)
        self.eventos.insert(0, f"{pid} ({proceso.nombre}) pasó a {estado_nuevo}.")
        self._despachar()

    def reanudar(self, pid):
        proceso = self._proceso(pid)
        if proceso.estado == Estado.LISTO_SUSPENDIDO:
            siguiente_estado = Estado.LISTO
        elif proceso.estado == Estado.BLOQUEADO_SUSPENDIDO:
            siguiente_estado = Estado.BLOQUEADO
        else:
            raise ValueError(
                "Selecciona un proceso que esté suspendido para reanudarlo."
            )
        inicio = self._buscar_espacio(self._memoria, proceso.tamano_mb)
        if inicio is None:
            raise ValueError(
                "No hay un bloque contiguo suficiente en memoria para reanudar "
                "este proceso."
            )
        self._asignar(self._memoria, inicio, proceso.tamano_mb, pid)
        proceso.estado = siguiente_estado
        if siguiente_estado == Estado.LISTO:
            self._cola_listos.append(pid)
            self._despachar()
        self.eventos.insert(
            0, f"{pid} ({proceso.nombre}) se reanudó como {siguiente_estado.value}."
        )

    def cambiar_capacidades(self, memoria_mb, almacenamiento_mb):
        self._validar_capacidad(memoria_mb, "memoria")
        self._validar_capacidad(almacenamiento_mb, "almacenamiento")
        if any(self._memoria[memoria_mb:]):
            raise ValueError(
                "No se puede reducir la memoria: hay procesos asignados en ese rango."
            )
        if any(self._almacenamiento[almacenamiento_mb:]):
            raise ValueError(
                "No se puede reducir el almacenamiento: hay procesos asignados "
                "en ese rango."
            )
        self._memoria = self._memoria[:memoria_mb] + [None] * max(
            0, memoria_mb - len(self._memoria)
        )
        self._almacenamiento = self._almacenamiento[:almacenamiento_mb] + [
            None
        ] * max(0, almacenamiento_mb - len(self._almacenamiento))
        self.memoria_mb = memoria_mb
        self.almacenamiento_mb = almacenamiento_mb
        self.eventos.insert(
            0,
            f"Capacidades actualizadas: memoria {memoria_mb} MB, "
            f"almacenamiento {almacenamiento_mb} MB.",
        )

    @staticmethod
    def _liberar(bloques, pid):
        for indice, propietario in enumerate(bloques):
            if propietario == pid:
                bloques[indice] = None

    @staticmethod
    def _segmentos(bloques):
        if not bloques:
            return []
        segmentos = []
        inicio = 0
        propietario = bloques[0]
        for indice in range(1, len(bloques) + 1):
            siguiente = bloques[indice] if indice < len(bloques) else object()
            if siguiente != propietario:
                segmentos.append((inicio, indice - 1, propietario))
                inicio = indice
                propietario = siguiente
        return segmentos

    def segmentos_memoria(self):
        return self._segmentos(self._memoria)

    def segmentos_almacenamiento(self):
        return self._segmentos(self._almacenamiento)
