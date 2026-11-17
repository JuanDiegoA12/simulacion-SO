import random
from dataclasses import dataclass, field
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

# Prioridad de llegada a la cola de Listos (menor valor = mayor prioridad).
# Se aplica para desempatar procesos que llegan a la cola en el mismo instante:
#  1) los que vienen de Ejecución, 2) los que vienen de Bloqueado, 3) los nuevos.
ORIGEN_EJECUCION = 0
ORIGEN_BLOQUEADO = 1
ORIGEN_NUEVO = 2


@dataclass
class Proceso:
    id: str
    nombre: str
    tamano_mb: int
    recursos: str
    prioritario: bool
    pasadas_cpu: int
    restantes: int
    estado: Estado = Estado.LISTO
    # Recursos por los que el proceso está bloqueado (vacío si el bloqueo es manual).
    espera_recursos: set = field(default_factory=set)
    # Prioridad y marca de tiempo con que fue encolado (para el desempate).
    prioridad_cola: int = ORIGEN_NUEVO
    instante_cola: int = 0


class Simulador:
    """Motor de procesos con asignación contigua de memoria y almacenamiento."""

    def __init__(self, memoria_mb=64, almacenamiento_mb=128, probabilidad_soltar_recurso=0.5):
        self._validar_capacidad(memoria_mb, "memoria")
        self._validar_capacidad(almacenamiento_mb, "almacenamiento")
        if not 0 <= probabilidad_soltar_recurso <= 1:
            raise ValueError("La probabilidad de soltar el recurso debe estar entre 0 y 1.")
        self.memoria_mb = memoria_mb
        self.almacenamiento_mb = almacenamiento_mb
        self.probabilidad_soltar_recurso = probabilidad_soltar_recurso
        self.procesos = []
        self._memoria = [None] * memoria_mb
        self._almacenamiento = [None] * almacenamiento_mb
        self._cola_listos = []
        self._ejecutando = None
        self._siguiente_id = 1
        self._instante = 0
        self.eventos = ["Simulación lista."]
        # Diccionario para controlar el propietario de cada recurso: { "Impresora": "P001" }
        self._recursos_ocupados = {}

    @staticmethod
    def _validar_capacidad(capacidad, nombre):
        if not isinstance(capacidad, int) or capacidad < 1:
            raise ValueError(f"La capacidad de {nombre} debe ser un entero mayor que cero.")

    @staticmethod
    def _es_recurso(recurso):
        """True si el texto representa un recurso real (no vacío ni 'Ninguno')."""
        return bool(recurso) and recurso.lower() != "ninguno"

    @classmethod
    def _lista_recursos(cls, texto):
        """Separa el texto por comas y devuelve los recursos reales.

        Descarta vacíos y 'Ninguno', recorta espacios y elimina duplicados
        conservando el orden de aparición. '' o 'Ninguno' devuelven [].
        """
        if not texto:
            return []
        vistos = []
        for parte in texto.split(","):
            recurso = parte.strip()
            if cls._es_recurso(recurso) and recurso not in vistos:
                vistos.append(recurso)
        return vistos

    def crear_proceso(self, nombre, tamano_mb, recursos, prioritario, pasadas_cpu):
        nombre = nombre.strip()
        if not nombre:
            raise ValueError("Escribe un nombre para el proceso.")
        if tamano_mb < 1:
            raise ValueError("El tamaño debe ser de al menos 1 MB.")
        if pasadas_cpu < 1:
            raise ValueError("Las pasadas por CPU deben ser al menos 1.")
        prioritario = bool(prioritario)
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
            prioritario=prioritario,
            pasadas_cpu=pasadas_cpu,
            restantes=pasadas_cpu,
        )
        self.procesos.append(proceso)
        self._siguiente_id += 1
        self._instante += 1
        self._encolar(pid, ORIGEN_NUEVO)
        etiqueta_prio = "Prioritario" if prioritario else "No prioritario"
        self.eventos.insert(
            0, f"{pid} ({nombre}) creado ({etiqueta_prio}) y agregado a Listo."
        )
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

    def _encolar(self, pid, origen):
        """Inserta en la cola de Listos respetando prioridad → origen → FIFO.

        Criterio de orden:
          1) Los procesos Prioritarios van delante de los No prioritarios.
          2) Dentro de la misma prioridad manda el orden de llegada (FIFO).
          3) Entre procesos que llegan en el mismo instante, el origen desempata:
             primero los que vienen de Ejecución, luego de Bloqueado y por último
             los nuevos.
        """
        proceso = self._proceso(pid)
        proceso.prioridad_cola = origen
        proceso.instante_cola = self._instante
        self._cola_listos.append(pid)
        indice = len(self._cola_listos) - 1
        while indice > 0:
            anterior = self._proceso(self._cola_listos[indice - 1])
            if proceso.prioritario and not anterior.prioritario:
                # Un Prioritario adelanta a cualquier No prioritario.
                adelantar = True
            elif proceso.prioritario == anterior.prioritario:
                # Misma prioridad: desempate por origen solo en llegada simultánea.
                mismo_instante = anterior.instante_cola == proceso.instante_cola
                adelantar = mismo_instante and anterior.prioridad_cola > origen
            else:
                # El anterior es Prioritario y el nuevo No: no puede adelantarlo.
                adelantar = False
            if adelantar:
                self._cola_listos[indice - 1], self._cola_listos[indice] = (
                    self._cola_listos[indice],
                    self._cola_listos[indice - 1],
                )
                indice -= 1
            else:
                break

    def _hay_competencia(self, recurso, pid):
        """True si otro proceso alcanzable necesita el mismo recurso."""
        for proceso in self.procesos:
            if proceso.id == pid or proceso.estado == Estado.TERMINADO:
                continue
            if proceso.estado == Estado.LISTO:
                if recurso in self._lista_recursos(proceso.recursos):
                    return True
            if proceso.estado == Estado.BLOQUEADO and recurso in proceso.espera_recursos:
                return True
        return False

    def _bloquear_por_recurso(self, proceso, faltantes):
        """Recorre Listo → Ejecución → Bloqueado sin descontar pasadas de CPU.

        'faltantes' es un dict {recurso: propietario} con los recursos que el
        proceso necesita pero que otros retienen. El proceso ya venía de la cola
        de Listos; deja explícito el recorrido por Ejecución antes de quedar
        Bloqueado y lo registra en un único evento legible. No modifica
        'restantes': no se consume ninguna pasada de CPU.
        """
        proceso.estado = Estado.LISTO
        proceso.estado = Estado.EJECUCION
        proceso.estado = Estado.BLOQUEADO
        proceso.espera_recursos = set(faltantes)
        recursos_txt = ", ".join(faltantes)
        propietarios_txt = ", ".join(dict.fromkeys(faltantes.values()))
        plural = "los recursos" if len(faltantes) > 1 else "el recurso"
        self.eventos.insert(
            0,
            f"{proceso.id} ({proceso.nombre}) intentó {plural} '{recursos_txt}' "
            f"(ocupado(s) por {propietarios_txt}): Listo → Ejecución → Bloqueado, "
            f"sin consumir CPU.",
        )

    def _desbloquear_espera(self, recurso, excepto=None):
        """Quita el recurso liberado del conjunto de espera de cada proceso.

        Un proceso bloqueado por varios recursos solo despierta cuando ya no le
        falta ninguno. Los bloqueados de forma manual (conjunto vacío) no se ven
        afectados.
        """
        for proceso in self.procesos:
            if proceso.id == excepto or recurso not in proceso.espera_recursos:
                continue
            proceso.espera_recursos.discard(recurso)
            if proceso.espera_recursos:
                # Aún le faltan otros recursos: sigue esperando.
                self.eventos.insert(
                    0,
                    f"{proceso.id} ({proceso.nombre}) sigue bloqueado; aún espera "
                    f"'{', '.join(sorted(proceso.espera_recursos))}'.",
                )
                continue
            if proceso.estado == Estado.BLOQUEADO:
                proceso.estado = Estado.LISTO
                self._encolar(proceso.id, ORIGEN_BLOQUEADO)
                self.eventos.insert(
                    0,
                    f"{proceso.id} ({proceso.nombre}) se desbloqueó "
                    f"(ya tiene todos sus recursos).",
                )
            elif proceso.estado == Estado.BLOQUEADO_SUSPENDIDO:
                proceso.estado = Estado.LISTO_SUSPENDIDO
                self.eventos.insert(
                    0,
                    f"{proceso.id} ({proceso.nombre}) cambió a Listo Suspendido "
                    f"(ya tiene todos sus recursos).",
                )

    def _hay_prioritario_en_cola(self):
        """True si algún proceso Listo en la cola es Prioritario."""
        for pid in self._cola_listos:
            proceso = self._proceso(pid)
            if proceso.estado == Estado.LISTO and proceso.prioritario:
                return True
        return False

    def _preemptar_si_corresponde(self):
        """Desaloja al proceso en Ejecución si es No prioritario y hay un
        Prioritario esperando en la cola de Listos.

        El desalojado vuelve a Listo sin perder una pasada de CPU (no se toca
        'restantes') y conserva los recursos que ya tenía asignados.
        """
        if self._ejecutando is None:
            return
        ejecutando = self._proceso(self._ejecutando)
        if ejecutando.prioritario or not self._hay_prioritario_en_cola():
            return
        ejecutando.estado = Estado.LISTO
        self._ejecutando = None
        self._encolar(ejecutando.id, ORIGEN_EJECUCION)
        self.eventos.insert(
            0,
            f"{ejecutando.id} ({ejecutando.nombre}) fue desalojado de Ejecución "
            f"por un proceso Prioritario; vuelve a Listo sin perder su pasada.",
        )

    def _despachar(self):
        self._preemptar_si_corresponde()
        if self._ejecutando is not None:
            return
        while self._cola_listos:
            pid = self._cola_listos[0]
            proceso = self._proceso(pid)
            if proceso.estado != Estado.LISTO:
                self._cola_listos.pop(0)
                continue

            recursos_requeridos = self._lista_recursos(proceso.recursos)
            if recursos_requeridos:
                faltantes = {}
                for recurso in recursos_requeridos:
                    propietario = self._recursos_ocupados.get(recurso)
                    if propietario is not None and propietario != pid:
                        faltantes[recurso] = propietario
                if faltantes:
                    # Falta al menos un recurso: adquisición todo-o-nada fallida.
                    # Pasa por Ejecución y se bloquea sin descontar tiempo de CPU,
                    # sin adquirir ninguno de los recursos libres.
                    self._cola_listos.pop(0)
                    self._bloquear_por_recurso(proceso, faltantes)
                    continue
                # Todos disponibles: se adquieren juntos.
                for recurso in recursos_requeridos:
                    self._recursos_ocupados[recurso] = pid

            self._cola_listos.pop(0)
            proceso.estado = Estado.EJECUCION
            self._ejecutando = pid
            self.eventos.insert(0, f"{pid} ({proceso.nombre}) entra a Ejecución.")
            return

    def _liberar_recursos(self, pid):
        """Libera todos los recursos retenidos por un proceso al terminar."""
        recursos_a_liberar = [
            rec for rec, propietario in self._recursos_ocupados.items() if propietario == pid
        ]
        for rec in recursos_a_liberar:
            del self._recursos_ocupados[rec]
            self.eventos.insert(0, f"Recurso '{rec}' liberado por {pid}.")
            self._desbloquear_espera(rec)

    def avanzar(self):
        """Consume una pasada de CPU y despacha el siguiente proceso en espera."""
        self._despachar()
        if self._ejecutando is None:
            return None
        self._instante += 1
        proceso = self._proceso(self._ejecutando)
        proceso.restantes -= 1
        pid_ejecutado = proceso.id
        self._ejecutando = None

        if proceso.restantes == 0:
            proceso.estado = Estado.TERMINADO
            self._liberar(self._memoria, pid_ejecutado)
            self._liberar(self._almacenamiento, pid_ejecutado)
            self.eventos.insert(0, f"{pid_ejecutado} ({proceso.nombre}) terminó.")
            self._liberar_recursos(pid_ejecutado)
        else:
            # Recursos que retiene este proceso y que además tienen competencia.
            retenidos = [
                rec
                for rec, propietario in self._recursos_ocupados.items()
                if propietario == pid_ejecutado
            ]
            disputados = [
                rec for rec in retenidos if self._hay_competencia(rec, pid_ejecutado)
            ]
            if disputados and random.random() < self.probabilidad_soltar_recurso:
                # Suelta solo los recursos disputados; conserva los demás.
                for rec in disputados:
                    del self._recursos_ocupados[rec]
                proceso.estado = Estado.BLOQUEADO
                proceso.espera_recursos = set(disputados)
                self.eventos.insert(
                    0,
                    f"{pid_ejecutado} ({proceso.nombre}) soltó "
                    f"'{', '.join(disputados)}' y pasa a BLOQUEADO hasta recuperarlo(s).",
                )
                for rec in disputados:
                    self._desbloquear_espera(rec, excepto=pid_ejecutado)
            else:
                proceso.estado = Estado.LISTO
                self._encolar(pid_ejecutado, ORIGEN_EJECUCION)
                self.eventos.insert(
                    0,
                    f"{pid_ejecutado} ({proceso.nombre}) completó una pasada; vuelve a Listo.",
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
        proceso.espera_recursos = set()
        self._instante += 1
        self._encolar(pid, ORIGEN_BLOQUEADO)
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
            self._instante += 1
            self._encolar(pid, ORIGEN_BLOQUEADO)
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

    def limpiar_simulacion(self):
        """Reinicia la simulación: borra procesos y libera memoria, almacenamiento y recursos."""
        self.procesos = []
        self._memoria = [None] * self.memoria_mb
        self._almacenamiento = [None] * self.almacenamiento_mb
        self._cola_listos = []
        self._ejecutando = None
        self._recursos_ocupados = {}
        self._siguiente_id = 1
        self._instante = 0
        self.eventos = ["Simulación reiniciada."]

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
