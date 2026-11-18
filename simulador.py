import math
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

RECURSOS_SISTEMA = ("Impresora", "Disco", "Red", "Escáner", "GPU")

MODO_PAGINACION = "Paginación (Asignación Fija)"
MODO_DINAMICO = "Particiones Dinámicas"
MODOS_MEMORIA = (MODO_PAGINACION, MODO_DINAMICO)

ORIGEN_EJECUCION = 0
ORIGEN_BLOQUEADO = 1
ORIGEN_NUEVO = 2

MARCOS_BASE = 16

# La memoria virtual (swap) que respalda a los procesos se dimensiona como un
# múltiplo de la RAM (regla clásica de ~2× RAM). El disco total puede ser mayor,
# pero solo esta porción funciona como swap.
FACTOR_SWAP = 2


@dataclass
class Proceso:
    id: str
    nombre: str
    tamano_mb: int
    hilos: int
    recursos: str
    prioritario: bool
    pasadas_cpu: int
    restantes: int
    estado: Estado = Estado.LISTO
    total_paginas: int = 1
    tabla_paginas: dict = field(default_factory=dict)
    orden_fifo_paginas: list = field(default_factory=list)
    pagina_actual: int = 0
    fallos_pagina: int = 0
    paginas_modificadas: set = field(default_factory=set)
    particion_ram: tuple = None
    espera_recursos: set = field(default_factory=set)
    prioridad_cola: int = ORIGEN_NUEVO
    instante_cola: int = 0
    # Tick de CPU en que el proceso llegó a Listo desde Bloqueado/suspendido.
    # Sirve para que se detenga un ciclo visible en Listo antes de Ejecución.
    recien_listo_tick: int = -1
    # Instante en que el proceso entró a Bloqueado (para elegir víctima de swap-out
    # por antigüedad: el bloqueado más antiguo se suspende primero).
    bloqueado_desde_instante: int = -1


class Simulador:
    """Motor de procesos con Paginación (Política Fija + FIFO), Particiones Dinámicas y Memoria Virtual."""

    def __init__(
        self,
        memoria_mb=64,
        almacenamiento_mb=128,
        modo_memoria=MODO_PAGINACION,
        marcos_fijos_por_proceso=3,
        probabilidad_soltar_recurso=0.5,
    ):
        self._validar_capacidad(memoria_mb, "memoria")
        self._validar_capacidad(almacenamiento_mb, "almacenamiento")
        if not 0 <= probabilidad_soltar_recurso <= 1:
            raise ValueError("La probabilidad de soltar el recurso debe estar entre 0 y 1.")
        self.memoria_mb = memoria_mb
        self.almacenamiento_mb = almacenamiento_mb
        self.swap_mb = self._calcular_swap(memoria_mb, almacenamiento_mb)
        self.modo_memoria = modo_memoria
        self.marcos_fijos_por_proceso = marcos_fijos_por_proceso
        self.probabilidad_soltar_recurso = probabilidad_soltar_recurso

        self.procesos = []
        self._bloques_swap = []
        self._cola_listos = []
        self._ejecutando = None
        self._siguiente_id = 1
        self._instante = 0
        self._tick = 0
        self.total_fallos_pagina = 0
        self.eventos = [f"Simulación lista · Modo: {self.modo_memoria} · Reemplazo: FIFO."]
        self.recursos_disponibles = {rec: True for rec in RECURSOS_SISTEMA}
        self._recursos_ocupados = {}
        self._inicializar_memoria()

    def _inicializar_memoria(self):
        self.tamano_marco_mb = max(1, self.memoria_mb // MARCOS_BASE)
        self.total_marcos = max(1, self.memoria_mb // self.tamano_marco_mb)
        self._marcos = [None] * self.total_marcos
        self._particiones = [[0, self.memoria_mb, None]]

    @staticmethod
    def _validar_capacidad(capacidad, nombre):
        if not isinstance(capacidad, int) or capacidad < 1:
            raise ValueError(f"La capacidad de {nombre} debe ser un entero mayor que cero.")

    @staticmethod
    def _calcular_swap(memoria_mb, almacenamiento_mb):
        """Swap = FACTOR_SWAP × RAM, acotado por el disco disponible.

        El disco debe poder contener el área de swap; si no, es un error de
        configuración.
        """
        swap = FACTOR_SWAP * memoria_mb
        if almacenamiento_mb < swap:
            raise ValueError(
                f"El disco de {almacenamiento_mb} MB no alcanza para el swap "
                f"requerido (memoria virtual = {FACTOR_SWAP}× RAM = {swap} MB). "
                f"Aumenta el disco o reduce la RAM."
            )
        return swap

    @staticmethod
    def _es_recurso(recurso):
        return bool(recurso) and recurso.lower() != "ninguno"

    @classmethod
    def _lista_recursos(cls, texto):
        if isinstance(texto, (list, tuple, set)):
            return [r.strip() for r in texto if cls._es_recurso(r.strip())]
        if not texto:
            return []
        vistos = []
        for parte in texto.split(","):
            recurso = parte.strip()
            if cls._es_recurso(recurso) and recurso not in vistos:
                vistos.append(recurso)
        return vistos

    def _paginas_requeridas(self, tamano_mb):
        return max(1, math.ceil(tamano_mb / self.tamano_marco_mb))

    @property
    def marcos_libres(self):
        return [idx for idx, ocupado in enumerate(self._marcos) if ocupado is None]

    def _asignar_paginacion_fija(self, proceso):
        necesarias = self._paginas_requeridas(proceso.tamano_mb)
        proceso.total_paginas = necesarias
        marcos_a_asignar = min(necesarias, self.marcos_fijos_por_proceso)
        libres = self.marcos_libres
        if len(libres) < marcos_a_asignar:
            return False

        proceso.tabla_paginas = {}
        proceso.orden_fifo_paginas = []
        for pagina in range(marcos_a_asignar):
            marco = libres[pagina]
            self._marcos[marco] = (proceso.id, pagina)
            proceso.tabla_paginas[pagina] = marco
            proceso.orden_fifo_paginas.append(pagina)
        return True

    def _acceder_pagina_virtual(self, proceso):
        if self.modo_memoria != MODO_PAGINACION or proceso.total_paginas <= 0:
            return
        pagina_obj = proceso.pagina_actual % proceso.total_paginas
        proceso.pagina_actual = (proceso.pagina_actual + 1) % proceso.total_paginas
        if pagina_obj % 2 == 1:
            proceso.paginas_modificadas.add(pagina_obj)

        if pagina_obj in proceso.tabla_paginas:
            marco = proceso.tabla_paginas[pagina_obj]
            self.eventos.insert(
                0,
                f"[MMU] {proceso.id} accedió Pág.{pagina_obj} → Acierto TLB/RAM (Marco {marco}, Bit P=1).",
            )
        else:
            proceso.fallos_pagina += 1
            self.total_fallos_pagina += 1
            pag_victima = proceso.orden_fifo_paginas.pop(0)
            marco_reutilizado = proceso.tabla_paginas.pop(pag_victima)
            proceso.paginas_modificadas.discard(pag_victima)

            self._marcos[marco_reutilizado] = (proceso.id, pagina_obj)
            proceso.tabla_paginas[pagina_obj] = marco_reutilizado
            proceso.orden_fifo_paginas.append(pagina_obj)

            self.eventos.insert(
                0,
                f"[Fallo Pág #{proceso.fallos_pagina}] {proceso.id} cargó Pág.{pagina_obj} desde Disco → "
                f"Reemplazo FIFO sacó Pág.{pag_victima} (Marco {marco_reutilizado}).",
            )

    def _asignar_particion_dinamica(self, proceso):
        for idx, (inicio, tam, propietario) in enumerate(self._particiones):
            if propietario is None and tam >= proceso.tamano_mb:
                sobrante = tam - proceso.tamano_mb
                self._particiones[idx] = [inicio, proceso.tamano_mb, proceso.id]
                if sobrante > 0:
                    self._particiones.insert(idx + 1, [inicio + proceso.tamano_mb, sobrante, None])
                proceso.particion_ram = (inicio, inicio + proceso.tamano_mb - 1)
                return True
        return False

    def _compactar_huecos_adyacentes(self):
        i = 0
        while i < len(self._particiones) - 1:
            ini_a, tam_a, prop_a = self._particiones[i]
            ini_b, tam_b, prop_b = self._particiones[i + 1]
            if prop_a is None and prop_b is None:
                self._particiones[i] = [ini_a, tam_a + tam_b, None]
                self._particiones.pop(i + 1)
            else:
                i += 1

    def _asignar_memoria_proceso(self, proceso):
        if self.modo_memoria == MODO_PAGINACION:
            return self._asignar_paginacion_fija(proceso)
        return self._asignar_particion_dinamica(proceso)

    def _liberar_memoria_proceso(self, pid):
        for idx, contenido in enumerate(self._marcos):
            if contenido is not None and contenido[0] == pid:
                self._marcos[idx] = None
        for part in self._particiones:
            if part[2] == pid:
                part[2] = None
        self._compactar_huecos_adyacentes()

        for p in self.procesos:
            if p.id == pid:
                p.tabla_paginas = {}
                p.orden_fifo_paginas = []
                p.particion_ram = None

    def _es_residente(self, proceso):
        """True si el proceso tiene memoria asignada en RAM."""
        if self.modo_memoria == MODO_PAGINACION:
            return bool(proceso.tabla_paginas)
        return proceso.particion_ram is not None

    def _liberar_ram_suspendiendo(self, min_mb):
        """Swap-out automático: suspende Bloqueados residentes para liberar RAM.

        Planificador a mediano plazo. Elige como víctima un proceso Bloqueado
        residente y NO prioritario; entre varios, el que lleva más tiempo
        bloqueado (criterio clásico: un proceso mucho tiempo en espera es buen
        candidato). Nunca suspende Prioritarios. Suspende de a uno hasta que la
        RAM libre alcance 'min_mb' o no queden candidatos. Devuelve True si al
        final hay al menos 'min_mb' libres.
        """
        if self.memoria_libre_mb >= min_mb:
            return True
        while self.memoria_libre_mb < min_mb:
            candidatos = [
                p
                for p in self.procesos
                if p.estado == Estado.BLOQUEADO
                and not p.prioritario
                and self._es_residente(p)
            ]
            if not candidatos:
                break
            # El bloqueado más antiguo primero (menor instante de bloqueo).
            victima = min(candidatos, key=lambda p: p.bloqueado_desde_instante)
            victima.estado = Estado.BLOQUEADO_SUSPENDIDO
            if victima.id in self._cola_listos:
                self._cola_listos.remove(victima.id)
            self._liberar_memoria_proceso(victima.id)
            self.eventos.insert(
                0,
                f"[Swap-Out] {victima.id} ({victima.nombre}) suspendido a Disco "
                f"(Bloqueado → Bloqueado suspendido) para liberar RAM.",
            )
        return self.memoria_libre_mb >= min_mb

    def _admitir_suspendidos_si_hay_ram(self):
        """Planificador a mediano plazo: recarga procesos suspendidos cuando hay RAM.

        Primero reactiva los Listo suspendido (pueden ejecutar al volver). Luego
        los Bloqueado suspendido vuelven a Bloqueado aunque su recurso siga
        ocupado: regresan a RAM y conservan su espera (espera_recursos).
        """
        for proceso in self.procesos:
            if proceso.estado == Estado.LISTO_SUSPENDIDO:
                if self._asignar_memoria_proceso(proceso):
                    proceso.estado = Estado.LISTO
                    proceso.recien_listo_tick = self._tick
                    self._instante += 1
                    self._encolar(proceso.id, ORIGEN_BLOQUEADO)
                    self.eventos.insert(
                        0,
                        f"[Swap-In] {proceso.id} ({proceso.nombre}) cargado automáticamente de Disco → Listo.",
                    )
        for proceso in self.procesos:
            if proceso.estado == Estado.BLOQUEADO_SUSPENDIDO:
                if self._asignar_memoria_proceso(proceso):
                    proceso.estado = Estado.BLOQUEADO
                    proceso.bloqueado_desde_instante = self._instante
                    self.eventos.insert(
                        0,
                        f"[Swap-In] {proceso.id} ({proceso.nombre}) cargado de Disco → "
                        f"Bloqueado (sigue esperando sus recursos).",
                    )

    def crear_proceso(self, nombre, tamano_mb, recursos, prioritario, pasadas_cpu, hilos=1):
        nombre = nombre.strip()
        if not nombre:
            raise ValueError("Escribe un nombre para el proceso.")
        if tamano_mb < 1:
            raise ValueError("El tamaño debe ser de al menos 1 MB.")
        if pasadas_cpu < 1:
            raise ValueError("Las pasadas por CPU deben ser al menos 1.")
        if hilos < 1:
            raise ValueError("El número de hilos debe ser al menos 1.")

        if tamano_mb > self.swap_libre_mb:
            raise ValueError(
                f"Memoria Virtual (Swap = 2× RAM) insuficiente: {self.swap_libre_mb} MB "
                f"libres de {self.swap_mb} MB de swap para respaldar este proceso de {tamano_mb} MB."
            )

        prioritario = bool(prioritario)
        lista_rec = self._lista_recursos(recursos)
        recursos_txt = ", ".join(lista_rec) if lista_rec else "Ninguno"

        for rec in lista_rec:
            if rec not in self.recursos_disponibles:
                self.recursos_disponibles[rec] = True

        pid = f"P{self._siguiente_id:03d}"
        self._bloques_swap.append((pid, tamano_mb))

        proceso = Proceso(
            id=pid,
            nombre=nombre,
            tamano_mb=tamano_mb,
            hilos=hilos,
            recursos=recursos_txt,
            prioritario=prioritario,
            pasadas_cpu=pasadas_cpu,
            restantes=pasadas_cpu,
            estado=Estado.LISTO,
            total_paginas=self._paginas_requeridas(tamano_mb),
        )
        self.procesos.append(proceso)
        self._siguiente_id += 1
        self._instante += 1
        etiqueta_prio = "Prioritario" if prioritario else "No prioritario"

        asignado = self._asignar_memoria_proceso(proceso)
        if not asignado:
            # Presión de RAM: intenta liberar suspendiendo Bloqueados residentes.
            necesario = self.tamano_marco_mb if self.modo_memoria == MODO_PAGINACION else tamano_mb
            if self._liberar_ram_suspendiendo(necesario):
                asignado = self._asignar_memoria_proceso(proceso)

        if asignado:
            self._encolar(pid, ORIGEN_NUEVO)
            if self.modo_memoria == MODO_PAGINACION:
                en_ram = len(proceso.tabla_paginas)
                en_swap = proceso.total_paginas - en_ram
                detalle = f"{en_ram} marco(s) fijos en RAM, {en_swap} pág(s) en Swap"
            else:
                ini, fin = proceso.particion_ram
                detalle = f"Partición dinámica {ini}–{fin} MB"
            self.eventos.insert(
                0,
                f"{pid} ({nombre}) creado [{detalle}, {etiqueta_prio}] → Listo.",
            )
            self._despachar()
        else:
            proceso.estado = Estado.LISTO_SUSPENDIDO
            self.eventos.insert(
                0,
                f"{pid} ({nombre}) sin espacio suficiente en RAM → Listo suspendido (en Memoria Virtual).",
            )

        return proceso

    def _proceso(self, pid):
        for proceso in self.procesos:
            if proceso.id == pid:
                return proceso
        raise ValueError("No se encontró el proceso seleccionado.")

    def _encolar(self, pid, origen):
        proceso = self._proceso(pid)
        proceso.prioridad_cola = origen
        proceso.instante_cola = self._instante
        self._cola_listos.append(pid)
        indice = len(self._cola_listos) - 1
        while indice > 0:
            anterior = self._proceso(self._cola_listos[indice - 1])
            if proceso.prioritario and not anterior.prioritario:
                adelantar = True
            elif proceso.prioritario == anterior.prioritario:
                mismo_instante = anterior.instante_cola == proceso.instante_cola
                adelantar = mismo_instante and anterior.prioridad_cola > origen
            else:
                adelantar = False
            if adelantar:
                self._cola_listos[indice - 1], self._cola_listos[indice] = (
                    self._cola_listos[indice],
                    self._cola_listos[indice - 1],
                )
                indice -= 1
            else:
                break

    def _bloquear_por_recurso(self, proceso, faltantes):
        proceso.estado = Estado.LISTO
        proceso.estado = Estado.EJECUCION
        proceso.estado = Estado.BLOQUEADO
        proceso.bloqueado_desde_instante = self._instante
        proceso.espera_recursos = set(faltantes)
        recursos_txt = ", ".join(faltantes)
        propietarios_txt = ", ".join(dict.fromkeys(faltantes.values()))
        self.eventos.insert(
            0,
            f"{proceso.id} ({proceso.nombre}) requiere '{recursos_txt}' "
            f"(en uso por {propietarios_txt}): Listo → Ejecución → Bloqueado (sin consumir CPU).",
        )

    def _desbloquear_espera(self, recurso, excepto=None):
        for proceso in self.procesos:
            if proceso.id == excepto or recurso not in proceso.espera_recursos:
                continue
            proceso.espera_recursos.discard(recurso)
            if proceso.espera_recursos:
                self.eventos.insert(
                    0,
                    f"{proceso.id} ({proceso.nombre}) sigue bloqueado; espera "
                    f"'{', '.join(sorted(proceso.espera_recursos))}'.",
                )
                continue
            if proceso.estado == Estado.BLOQUEADO:
                proceso.estado = Estado.LISTO
                proceso.recien_listo_tick = self._tick
                self._encolar(proceso.id, ORIGEN_BLOQUEADO)
                self.eventos.insert(
                    0,
                    f"{proceso.id} ({proceso.nombre}) se desbloqueó (recursos disponibles) → Listo.",
                )
            elif proceso.estado == Estado.BLOQUEADO_SUSPENDIDO:
                proceso.estado = Estado.LISTO_SUSPENDIDO
                self.eventos.insert(
                    0,
                    f"{proceso.id} ({proceso.nombre}) cambió a Listo Suspendido.",
                )

    def _hay_prioritario_en_cola(self):
        for pid in self._cola_listos:
            proceso = self._proceso(pid)
            if (
                proceso.estado == Estado.LISTO
                and proceso.prioritario
                and proceso.recien_listo_tick != self._tick
            ):
                return True
        return False

    def _preemptar_si_corresponde(self):
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
            f"{ejecutando.id} ({ejecutando.nombre}) desalojado por proceso Prioritario → Listo.",
        )

    def _despachar(self):
        self._preemptar_si_corresponde()
        if self._ejecutando is not None:
            return
        indice = 0
        while indice < len(self._cola_listos):
            pid = self._cola_listos[indice]
            proceso = self._proceso(pid)
            if proceso.estado != Estado.LISTO:
                self._cola_listos.pop(indice)
                continue

            # Un proceso que acaba de llegar a Listo desde Bloqueado/suspendido
            # en ESTE tick se detiene un ciclo visible en Listo; se saltará hasta
            # el próximo avanzar (cuando _tick ya sea mayor que su marca).
            if proceso.recien_listo_tick == self._tick:
                indice += 1
                continue

            recursos_requeridos = self._lista_recursos(proceso.recursos)
            if recursos_requeridos:
                faltantes = {}
                for recurso in recursos_requeridos:
                    disponible = self.recursos_disponibles.get(recurso, True)
                    propietario = self._recursos_ocupados.get(recurso)
                    if not disponible and propietario != pid:
                        faltantes[recurso] = propietario or "Sistema"
                if faltantes:
                    self._cola_listos.pop(indice)
                    self._bloquear_por_recurso(proceso, faltantes)
                    continue
                for recurso in recursos_requeridos:
                    self.recursos_disponibles[recurso] = False
                    self._recursos_ocupados[recurso] = pid

            self._cola_listos.pop(indice)
            proceso.estado = Estado.EJECUCION
            self._ejecutando = pid
            sufijo = (
                " [venía de Bloqueado → Listo]"
                if proceso.prioridad_cola == ORIGEN_BLOQUEADO
                else ""
            )
            self.eventos.insert(
                0,
                f"{pid} ({proceso.nombre}) entra a Ejecución "
                f"({proceso.hilos} hilo(s)).{sufijo}",
            )
            return

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

    def _liberar_recursos(self, pid):
        recursos_a_liberar = [
            rec for rec, propietario in self._recursos_ocupados.items() if propietario == pid
        ]
        for rec in recursos_a_liberar:
            del self._recursos_ocupados[rec]
            self.recursos_disponibles[rec] = True
            self.eventos.insert(0, f"Recurso '{rec}' liberado (Disponible=True) por {pid}.")
            self._desbloquear_espera(rec)

    def avanzar(self):
        self._tick += 1
        self._admitir_suspendidos_si_hay_ram()
        self._despachar()
        if self._ejecutando is None:
            return None
        self._instante += 1
        proceso = self._proceso(self._ejecutando)

        self._acceder_pagina_virtual(proceso)

        proceso.restantes -= 1
        pid_ejecutado = proceso.id
        self._ejecutando = None

        if proceso.restantes <= 0:
            proceso.restantes = 0
            proceso.estado = Estado.TERMINADO
            self._liberar_memoria_proceso(pid_ejecutado)
            self._liberar_bloque(self._bloques_swap, pid_ejecutado)
            self.eventos.insert(0, f"{pid_ejecutado} ({proceso.nombre}) terminó y liberó RAM y Swap.")
            self._liberar_recursos(pid_ejecutado)
            self._admitir_suspendidos_si_hay_ram()
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
                    self.recursos_disponibles[rec] = True
                proceso.estado = Estado.BLOQUEADO
                proceso.bloqueado_desde_instante = self._instante
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
                    f"{pid_ejecutado} ({proceso.nombre}) completó pasada ({proceso.restantes} restante(s)) → Listo.",
                )
        self._despachar()
        return proceso

    @property
    def proceso_ejecutando(self):
        if self._ejecutando is None:
            return None
        return self._proceso(self._ejecutando)

    @property
    def memoria_usada_mb(self):
        if self.modo_memoria == MODO_PAGINACION:
            ocupados = sum(1 for m in self._marcos if m is not None)
            return ocupados * self.tamano_marco_mb
        return sum(tam for _, tam, prop in self._particiones if prop is not None)

    @property
    def memoria_libre_mb(self):
        return max(0, self.memoria_mb - self.memoria_usada_mb)

    @property
    def grado_multiprogramacion(self):
        """Procesos residentes en memoria principal (control de carga).

        Son los procesos en Ejecución, Listo o Bloqueado; no cuentan los
        suspendidos (están en swap), ni Nuevo ni Terminado.
        """
        residentes = (Estado.EJECUCION, Estado.LISTO, Estado.BLOQUEADO)
        return sum(1 for p in self.procesos if p.estado in residentes)

    @property
    def max_multiprogramacion(self):
        """Máximo teórico de procesos en RAM. En paginación (asignación fija)
        cada proceso toma hasta 'marcos_fijos_por_proceso' marcos, así que caben
        total_marcos // marcos_fijos. En dinámico depende de los tamaños: None."""
        if self.modo_memoria == MODO_PAGINACION:
            return max(1, self.total_marcos // max(1, self.marcos_fijos_por_proceso))
        return None

    @property
    def fragmentacion_externa_mb(self):
        if self.modo_memoria != MODO_DINAMICO:
            return 0
        huecos = [tam for _, tam, prop in self._particiones if prop is None]
        return sum(huecos) if len(huecos) > 1 else 0

    @property
    def almacenamiento_usado_mb(self):
        return sum(tam for _, tam in self._bloques_swap)

    @property
    def almacenamiento_libre_mb(self):
        return max(0, self.almacenamiento_mb - self.almacenamiento_usado_mb)

    @property
    def swap_usado_mb(self):
        """MB de memoria virtual (swap) ocupados por el respaldo de procesos."""
        return self.almacenamiento_usado_mb

    @property
    def swap_libre_mb(self):
        """MB de swap disponibles. El respaldo de procesos se limita al swap
        (2× RAM), no al disco total."""
        return max(0, self.swap_mb - self.swap_usado_mb)

    def bloquear_ejecucion(self):
        if self._ejecutando is None:
            raise ValueError("No hay un proceso en ejecución para bloquear.")
        proceso = self._proceso(self._ejecutando)
        proceso.estado = Estado.BLOQUEADO
        proceso.bloqueado_desde_instante = self._instante
        self._ejecutando = None
        self.eventos.insert(0, f"{proceso.id} ({proceso.nombre}) bloqueado manualmente.")
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
        self.eventos.insert(0, f"{pid} ({proceso.nombre}) desbloqueado → Listo.")
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
            raise ValueError("Solo se pueden suspender procesos Listos o Bloqueados.")
        if pid in self._cola_listos:
            self._cola_listos.remove(pid)
        self._liberar_memoria_proceso(pid)
        self.eventos.insert(0, f"{pid} ({proceso.nombre}) vaciado a Disco ({estado_nuevo}) y liberó RAM.")
        self._despachar()

    def reanudar(self, pid):
        proceso = self._proceso(pid)
        if proceso.estado == Estado.LISTO_SUSPENDIDO:
            siguiente_estado = Estado.LISTO
        elif proceso.estado == Estado.BLOQUEADO_SUSPENDIDO:
            siguiente_estado = Estado.BLOQUEADO
        else:
            raise ValueError("Selecciona un proceso que esté suspendido para reanudarlo.")

        if not self._asignar_memoria_proceso(proceso):
            # Presión de RAM: intenta liberar suspendiendo Bloqueados residentes.
            necesario = self.tamano_marco_mb if self.modo_memoria == MODO_PAGINACION else proceso.tamano_mb
            if not (self._liberar_ram_suspendiendo(necesario) and self._asignar_memoria_proceso(proceso)):
                raise ValueError(
                    f"RAM insuficiente o fragmentada para cargar {pid} ({proceso.tamano_mb} MB) desde Memoria Virtual."
                )

        proceso.estado = siguiente_estado
        if siguiente_estado == Estado.LISTO:
            proceso.recien_listo_tick = self._tick
            self._instante += 1
            self._encolar(pid, ORIGEN_BLOQUEADO)
            self._despachar()
        self.eventos.insert(
            0, f"{pid} ({proceso.nombre}) cargado desde Swap a RAM como {siguiente_estado.value}."
        )

    def configurar_memoria(self, memoria_mb, almacenamiento_mb, modo_memoria, marcos_fijos):
        self._validar_capacidad(memoria_mb, "memoria")
        self._validar_capacidad(almacenamiento_mb, "almacenamiento")
        activos = [p for p in self.procesos if p.estado != Estado.TERMINADO]
        if activos:
            raise ValueError(
                "Presiona 'Limpiar todo' o espera a que terminen los procesos activos antes de cambiar la memoria."
            )
        nuevo_swap = self._calcular_swap(memoria_mb, almacenamiento_mb)
        self.memoria_mb = memoria_mb
        self.almacenamiento_mb = almacenamiento_mb
        self.swap_mb = nuevo_swap
        self.modo_memoria = modo_memoria
        self.marcos_fijos_por_proceso = marcos_fijos
        self._inicializar_memoria()
        self.eventos.insert(
            0,
            f"Configuración aplicada: {modo_memoria} | RAM {memoria_mb} MB | "
            f"Swap (2× RAM) {nuevo_swap} MB | Disco {almacenamiento_mb} MB | "
            f"Política fija: {marcos_fijos} marcos/proceso | Reemplazo: FIFO.",
        )

    def reiniciar_procesos(self):
        """Vuelve a cargar todos los procesos creados a su estado inicial para repetir la prueba."""
        if not self.procesos:
            raise ValueError("No hay procesos creados para volver a ejecutar.")

        total_requerido = sum(p.tamano_mb for p in self.procesos)
        if total_requerido > self.swap_mb:
            raise ValueError(
                f"La memoria virtual (swap = 2× RAM = {self.swap_mb} MB) no alcanza para "
                f"respaldar todos los procesos ({total_requerido} MB)."
            )

        self._bloques_swap = []
        self._cola_listos = []
        self._ejecutando = None
        self._recursos_ocupados = {}
        self.recursos_disponibles = {rec: True for rec in RECURSOS_SISTEMA}
        self.total_fallos_pagina = 0
        self._tick = 0
        self._inicializar_memoria()

        for proceso in self.procesos:
            proceso.restantes = proceso.pasadas_cpu
            proceso.espera_recursos = set()
            proceso.tabla_paginas = {}
            proceso.orden_fifo_paginas = []
            proceso.pagina_actual = 0
            proceso.fallos_pagina = 0
            proceso.paginas_modificadas = set()
            proceso.particion_ram = None
            proceso.total_paginas = self._paginas_requeridas(proceso.tamano_mb)
            proceso.recien_listo_tick = -1
            proceso.bloqueado_desde_instante = -1

            self._bloques_swap.append((proceso.id, proceso.tamano_mb))
            self._instante += 1

            if self._asignar_memoria_proceso(proceso):
                proceso.estado = Estado.LISTO
                self._encolar(proceso.id, ORIGEN_NUEVO)
            else:
                proceso.estado = Estado.LISTO_SUSPENDIDO

        self.eventos.insert(
            0, f"🔄 Todos los procesos fueron reiniciados bajo '{self.modo_memoria}' (FIFO)."
        )
        self._despachar()

    def limpiar_simulacion(self):
        self.procesos = []
        self._bloques_swap = []
        self._cola_listos = []
        self._ejecutando = None
        self._recursos_ocupados = {}
        self.recursos_disponibles = {rec: True for rec in RECURSOS_SISTEMA}
        self._siguiente_id = 1
        self._instante = 0
        self._tick = 0
        self.total_fallos_pagina = 0
        self._inicializar_memoria()
        self.eventos = [f"Simulación reiniciada ({self.modo_memoria} · FIFO)."]

    @staticmethod
    def _liberar_bloque(lista_bloques, pid):
        lista_bloques[:] = [(p, tam) for p, tam in lista_bloques if p != pid]

    def tabla_marcos_memoria(self):
        filas = []
        for idx, contenido in enumerate(self._marcos):
            inicio_mb = idx * self.tamano_marco_mb
            fin_mb = inicio_mb + self.tamano_marco_mb - 1
            pid, pagina = contenido if contenido is not None else (None, None)
            filas.append((idx, inicio_mb, fin_mb, pid, pagina))
        return filas

    def segmentos_particiones_dinamicas(self):
        return [(ini, ini + tam - 1, tam, prop) for ini, tam, prop in self._particiones]

    def tabla_memoria_virtual(self):
        filas = []
        for p in self.procesos:
            if p.estado == Estado.TERMINADO:
                continue
            if self.modo_memoria == MODO_PAGINACION:
                for pag in range(p.total_paginas):
                    en_ram = pag in p.tabla_paginas
                    marco = p.tabla_paginas.get(pag)
                    modificada = "1 (Sí)" if pag in p.paginas_modificadas else "0 (No)"
                    if en_ram:
                        pos_fifo = p.orden_fifo_paginas.index(pag) + 1
                        sufijo = " · Próxima víctima" if pos_fifo == 1 else ""
                        detalle_fifo = f"Marco #{marco} (Cola FIFO: #{pos_fifo}{sufijo})"
                    else:
                        detalle_fifo = "Memoria Secundaria (Disco)"
                    filas.append((
                        f"{p.id} · {p.nombre}",
                        f"Página {pag}",
                        "1 (En RAM)" if en_ram else "0 (En Swap)",
                        modificada,
                        detalle_fifo,
                    ))
            else:
                en_ram = p.particion_ram is not None
                ubicacion = f"RAM {p.particion_ram[0]}–{p.particion_ram[1]} MB" if en_ram else "Swap (Disco)"
                filas.append((
                    f"{p.id} · {p.nombre}",
                    f"Segmento ({p.tamano_mb} MB)",
                    "1 (En RAM)" if en_ram else "0 (En Swap)",
                    "—",
                    ubicacion,
                ))
        return filas

    def segmentos_almacenamiento(self):
        segmentos = []
        cursor = 0
        for pid, tam in self._bloques_swap:
            segmentos.append((cursor, cursor + tam - 1, pid))
            cursor += tam
        if cursor < self.almacenamiento_mb:
            segmentos.append((cursor, self.almacenamiento_mb - 1, None))
        return segmentos