import math
import sys

try:
    import tkinter as tk
    from tkinter import messagebox, ttk
except ModuleNotFoundError as error:
    if error.name == "tkinter":
        print(
            "No se encontró Tkinter. Instálalo para tu versión de Python "
            "(por ejemplo, en Debian/Ubuntu: sudo apt install python3-tk).",
            file=sys.stderr,
        )
        raise SystemExit(1) from error
    raise

from simulador import ESTADOS, Estado, Simulador


FONDO = "#f3f4f6"
BLANCO = "#ffffff"
TINTA = "#171717"
GRIS = "#dedede"
GRIS_OSCURO = "#5a5a5a"
ACENTO = "#111111"


class Aplicacion(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Simulador de procesos · Modelo de 7 estados")
        self.geometry("1180x780")
        self.minsize(980, 680)
        self.configure(bg=FONDO)

        self.simulador = Simulador()
        self.ejecutando = True
        self.after_id = None
        self.intervalo_var = tk.StringVar(value="1")
        self.memoria_var = tk.StringVar(value="64")
        self.almacenamiento_var = tk.StringVar(value="128")
        self.estado_cpu_var = tk.StringVar(value="CPU activa")
        self.cpu_actual_var = tk.StringVar(value="Sin proceso en ejecución")
        self.form_vars = {
            "nombre": tk.StringVar(),
            "tamano": tk.StringVar(value="4"),
            "recursos": tk.StringVar(value="Ninguno"),
            "prioridad": tk.StringVar(value="1"),
            "pasadas": tk.StringVar(value="3"),
        }
        self._configurar_estilos()
        self._construir_interfaz()
        self.intervalo_var.trace_add("write", lambda *_: self._programar_reloj())
        self._refrescar()
        self._programar_reloj()
        self.protocol("WM_DELETE_WINDOW", self._cerrar)

    def _configurar_estilos(self):
        estilo = ttk.Style(self)
        estilo.theme_use("clam")
        estilo.configure("TFrame", background=FONDO)
        estilo.configure("Card.TFrame", background=BLANCO)
        estilo.configure("TLabel", background=FONDO, foreground=TINTA, font=("TkDefaultFont", 10))
        estilo.configure("Card.TLabel", background=BLANCO, foreground=TINTA, font=("TkDefaultFont", 10))
        estilo.configure("Title.TLabel", background=FONDO, foreground=TINTA, font=("TkDefaultFont", 23, "bold"))
        estilo.configure("Section.TLabel", background=BLANCO, foreground=TINTA, font=("TkDefaultFont", 12, "bold"))
        estilo.configure("Muted.TLabel", background=BLANCO, foreground=GRIS_OSCURO, font=("TkDefaultFont", 9))
        estilo.configure("TNotebook", background=FONDO, borderwidth=0)
        estilo.configure("TNotebook.Tab", padding=(18, 11), font=("TkDefaultFont", 10))
        estilo.map("TNotebook.Tab", background=[("selected", BLANCO)], foreground=[("selected", TINTA)])
        estilo.configure("Treeview", rowheight=30, font=("TkDefaultFont", 10), background=BLANCO, fieldbackground=BLANCO)
        estilo.configure("Treeview.Heading", font=("TkDefaultFont", 10, "bold"), background=GRIS, foreground=TINTA, padding=8)
        estilo.map("Treeview", background=[("selected", "#c8c8c8")], foreground=[("selected", TINTA)])
        estilo.configure("Black.TButton", background=ACENTO, foreground=BLANCO, padding=(12, 8), font=("TkDefaultFont", 10, "bold"))
        estilo.map("Black.TButton", background=[("active", "#333333")])
        estilo.configure("TButton", padding=(10, 7))

    def _construir_interfaz(self):
        encabezado = ttk.Frame(self, padding=(22, 16, 22, 8))
        encabezado.pack(fill="x")
        ttk.Label(encabezado, text="Simulador de procesos", style="Title.TLabel").pack(side="left")
        ttk.Button(
            encabezado,
            text="+ Crear proceso",
            style="Black.TButton",
            command=self._abrir_creacion_proceso,
        ).pack(side="right", padx=(12, 0))
        ttk.Label(
            encabezado,
            text="Planificación por orden de llegada",
            foreground=GRIS_OSCURO,
        ).pack(side="right", anchor="s", pady=8)

        configuracion = ttk.Frame(self, padding=(22, 2, 22, 12))
        configuracion.pack(fill="x")
        self._campo_config(configuracion, "Memoria (MB)", self.memoria_var, 10)
        self._campo_config(configuracion, "Almacenamiento (MB)", self.almacenamiento_var, 16)
        self._campo_config(configuracion, "Tiempo por pasada (s)", self.intervalo_var, 17)
        ttk.Button(configuracion, text="Aplicar capacidades", command=self._aplicar_capacidades).pack(side="left", padx=(16, 0), pady=(15, 0))
        self.cpu_toggle_button = ttk.Button(configuracion, text="⏸ Pausar", command=self._alternar_cpu)
        self.cpu_toggle_button.pack(side="right", padx=(8, 0), pady=(15, 0))
        ttk.Button(configuracion, text="▶ Paso CPU", command=self._paso_manual).pack(side="right", pady=(15, 0))
        ttk.Label(configuracion, textvariable=self.estado_cpu_var).pack(side="right", padx=12, pady=(15, 0))

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=22, pady=(0, 20))
        self.pestana_procesos = ttk.Frame(self.notebook, padding=18)
        self.pestana_memoria = ttk.Frame(self.notebook, padding=18)
        self.pestana_almacenamiento = ttk.Frame(self.notebook, padding=18)
        self.pestana_estados = ttk.Frame(self.notebook, padding=18)
        self.notebook.add(self.pestana_procesos, text="Programas / Procesos")
        self.notebook.add(self.pestana_memoria, text="Memoria")
        self.notebook.add(self.pestana_almacenamiento, text="Almacenamiento")
        self.notebook.add(self.pestana_estados, text="Modelo de 7 estados")
        self._construir_pestana_procesos()
        self._construir_pestana_memoria()
        self._construir_pestana_almacenamiento()
        self._construir_pestana_estados()

    @staticmethod
    def _campo_config(parent, etiqueta, variable, ancho):
        caja = ttk.Frame(parent)
        caja.pack(side="left", padx=(0, 14))
        ttk.Label(caja, text=etiqueta).pack(anchor="w")
        ttk.Entry(caja, textvariable=variable, width=ancho).pack(anchor="w", pady=(4, 0))

    def _construir_pestana_procesos(self):
        self.pestana_procesos.columnconfigure(0, weight=0, minsize=270)
        self.pestana_procesos.columnconfigure(1, weight=1)
        self.pestana_procesos.rowconfigure(1, weight=1)
        ttk.Label(self.pestana_procesos, text="Crear un proceso", style="Title.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 15)
        )
        formulario = ttk.Frame(self.pestana_procesos, style="Card.TFrame", padding=18)
        formulario.grid(row=1, column=0, sticky="nsew", padx=(0, 16))
        for clave, etiqueta in (
            ("nombre", "Nombre"),
            ("tamano", "Tamaño (MB)"),
            ("recursos", "Recursos requeridos"),
            ("prioridad", "Prioridad"),
            ("pasadas", "Pasadas por CPU"),
        ):
            ttk.Label(formulario, text=etiqueta, style="Card.TLabel").pack(anchor="w", pady=(7, 3))
            entrada = ttk.Entry(formulario, textvariable=self.form_vars[clave])
            entrada.pack(fill="x", pady=(0, 6))
            if clave == "nombre":
                self.nombre_entry = entrada
        ttk.Label(
            formulario,
            text="La prioridad se registra para consulta; esta versión planifica estrictamente por orden de llegada.",
            style="Muted.TLabel",
            wraplength=230,
        ).pack(anchor="w", pady=(8, 12))
        ttk.Button(
            formulario,
            text="＋  CREAR PROCESO",
            style="Black.TButton",
            command=self._crear_proceso,
        ).pack(fill="x", ipady=5, pady=(4, 0))

        lista = ttk.Frame(self.pestana_procesos, style="Card.TFrame", padding=14)
        lista.grid(row=1, column=1, sticky="nsew")
        lista.rowconfigure(1, weight=1)
        lista.columnconfigure(0, weight=1)
        barra = ttk.Frame(lista, style="Card.TFrame")
        barra.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        ttk.Label(barra, text="Procesos", style="Section.TLabel").pack(side="left")
        ttk.Label(barra, textvariable=self.cpu_actual_var, style="Muted.TLabel").pack(side="right")
        columnas = ("id", "nombre", "tamano", "recursos", "prioridad", "pasadas", "restantes", "estado")
        self.tabla_procesos = self._crear_tabla(lista, columnas, {
            "id": ("ID", 65), "nombre": ("Nombre", 130), "tamano": ("MB", 55),
            "recursos": ("Recursos", 130), "prioridad": ("Prioridad", 70),
            "pasadas": ("Pasadas CPU", 85), "restantes": ("Restantes", 75),
            "estado": ("Estado", 150),
        })
        self.tabla_procesos.grid(row=1, column=0, sticky="nsew")
        acciones = ttk.Frame(lista, style="Card.TFrame")
        acciones.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        ttk.Button(acciones, text="Bloquear proceso en CPU", command=self._bloquear).pack(side="left", padx=(0, 8))
        ttk.Button(acciones, text="Desbloquear seleccionado", command=self._desbloquear).pack(side="left", padx=(0, 8))
        ttk.Button(acciones, text="Suspender seleccionado", command=self._suspender).pack(side="left", padx=(0, 8))
        ttk.Button(acciones, text="Reanudar seleccionado", command=self._reanudar).pack(side="left")

    def _construir_pestana_memoria(self):
        self.pestana_memoria.columnconfigure(0, weight=1)
        self.pestana_memoria.rowconfigure(2, weight=1)
        ttk.Label(self.pestana_memoria, text="Memoria", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        self.resumen_memoria = ttk.Label(self.pestana_memoria, text="", font=("TkDefaultFont", 11))
        self.resumen_memoria.grid(row=1, column=0, sticky="w", pady=(5, 14))
        panel = ttk.Frame(self.pestana_memoria, style="Card.TFrame", padding=12)
        panel.grid(row=2, column=0, sticky="nsew")
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(0, weight=1)
        columnas = ("inicio", "fin", "tamano", "proceso", "estado")
        self.tabla_memoria = self._crear_tabla(panel, columnas, {
            "inicio": ("Dirección inicial", 150), "fin": ("Dirección final", 150),
            "tamano": ("Tamaño (MB)", 100), "proceso": ("Proceso", 180),
            "estado": ("Estado", 190),
        })
        self.tabla_memoria.grid(row=0, column=0, sticky="nsew")

    def _construir_pestana_almacenamiento(self):
        self.pestana_almacenamiento.columnconfigure(0, weight=1)
        self.pestana_almacenamiento.rowconfigure(2, weight=1)
        ttk.Label(self.pestana_almacenamiento, text="Almacenamiento", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        self.resumen_almacenamiento = ttk.Label(self.pestana_almacenamiento, text="", font=("TkDefaultFont", 11))
        self.resumen_almacenamiento.grid(row=1, column=0, sticky="w", pady=(5, 14))
        panel = ttk.Frame(self.pestana_almacenamiento, style="Card.TFrame", padding=12)
        panel.grid(row=2, column=0, sticky="nsew")
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(0, weight=1)
        columnas = ("bloque", "proceso", "estado", "recursos")
        self.tabla_almacenamiento = self._crear_tabla(panel, columnas, {
            "bloque": ("Bloques / direcciones", 240), "proceso": ("Proceso", 180),
            "estado": ("Estado", 210), "recursos": ("Recursos", 220),
        })
        self.tabla_almacenamiento.grid(row=0, column=0, sticky="nsew")

    def _construir_pestana_estados(self):
        self.pestana_estados.columnconfigure(0, weight=1)
        self.pestana_estados.rowconfigure(2, weight=1)
        ttk.Label(self.pestana_estados, text="Modelo de 7 estados", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            self.pestana_estados,
            text="Las transiciones manuales permiten explorar bloqueo y suspensión; la CPU atiende los procesos por orden de llegada.",
            wraplength=980,
        ).grid(row=1, column=0, sticky="w", pady=(4, 10))
        cuerpo = ttk.Frame(self.pestana_estados)
        cuerpo.grid(row=2, column=0, sticky="nsew")
        cuerpo.columnconfigure(0, weight=3)
        cuerpo.columnconfigure(1, weight=2)
        cuerpo.rowconfigure(0, weight=1)
        self.diagrama = tk.Canvas(cuerpo, background=BLANCO, highlightthickness=0, height=390)
        self.diagrama.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        log_panel = ttk.Frame(cuerpo, style="Card.TFrame", padding=12)
        log_panel.grid(row=0, column=1, sticky="nsew")
        log_panel.rowconfigure(1, weight=1)
        log_panel.columnconfigure(0, weight=1)
        ttk.Label(log_panel, text="Registro de eventos", style="Section.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 8))
        self.lista_eventos = tk.Listbox(log_panel, font=("TkDefaultFont", 10), background=BLANCO, foreground=TINTA, relief="flat", activestyle="none")
        self.lista_eventos.grid(row=1, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(log_panel, orient="vertical", command=self.lista_eventos.yview)
        scrollbar.grid(row=1, column=1, sticky="ns")
        self.lista_eventos.configure(yscrollcommand=scrollbar.set)
        self._dibujar_diagrama()

    @staticmethod
    def _crear_tabla(parent, columnas, configuracion):
        tabla = ttk.Treeview(parent, columns=columnas, show="headings", selectmode="browse")
        for columna in columnas:
            titulo, ancho = configuracion[columna]
            tabla.heading(columna, text=titulo)
            tabla.column(columna, width=ancho, minwidth=55, anchor="w", stretch=True)
        scroll_y = ttk.Scrollbar(parent, orient="vertical", command=tabla.yview)
        scroll_x = ttk.Scrollbar(parent, orient="horizontal", command=tabla.xview)
        tabla.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        tabla._scroll_y = scroll_y
        tabla._scroll_x = scroll_x
        tabla.bind("<Configure>", lambda _evento: (
            scroll_y.place(relx=1, rely=0, relheight=1, anchor="ne"),
            scroll_x.place(relx=0, rely=1, relwidth=1, anchor="sw"),
        ))
        return tabla

    def _crear_proceso(self):
        self._guardar_proceso(
            self.form_vars["nombre"].get(),
            self.form_vars["tamano"].get(),
            self.form_vars["recursos"].get(),
            self.form_vars["prioridad"].get(),
            self.form_vars["pasadas"].get(),
            self,
        )

    def _guardar_proceso(self, nombre, tamano, recursos, prioridad, pasadas, ventana):
        try:
            proceso = self.simulador.crear_proceso(
                nombre,
                int(tamano),
                recursos,
                int(prioridad),
                int(pasadas),
            )
        except ValueError as error:
            messagebox.showerror("No se pudo crear el proceso", str(error), parent=ventana)
            return False
        if ventana == self:
            self.form_vars["nombre"].set("")
        else:
            ventana.destroy()
        self._refrescar()
        self.notebook.select(self.pestana_procesos)
        self.tabla_procesos.selection_set(proceso.id)
        self.tabla_procesos.see(proceso.id)
        return True

    def _abrir_creacion_proceso(self):
        ventana = tk.Toplevel(self)
        ventana.title("Crear proceso")
        ventana.transient(self)
        ventana.resizable(False, False)
        ventana.configure(bg=FONDO)
        ventana.grab_set()
        contenido = ttk.Frame(ventana, padding=20)
        contenido.pack(fill="both", expand=True)
        ttk.Label(contenido, text="Crear un proceso", style="Title.TLabel").pack(
            anchor="w", pady=(0, 8)
        )
        ttk.Label(
            contenido,
            text="Completa los datos y pulsa el botón para agregarlo a la tabla.",
            wraplength=320,
        ).pack(anchor="w", pady=(0, 12))

        variables = {
            "nombre": tk.StringVar(),
            "tamano": tk.StringVar(value="4"),
            "recursos": tk.StringVar(value="Ninguno"),
            "prioridad": tk.StringVar(value="1"),
            "pasadas": tk.StringVar(value="3"),
        }
        for clave, etiqueta in (
            ("nombre", "Nombre"),
            ("tamano", "Tamaño (MB)"),
            ("recursos", "Recursos requeridos"),
            ("prioridad", "Prioridad"),
            ("pasadas", "Pasadas por CPU"),
        ):
            ttk.Label(contenido, text=etiqueta).pack(anchor="w", pady=(6, 2))
            entrada = ttk.Entry(contenido, textvariable=variables[clave], width=38)
            entrada.pack(fill="x")
            if clave == "nombre":
                entrada.focus_set()

        ttk.Button(
            contenido,
            text="＋  CREAR PROCESO Y AGREGAR A LA TABLA",
            style="Black.TButton",
            command=lambda: self._guardar_proceso(
                variables["nombre"].get(),
                variables["tamano"].get(),
                variables["recursos"].get(),
                variables["prioridad"].get(),
                variables["pasadas"].get(),
                ventana,
            ),
        ).pack(fill="x", ipady=5, pady=(18, 0))
        ventana.bind(
            "<Return>",
            lambda _evento: self._guardar_proceso(
                variables["nombre"].get(),
                variables["tamano"].get(),
                variables["recursos"].get(),
                variables["prioridad"].get(),
                variables["pasadas"].get(),
                ventana,
            ),
        )
        ventana.update_idletasks()
        ventana.geometry(
            f"+{self.winfo_rootx() + (self.winfo_width() - ventana.winfo_width()) // 2}"
            f"+{self.winfo_rooty() + (self.winfo_height() - ventana.winfo_height()) // 2}"
        )

    def _aplicar_capacidades(self):
        try:
            memoria = int(self.memoria_var.get())
            almacenamiento = int(self.almacenamiento_var.get())
            self.simulador.cambiar_capacidades(memoria, almacenamiento)
        except ValueError as error:
            messagebox.showerror("Capacidad no válida", str(error), parent=self)
            return
        self._refrescar()

    def _alternar_cpu(self):
        self.ejecutando = not self.ejecutando
        self.estado_cpu_var.set("CPU activa" if self.ejecutando else "CPU pausada")
        self.cpu_toggle_button.configure(
            text="⏸ Pausar" if self.ejecutando else "▶ Reanudar"
        )
        self._programar_reloj()

    def _programar_reloj(self):
        if self.after_id is not None:
            self.after_cancel(self.after_id)
            self.after_id = None
        if self.ejecutando:
            try:
                segundos = float(self.intervalo_var.get())
                if not math.isfinite(segundos) or segundos <= 0:
                    raise ValueError
            except ValueError:
                self.estado_cpu_var.set("Intervalo no válido")
                return
            self.after_id = self.after(max(1, int(segundos * 1000)), self._avanzar_cpu)

    def _avanzar_cpu(self):
        self.after_id = None
        self.simulador.avanzar()
        self._refrescar()
        self._programar_reloj()

    def _paso_manual(self):
        self.simulador.avanzar()
        self._refrescar()

    def _pid_seleccionado(self):
        seleccion = self.tabla_procesos.selection()
        if not seleccion:
            raise ValueError("Selecciona un proceso de la tabla.")
        return seleccion[0]

    def _ejecutar_accion(self, accion):
        try:
            accion(self._pid_seleccionado())
        except ValueError as error:
            messagebox.showinfo("Acción no disponible", str(error), parent=self)
            return
        self._refrescar()

    def _bloquear(self):
        try:
            self.simulador.bloquear_ejecucion()
        except ValueError as error:
            messagebox.showinfo("Acción no disponible", str(error), parent=self)
            return
        self._refrescar()

    def _desbloquear(self):
        self._ejecutar_accion(self.simulador.desbloquear)

    def _suspender(self):
        self._ejecutar_accion(self.simulador.suspender)

    def _reanudar(self):
        self._ejecutar_accion(self.simulador.reanudar)

    def _refrescar(self):
        procesos = self.simulador.procesos
        self._reemplazar_filas(
            self.tabla_procesos,
            [
                (
                    p.id, p.nombre, p.tamano_mb, p.recursos, p.prioridad,
                    p.pasadas_cpu, p.restantes, p.estado.value,
                )
                for p in procesos
            ],
        )
        actual = self.simulador.proceso_ejecutando
        self.cpu_actual_var.set(
            f"En CPU: {actual.id} · {actual.nombre}"
            if actual
            else "Sin proceso en ejecución"
        )

        self.resumen_memoria.configure(
            text=f"{self.simulador.memoria_mb} MB totales · "
            f"{self.simulador.memoria_libre_mb} MB libres"
        )
        filas_memoria = []
        mapa_procesos = {p.id: p for p in procesos}
        for inicio, fin, pid in self.simulador.segmentos_memoria():
            proceso = mapa_procesos.get(pid) if pid else None
            filas_memoria.append(
                (
                    f"0x{inicio * 1048576:08X}",
                    f"0x{(fin + 1) * 1048576 - 1:08X}",
                    fin - inicio + 1,
                    f"{pid} · {proceso.nombre}" if proceso else "Libre",
                    proceso.estado.value if proceso else "—",
                )
            )
        self._reemplazar_filas(self.tabla_memoria, filas_memoria)

        self.resumen_almacenamiento.configure(
            text=f"{self.simulador.almacenamiento_mb} MB totales · "
            f"{self.simulador.almacenamiento_libre_mb} MB libres"
        )
        filas_almacenamiento = []
        for inicio, fin, pid in self.simulador.segmentos_almacenamiento():
            proceso = mapa_procesos.get(pid) if pid else None
            filas_almacenamiento.append(
                (
                    f"{inicio}–{fin}" if inicio != fin else str(inicio),
                    f"{pid} · {proceso.nombre}" if proceso else "Libre",
                    proceso.estado.value if proceso else "—",
                    proceso.recursos if proceso else "—",
                )
            )
        self._reemplazar_filas(self.tabla_almacenamiento, filas_almacenamiento)

        self.lista_eventos.delete(0, tk.END)
        for evento in self.simulador.eventos[:100]:
            self.lista_eventos.insert(tk.END, evento)
        self._dibujar_diagrama()

    @staticmethod
    def _reemplazar_filas(tabla, filas):
        seleccion = tabla.selection()
        for item in tabla.get_children():
            tabla.delete(item)
        for fila in filas:
            identificador = fila[0] if tabla is not None and tabla["columns"][0] == "id" else None
            if identificador:
                tabla.insert("", "end", iid=identificador, values=fila)
            else:
                tabla.insert("", "end", values=fila)
        for item in seleccion:
            if tabla.exists(item):
                tabla.selection_set(item)

    def _dibujar_diagrama(self):
        canvas = self.diagrama
        canvas.delete("all")
        ancho = max(canvas.winfo_width(), 640)
        alto = max(canvas.winfo_height(), 350)
        posiciones = {
            "Nuevo": (0.14, 0.20),
            Estado.LISTO_SUSPENDIDO.value: (0.15, 0.48),
            Estado.LISTO.value: (0.43, 0.48),
            Estado.EJECUCION.value: (0.70, 0.48),
            Estado.TERMINADO.value: (0.88, 0.48),
            Estado.BLOQUEADO_SUSPENDIDO.value: (0.15, 0.78),
            Estado.BLOQUEADO.value: (0.43, 0.78),
        }
        nodos = {}
        for estado in ESTADOS:
            x, y = posiciones[estado]
            cx, cy = ancho * x, alto * y
            radio_x, radio_y = (78, 30) if len(estado) < 15 else (92, 32)
            nodos[estado] = (cx, cy, radio_x, radio_y)

        transiciones = (
            ("Nuevo", Estado.LISTO.value),
            ("Nuevo", Estado.LISTO_SUSPENDIDO.value),
            (Estado.LISTO_SUSPENDIDO.value, Estado.LISTO.value),
            (Estado.LISTO.value, Estado.EJECUCION.value),
            (Estado.EJECUCION.value, Estado.LISTO.value),
            (Estado.EJECUCION.value, Estado.TERMINADO.value),
            (Estado.EJECUCION.value, Estado.BLOQUEADO.value),
            (Estado.BLOQUEADO.value, Estado.LISTO.value),
            (Estado.BLOQUEADO.value, Estado.BLOQUEADO_SUSPENDIDO.value),
            (Estado.BLOQUEADO_SUSPENDIDO.value, Estado.BLOQUEADO.value),
        )
        for origen, destino in transiciones:
            x1, y1, rx1, ry1 = nodos[origen]
            x2, y2, rx2, ry2 = nodos[destino]
            dx, dy = x2 - x1, y2 - y1
            distancia = max((dx * dx + dy * dy) ** 0.5, 1)
            start = (x1 + dx / distancia * (rx1 - 4), y1 + dy / distancia * (ry1 - 4))
            end = (x2 - dx / distancia * (rx2 + 4), y2 - dy / distancia * (ry2 + 4))
            canvas.create_line(*start, *end, fill=TINTA, width=2, arrow=tk.LAST)

        conteos = {estado: 0 for estado in ESTADOS}
        for proceso in self.simulador.procesos:
            conteos[proceso.estado.value] += 1
        conteos["Nuevo"] = 0
        for estado, (cx, cy, rx, ry) in nodos.items():
            conteo = conteos[estado]
            relleno = TINTA if conteo else GRIS
            texto = BLANCO if conteo else TINTA
            canvas.create_oval(
                cx - rx, cy - ry, cx + rx, cy + ry,
                fill=relleno, outline=TINTA, width=2,
            )
            etiqueta = f"{estado}\n{conteo} proceso" + ("" if conteo == 1 else "s")
            canvas.create_text(
                cx, cy, text=etiqueta, fill=texto, width=rx * 1.8,
                font=("TkDefaultFont", 10, "bold"),
            )

    def _cerrar(self):
        if self.after_id is not None:
            self.after_cancel(self.after_id)
        self.destroy()


if __name__ == "__main__":
    Aplicacion().mainloop()
