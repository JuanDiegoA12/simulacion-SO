import math
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


class Simulador:
    """Motor de procesos con Paginación (Política Fija + FIFO), Particiones Dinámicas y Memoria Virtual."""

    def __init__(
        self,
        memoria_mb=64,
        almacenamiento_mb=128,
        modo_memoria=MODO_PAGINACION,
        marcos_fijos_por_proceso=3,
    ):
        self._validar_capacidad(memoria_mb, "memoria")
        self._validar_capacidad(almacenamiento_mb, "almacenamiento")
        self.memoria_mb = memoria_mb
        self.almacenamiento_mb = almacenamiento_mb
        self.modo_memoria = modo_memoria
        self.marcos_fijos_por_proceso = marcos_fijos_por_proceso

        self.procesos = []
        self._bloques_swap = []
        self._cola_listos = []
        self._ejecutando = None
        self._siguiente_id = 1
        self._instante = 0
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

    def _admitir_suspendidos_si_hay_ram(self):
        """Planificador a mediano plazo: carga procesos de Listo suspendido cuando se libera RAM."""
        for proceso in self.procesos:
            if proceso.estado == Estado.LISTO_SUSPENDIDO:
                if self._asignar_memoria_proceso(proceso):
                    proceso.estado = Estado.LISTO
                    self._instante += 1
                    self._encolar(proceso.id, ORIGEN_BLOQUEADO)
                    self.eventos.insert(
                        0,
                        f"[Swap-In] {proceso.id} ({proceso.nombre}) cargado automáticamente de Disco → Listo.",
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

        if tamano_mb > self.almacenamiento_libre_mb:
            raise ValueError(
                f"Memoria Virtual (Disco) insuficiente: {self.almacenamiento_libre_mb} MB libres "
                f"para respaldar este proceso de {tamano_mb} MB."
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

        if self._asignar_memoria_proceso(proceso):
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
        proceso.estado = Estado.BLOQUEADO
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
            if proceso.estado == Estado.LISTO and proceso.prioritario:
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
                    disponible = self.recursos_disponibles.get(recurso, True)
                    propietario = self._recursos_ocupados.get(recurso)
                    if not disponible and propietario != pid:
                        faltantes[recurso] = propietario or "Sistema"
                if faltantes:
                    self._cola_listos.pop(0)
                    self._bloquear_por_recurso(proceso, faltantes)
                    continue
                for recurso in recursos_requeridos:
                    self.recursos_disponibles[recurso] = False
                    self._recursos_ocupados[recurso] = pid

            self._cola_listos.pop(0)
            proceso.estado = Estado.EJECUCION
            self._ejecutando = pid
            self.eventos.insert(
                0, f"{pid} ({proceso.nombre}) entra a Ejecución ({proceso.hilos} hilo(s))."
            )
            return

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

    def bloquear_ejecucion(self):
        if self._ejecutando is None:
            raise ValueError("No hay un proceso en ejecución para bloquear.")
        proceso = self._proceso(self._ejecutando)
        proceso.estado = Estado.BLOQUEADO
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
            raise ValueError(
                f"RAM insuficiente o fragmentada para cargar {pid} ({proceso.tamano_mb} MB) desde Memoria Virtual."
            )

        proceso.estado = siguiente_estado
        if siguiente_estado == Estado.LISTO:
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
        self.memoria_mb = memoria_mb
        self.almacenamiento_mb = almacenamiento_mb
        self.modo_memoria = modo_memoria
        self.marcos_fijos_por_proceso = marcos_fijos
        self._inicializar_memoria()
        self.eventos.insert(
            0,
            f"Configuración aplicada: {modo_memoria} | RAM {memoria_mb} MB | Disco {almacenamiento_mb} MB | "
            f"Política fija: {marcos_fijos} marcos/proceso | Reemplazo: FIFO.",
        )

    def reiniciar_procesos(self):
        """Vuelve a cargar todos los procesos creados a su estado inicial para repetir la prueba."""
        if not self.procesos:
            raise ValueError("No hay procesos creados para volver a ejecutar.")

        total_requerido = sum(p.tamano_mb for p in self.procesos)
        if total_requerido > self.almacenamiento_mb:
            raise ValueError(
                f"El almacenamiento actual ({self.almacenamiento_mb} MB) no alcanza para respaldar "
                f"todos los procesos ({total_requerido} MB)."
            )

        self._bloques_swap = []
        self._cola_listos = []
        self._ejecutando = None
        self._recursos_ocupados = {}
        self.recursos_disponibles = {rec: True for rec in RECURSOS_SISTEMA}
        self.total_fallos_pagina = 0
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