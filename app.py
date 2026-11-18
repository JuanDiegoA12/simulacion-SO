import math
import re
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

from simulador import (
    ESTADOS,
    MODO_DINAMICO,
    MODO_PAGINACION,
    MODOS_MEMORIA,
    RECURSOS_SISTEMA,
    Estado,
    Simulador,
)


# Paleta de colores vivos
FONDO = "#eef2ff"             # Lavanda suave de fondo
HEADER_BG = "#1e1b4b"         # Índigo profundo para barra superior
BLANCO = "#ffffff"
BORDE = "#a5b4fc"             # Borde índigo claro
TINTA = "#1e1b4b"
TEXTO_SEC = "#4338ca"
GRIS_OSCURO = "#475569"

INDIGO = "#4f46e5"
INDIGO_HOVER = "#4338ca"
CIAN = "#0284c7"
CIAN_HOVER = "#0369a1"
MORADO = "#7c3aed"
MORADO_HOVER = "#6d28d9"
ROSA = "#e11d48"
ROSA_HOVER = "#be123c"

COLOR_NUEVO = "#7c3aed"       # Violeta vivo
COLOR_EJECUCION = "#10b981"   # Verde esmeralda vivo
COLOR_BLOQUEADO = "#ef4444"   # Rojo vivo
COLOR_LISTO = "#2563eb"       # Azul eléctrico
COLOR_SUSPENDIDO = "#f59e0b"  # Ámbar / Naranja vivo
COLOR_TERMINADO = "#475569"   # Pizarra

OPCIONES_RAM = [
    "64 MB (Modo prueba)",
    "512 MB",
    "1024 MB (1 GB)",
    "2048 MB (2 GB)",
    "4096 MB (4 GB)",
    "8192 MB (8 GB)",
    "16384 MB (16 GB)",
    "32768 MB (32 GB)",
    "65536 MB (64 GB)",
    "131072 MB (128 GB)",
    "262144 MB (256 GB · Máx)",
]

OPCIONES_ALMACENAMIENTO = [
    "128 MB (Modo prueba)",
    "1024 MB (1 GB)",
    "65536 MB (64 GB)",
    "131072 MB (128 GB)",
    "262144 MB (256 GB)",
    "524288 MB (512 GB)",
    "1048576 MB (1 TB)",
    "2097152 MB (2 TB)",
    "4194304 MB (4 TB)",
]

OPCIONES_POLITICA_FIJA = [
    "2 marcos / proceso",
    "3 marcos / proceso",
    "4 marcos / proceso",
    "6 marcos / proceso",
    "8 marcos / proceso",
]

OPCIONES_ALGORITMO = [
    "FIFO (First-In, First-Out)",
]

MIN_CAPACIDAD_MB = 1
MAX_RAM_MB = 262144
MIN_INTERVALO_S = 0.1
MAX_INTERVALO_S = 60.0
MAX_PASADAS_CPU = 999
MAX_HILOS = 64


class Aplicacion(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Simulador SO · 7 Estados, Particiones Dinámicas, Paginación FIFO y Memoria Virtual")
        # Tamaño seguro para permitir maximizar y redimensionar libremente
        self.geometry("1180x670")
        self.minsize(880, 560)
        self.resizable(True, True)
        try:
            self.attributes("-zoomed", True)
        except tk.TclError:
            pass
        self.configure(bg=FONDO)

        self.simulador = Simulador()
        self.ejecutando = True
        self.after_id = None
        self.intervalo_var = tk.StringVar(value="1")
        self.memoria_var = tk.StringVar(value=OPCIONES_RAM[0])
        self.almacenamiento_var = tk.StringVar(value=OPCIONES_ALMACENAMIENTO[0])
        self.modo_memoria_var = tk.StringVar(value=MODOS_MEMORIA[0])
        self.politica_fija_var = tk.StringVar(value=OPCIONES_POLITICA_FIJA[1])
        self.algoritmo_var = tk.StringVar(value=OPCIONES_ALGORITMO[0])
        self.estado_cpu_var = tk.StringVar(value="● CPU ACTIVA")
        self.cpu_actual_var = tk.StringVar(value="CPU en espera")
        self._ultimo_historial = None

        self.form_vars = {
            "nombre": tk.StringVar(),
            "tamano": tk.StringVar(value="16"),
            "hilos": tk.StringVar(value="2"),
            "prioritario": tk.BooleanVar(value=False),
            "pasadas": tk.StringVar(value="5"),
        }
        self.recursos_check_vars = {
            rec: tk.BooleanVar(value=False) for rec in RECURSOS_SISTEMA
        }

        self._registrar_validadores()
        self._configurar_estilos()
        self._construir_interfaz()
        self.intervalo_var.trace_add("write", lambda *_: self._programar_reloj())
        self._refrescar()
        self._programar_reloj()
        self.protocol("WM_DELETE_WINDOW", self._cerrar)

    def _registrar_validadores(self):
        self.vcmd_tamano = (
            self.register(lambda P: self._validar_entero_rango(P, MAX_RAM_MB)),
            "%P",
        )
        self.vcmd_hilos = (
            self.register(lambda P: self._validar_entero_rango(P, MAX_HILOS)),
            "%P",
        )
        self.vcmd_pasadas = (
            self.register(lambda P: self._validar_entero_rango(P, MAX_PASADAS_CPU)),
            "%P",
        )
        self.vcmd_intervalo = (
            self.register(self._validar_intervalo),
            "%P",
        )
        self.vcmd_nombre = (
            self.register(lambda P: self._validar_texto(P, max_len=24)),
            "%P",
        )

    @staticmethod
    def _validar_entero_rango(valor: str, maximo: int) -> bool:
        if valor == "":
            return True
        if not valor.isdigit():
            return False
        if valor.startswith("0"):
            return False
        return 1 <= int(valor) <= maximo

    @staticmethod
    def _validar_intervalo(valor: str) -> bool:
        if valor == "":
            return True
        if valor.startswith(".") or " " in valor:
            return False
        if not re.fullmatch(r"(0(\.\d{0,2})?|[1-9]\d?(\.\d{0,2})?)", valor):
            return False
        if valor in ("0.0", "0.00"):
            return False
        try:
            return float(valor) <= MAX_INTERVALO_S
        except ValueError:
            return False

    def _normalizar_intervalo(self, _evento=None):
        raw = self.intervalo_var.get().strip()
        try:
            val = float(raw)
            if not math.isfinite(val) or val < MIN_INTERVALO_S or val > MAX_INTERVALO_S:
                raise ValueError
            if raw.endswith("."):
                self.intervalo_var.set(raw[:-1])
        except ValueError:
            self.intervalo_var.set("1")

    @staticmethod
    def _validar_texto(valor: str, max_len: int) -> bool:
        if len(valor) > max_len:
            return False
        return bool(re.match(r"^[a-zA-Z0-9áéíóúÁÉÍÓÚñÑüÜ _\-]*$", valor))

    @staticmethod
    def _extraer_entero(texto_opcion: str) -> int:
        return int(texto_opcion.split()[0])

    def _configurar_estilos(self):
        estilo = ttk.Style(self)
        estilo.theme_use("clam")

        estilo.configure("TFrame", background=FONDO)
        estilo.configure("Card.TFrame", background=BLANCO)
        estilo.configure("TLabel", background=FONDO, foreground=TINTA, font=("TkDefaultFont", 9))
        estilo.configure("Card.TLabel", background=BLANCO, foreground=TINTA, font=("TkDefaultFont", 9, "bold"))
        estilo.configure("CardHeader.TLabel", background=BLANCO, foreground=TEXTO_SEC, font=("TkDefaultFont", 8, "bold"))
        estilo.configure("Card.TCheckbutton", background=BLANCO, foreground=TINTA, font=("TkDefaultFont", 9))
        estilo.configure("Section.TLabel", background=BLANCO, foreground=INDIGO, font=("TkDefaultFont", 11, "bold"))
        estilo.configure("Muted.TLabel", background=BLANCO, foreground=GRIS_OSCURO, font=("TkDefaultFont", 9))

        # Pestañas coloridas
        estilo.configure("TNotebook", background=FONDO, borderwidth=0)
        estilo.configure(
            "TNotebook.Tab",
            padding=(14, 7),
            font=("TkDefaultFont", 9, "bold"),
            background="#c7d2fe",
            foreground="#312e81",
        )
        estilo.map(
            "TNotebook.Tab",
            background=[("selected", INDIGO)],
            foreground=[("selected", BLANCO)],
        )

        # Tablas con encabezados vivos en índigo
        estilo.configure(
            "Treeview",
            rowheight=27,
            font=("TkDefaultFont", 9),
            background=BLANCO,
            fieldbackground=BLANCO,
            borderwidth=0,
        )
        estilo.configure(
            "Treeview.Heading",
            font=("TkDefaultFont", 9, "bold"),
            background="#312e81",
            foreground=BLANCO,
            padding=6,
            relief="flat",
        )
        estilo.map("Treeview.Heading", background=[("active", INDIGO)])

        # Botones de colores vivos por función
        estilo.configure("Primary.TButton", background=INDIGO, foreground=BLANCO, padding=(11, 6), font=("TkDefaultFont", 9, "bold"), borderwidth=0)
        estilo.map("Primary.TButton", background=[("active", INDIGO_HOVER)])

        estilo.configure("Cyan.TButton", background=CIAN, foreground=BLANCO, padding=(10, 6), font=("TkDefaultFont", 9, "bold"), borderwidth=0)
        estilo.map("Cyan.TButton", background=[("active", CIAN_HOVER)])

        estilo.configure("Purple.TButton", background=MORADO, foreground=BLANCO, padding=(10, 6), font=("TkDefaultFont", 9, "bold"), borderwidth=0)
        estilo.map("Purple.TButton", background=[("active", MORADO_HOVER)])

        estilo.configure("Danger.TButton", background=ROSA, foreground=BLANCO, padding=(10, 6), font=("TkDefaultFont", 9, "bold"), borderwidth=0)
        estilo.map("Danger.TButton", background=[("active", ROSA_HOVER)])

        estilo.configure("Success.TButton", background="#059669", foreground=BLANCO, padding=(10, 6), font=("TkDefaultFont", 9, "bold"), borderwidth=0)
        estilo.map("Success.TButton", background=[("active", "#047857")])

        estilo.configure("Amber.TButton", background="#d97706", foreground=BLANCO, padding=(10, 6), font=("TkDefaultFont", 9, "bold"), borderwidth=0)
        estilo.map("Amber.TButton", background=[("active", "#b45309")])

        estilo.configure("TButton", padding=(9, 5), font=("TkDefaultFont", 9))

    @staticmethod
    def _crear_tarjeta(parent, padding=12, color_borde=BORDE):
        """Crea una tarjeta blanca con borde colorido y franja superior viva."""
        borde = tk.Frame(parent, bg=color_borde, bd=0)
        franja = tk.Frame(borde, bg=INDIGO, height=3)
        franja.pack(fill="x", side="top")
        interior = ttk.Frame(borde, style="Card.TFrame", padding=padding)
        interior.pack(fill="both", expand=True, padx=1, pady=(0, 1))
        return borde, interior

    def _construir_interfaz(self):
        # Banner superior oscuro vibrante
        banner = tk.Frame(self, bg=HEADER_BG, padx=18, pady=9)
        banner.pack(fill="x")

        bloque_titulo = tk.Frame(banner, bg=HEADER_BG)
        bloque_titulo.pack(side="left")
        tk.Label(
            bloque_titulo,
            text="Simulador de Sistemas Operativos",
            bg=HEADER_BG,
            fg="#ffffff",
            font=("TkDefaultFont", 16, "bold"),
        ).pack(anchor="w")
        tk.Label(
            bloque_titulo,
            text="7 Estados · Concurrencia · Paginación FIFO · Particiones Dinámicas · Memoria Virtual",
            bg=HEADER_BG,
            fg="#a5b4fc",
            font=("TkDefaultFont", 9),
        ).pack(anchor="w")

        ttk.Button(banner, text="🧹 Limpiar todo", style="Danger.TButton", command=self._limpiar_todo).pack(side="right", padx=(6, 0), pady=2)
        ttk.Button(banner, text="🔄 Reejecutar procesos", style="Purple.TButton", command=self._reiniciar_procesos).pack(side="right", padx=(6, 0), pady=2)
        self.cpu_toggle_button = ttk.Button(banner, text="⏸ Pausar", style="Amber.TButton", command=self._alternar_cpu)
        self.cpu_toggle_button.pack(side="right", padx=(6, 0), pady=2)
        ttk.Button(banner, text="▶ Paso CPU", style="Cyan.TButton", command=self._paso_manual).pack(side="right", padx=(6, 0), pady=2)

        self.lbl_estado_cpu = tk.Label(
            banner,
            textvariable=self.estado_cpu_var,
            bg="#064e3b",
            fg="#34d399",
            font=("TkDefaultFont", 9, "bold"),
            padx=10,
            pady=4,
        )
        self.lbl_estado_cpu.pack(side="right", padx=12, pady=2)

        # Barra de configuración de Hardware y Políticas
        marco_config_ext, configuracion = self._crear_tarjeta(self, padding=(12, 8))
        marco_config_ext.pack(fill="x", padx=16, pady=(8, 6))

        self._campo_desplegable(configuracion, "ESQUEMA DE MEMORIA", self.modo_memoria_var, MODOS_MEMORIA, 23)
        self._campo_desplegable(configuracion, "POLÍTICA FIJA", self.politica_fija_var, OPCIONES_POLITICA_FIJA, 16)
        self._campo_desplegable(configuracion, "ALGORITMO", self.algoritmo_var, OPCIONES_ALGORITMO, 20)
        self._campo_desplegable(configuracion, "MEMORIA RAM (MÁX 256 GB)", self.memoria_var, OPCIONES_RAM, 19)
        self._campo_desplegable(configuracion, "MEM. VIRTUAL / DISCO", self.almacenamiento_var, OPCIONES_ALMACENAMIENTO, 18)

        caja_tiempo = ttk.Frame(configuracion, style="Card.TFrame")
        caja_tiempo.pack(side="left", padx=(0, 8))
        ttk.Label(caja_tiempo, text="CICLO (0.1–60s)", style="CardHeader.TLabel").pack(anchor="w")
        entry_tiempo = ttk.Entry(
            caja_tiempo,
            textvariable=self.intervalo_var,
            width=10,
            validate="key",
            validatecommand=self.vcmd_intervalo,
        )
        entry_tiempo.pack(anchor="w", pady=(2, 0))
        entry_tiempo.bind("<FocusOut>", self._normalizar_intervalo)
        entry_tiempo.bind("<Return>", self._normalizar_intervalo)

        ttk.Button(configuracion, text="✓ Aplicar", style="Primary.TButton", command=self._aplicar_capacidades).pack(side="left", padx=(6, 0), pady=(11, 0))

        # Cuaderno de pestañas principal
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=16, pady=(2, 10))
        self.pestana_procesos = ttk.Frame(self.notebook, padding=(0, 6, 0, 0))
        self.pestana_memoria = ttk.Frame(self.notebook, padding=(0, 6, 0, 0))
        self.pestana_virtual = ttk.Frame(self.notebook, padding=(0, 6, 0, 0))
        self.pestana_recursos = ttk.Frame(self.notebook, padding=(0, 6, 0, 0))
        self.pestana_estados = ttk.Frame(self.notebook, padding=(0, 6, 0, 0))

        self.notebook.add(self.pestana_procesos, text="  Programas / Procesos  ")
        self.notebook.add(self.pestana_memoria, text="  Memoria Principal (RAM)  ")
        self.notebook.add(self.pestana_virtual, text="  Memoria Virtual y Disco (Swap)  ")
        self.notebook.add(self.pestana_recursos, text="  Estado de Recursos  ")
        self.notebook.add(self.pestana_estados, text="  Modelo de 7 Estados  ")

        self._construir_pestana_procesos()
        self._construir_pestana_memoria()
        self._construir_pestana_virtual()
        self._construir_pestana_recursos()
        self._construir_pestana_estados()

    @staticmethod
    def _campo_desplegable(parent, etiqueta, variable, opciones, ancho):
        caja = ttk.Frame(parent, style="Card.TFrame")
        caja.pack(side="left", padx=(0, 8))
        ttk.Label(caja, text=etiqueta, style="CardHeader.TLabel").pack(anchor="w")
        combo = ttk.Combobox(
            caja,
            textvariable=variable,
            values=opciones,
            width=ancho,
            state="readonly",
        )
        combo.pack(anchor="w", pady=(2, 0))

    def _construir_pestana_procesos(self):
        self.pestana_procesos.columnconfigure(0, weight=0, minsize=290)
        self.pestana_procesos.columnconfigure(1, weight=1)
        self.pestana_procesos.rowconfigure(0, weight=1)

        # Tarjeta izquierda: Formulario compacto
        card_form_ext, formulario = self._crear_tarjeta(self.pestana_procesos, padding=12)
        card_form_ext.grid(row=0, column=0, sticky="nsew", padx=(0, 12))

        ttk.Label(formulario, text="Nuevo Proceso", style="Section.TLabel").pack(anchor="w", pady=(0, 6))

        ttk.Label(formulario, text="Nombre del proceso", style="Card.TLabel").pack(anchor="w", pady=(0, 2))
        self.nombre_entry = ttk.Entry(
            formulario,
            textvariable=self.form_vars["nombre"],
            validate="key",
            validatecommand=self.vcmd_nombre,
        )
        self.nombre_entry.pack(fill="x", pady=(0, 5))

        ttk.Label(formulario, text="Tamaño en memoria (MB)", style="Card.TLabel").pack(anchor="w", pady=(0, 2))
        ttk.Entry(
            formulario,
            textvariable=self.form_vars["tamano"],
            validate="key",
            validatecommand=self.vcmd_tamano,
        ).pack(fill="x", pady=(0, 5))

        fila_doble = ttk.Frame(formulario, style="Card.TFrame")
        fila_doble.pack(fill="x", pady=(0, 5))
        fila_doble.columnconfigure(0, weight=1)
        fila_doble.columnconfigure(1, weight=1)

        col_hilos = ttk.Frame(fila_doble, style="Card.TFrame")
        col_hilos.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ttk.Label(col_hilos, text="Hilos (1–64)", style="Card.TLabel").pack(anchor="w", pady=(0, 2))
        ttk.Entry(
            col_hilos,
            textvariable=self.form_vars["hilos"],
            width=10,
            validate="key",
            validatecommand=self.vcmd_hilos,
        ).pack(fill="x")

        col_pasadas = ttk.Frame(fila_doble, style="Card.TFrame")
        col_pasadas.grid(row=0, column=1, sticky="ew", padx=(4, 0))
        ttk.Label(col_pasadas, text="Pasadas (1–999)", style="Card.TLabel").pack(anchor="w", pady=(0, 2))
        ttk.Entry(
            col_pasadas,
            textvariable=self.form_vars["pasadas"],
            width=10,
            validate="key",
            validatecommand=self.vcmd_pasadas,
        ).pack(fill="x")

        ttk.Label(formulario, text="Recursos requeridos (Checklist):", style="Card.TLabel").pack(
            anchor="w", pady=(2, 2)
        )
        marco_checks = ttk.Frame(formulario, style="Card.TFrame")
        marco_checks.pack(fill="x", pady=(0, 4))

        for idx, rec in enumerate(RECURSOS_SISTEMA):
            chk = ttk.Checkbutton(
                marco_checks,
                text=rec,
                variable=self.recursos_check_vars[rec],
                style="Card.TCheckbutton",
            )
            chk.grid(row=idx // 3, column=idx % 3, sticky="w", padx=(0, 8), pady=1)

        ttk.Checkbutton(
            formulario,
            text="Proceso Prioritario (desaloja No prioritarios)",
            variable=self.form_vars["prioritario"],
            style="Card.TCheckbutton",
        ).pack(anchor="w", pady=(2, 8))

        ttk.Button(
            formulario,
            text="＋  CREAR PROCESO",
            style="Primary.TButton",
            command=self._crear_proceso,
        ).pack(fill="x", ipady=3)

        # Tarjeta derecha: Tabla de procesos
        card_lista_ext, lista = self._crear_tarjeta(self.pestana_procesos, padding=12)
        card_lista_ext.grid(row=0, column=1, sticky="nsew")
        lista.rowconfigure(1, weight=1)
        lista.columnconfigure(0, weight=1)

        barra = ttk.Frame(lista, style="Card.TFrame")
        barra.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ttk.Label(barra, text="Cola y Estado de Procesos", style="Section.TLabel").pack(side="left")
        ttk.Label(barra, textvariable=self.cpu_actual_var, font=("TkDefaultFont", 10, "bold"), foreground="#059669").pack(side="right")
        
        columnas = ("id", "nombre", "tamano", "paginas", "fallos", "hilos", "recursos", "prioridad", "restantes", "estado")
        self.tabla_procesos = self._crear_tabla(lista, columnas, {
            "id": ("ID", 50), "nombre": ("Nombre", 100), "tamano": ("MB", 46),
            "paginas": ("RAM/Tot", 66), "fallos": ("Fallos Pág", 68), "hilos": ("Hilos", 44),
            "recursos": ("Recursos", 115), "prioridad": ("Prioridad", 95),
            "restantes": ("Restantes", 66), "estado": ("Estado Actual", 125),
        })
        
        self.tabla_procesos.tag_configure("EJECUCION", background="#a7f3d0", foreground="#064e3b")
        self.tabla_procesos.tag_configure("BLOQUEADO", background="#fecaca", foreground="#7f1d1d")
        self.tabla_procesos.tag_configure("LISTO", background="#bfdbfe", foreground="#1e3a8a")
        self.tabla_procesos.tag_configure("SUSPENDIDO", background="#fde68a", foreground="#78350f")
        self.tabla_procesos.tag_configure("TERMINADO", background="#e2e8f0", foreground="#475569")

        self.tabla_procesos.grid(row=1, column=0, sticky="nsew")

        acciones = ttk.Frame(lista, style="Card.TFrame")
        acciones.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(acciones, text="⛔ Bloquear en CPU", style="Danger.TButton", command=self._bloquear).pack(side="left", padx=(0, 6))
        ttk.Button(acciones, text="✅ Desbloquear", style="Success.TButton", command=self._desbloquear).pack(side="left", padx=(0, 6))
        ttk.Button(acciones, text="💾 Suspender (a Swap)", style="Amber.TButton", command=self._suspender).pack(side="left", padx=(0, 6))
        ttk.Button(acciones, text="⚡ Reanudar (a RAM)", style="Cyan.TButton", command=self._reanudar).pack(side="left")

    def _construir_pestana_memoria(self):
        self.pestana_memoria.columnconfigure(0, weight=1)
        self.pestana_memoria.rowconfigure(0, weight=1)

        card_ext, panel = self._crear_tarjeta(self.pestana_memoria, padding=12)
        card_ext.grid(row=0, column=0, sticky="nsew")
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(3, weight=1)

        self.titulo_memoria = ttk.Label(panel, text="Memoria Principal (RAM)", style="Section.TLabel")
        self.titulo_memoria.grid(row=0, column=0, sticky="w")
        self.resumen_memoria = ttk.Label(panel, text="", style="Muted.TLabel", font=("TkDefaultFont", 9, "bold"))
        self.resumen_memoria.grid(row=1, column=0, sticky="w", pady=(2, 6))

        self.canvas_memoria = tk.Canvas(panel, height=50, background="#e0e7ff", highlightthickness=1, highlightbackground=BORDE)
        self.canvas_memoria.grid(row=2, column=0, sticky="ew", pady=(0, 10))

        columnas = ("unidad", "direccion", "proceso", "detalle", "estado")
        self.tabla_memoria = self._crear_tabla(panel, columnas, {
            "unidad": ("Marco / Partición", 145),
            "direccion": ("Dirección Física (MB / Hex)", 220),
            "proceso": ("Proceso Ocupante", 190),
            "detalle": ("Página / Tamaño", 170),
            "estado": ("Estado / Fragmentación", 190),
        })
        self.tabla_memoria.grid(row=3, column=0, sticky="nsew")

    def _construir_pestana_virtual(self):
        self.pestana_virtual.columnconfigure(0, weight=1)
        self.pestana_virtual.rowconfigure(0, weight=1)

        card_ext, panel = self._crear_tarjeta(self.pestana_virtual, padding=12)
        card_ext.grid(row=0, column=0, sticky="nsew")
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(2, weight=1)

        ttk.Label(panel, text="Tabla de Páginas y Memoria Virtual (Reemplazo FIFO · RAM vs. Disco)", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        self.resumen_virtual = ttk.Label(panel, text="", style="Muted.TLabel", font=("TkDefaultFont", 9, "bold"))
        self.resumen_virtual.grid(row=1, column=0, sticky="w", pady=(2, 10))

        columnas = ("proceso", "pagina", "presencia", "modificacion", "ubicacion")
        self.tabla_virtual = self._crear_tabla(panel, columnas, {
            "proceso": ("Proceso", 180),
            "pagina": ("Página / Segmento Virtual", 175),
            "presencia": ("Bit Presencia (P)", 145),
            "modificacion": ("Bit Modificación (M)", 145),
            "ubicacion": ("Ubicación Física / Orden FIFO", 280),
        })
        self.tabla_virtual.grid(row=2, column=0, sticky="nsew")

    def _construir_pestana_recursos(self):
        self.pestana_recursos.columnconfigure(0, weight=1)
        self.pestana_recursos.rowconfigure(0, weight=1)

        card_ext, panel = self._crear_tarjeta(self.pestana_recursos, padding=12)
        card_ext.grid(row=0, column=0, sticky="nsew")
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(1, weight=1)

        ttk.Label(panel, text="Estado Booleano de Recursos del Sistema (Exclusión Mutua)", style="Section.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 8))
        
        columnas = ("recurso", "disponible", "estado", "propietario")
        self.tabla_recursos = self._crear_tabla(panel, columnas, {
            "recurso": ("Recurso / Dispositivo", 210),
            "disponible": ("Disponible (Booleano)", 170),
            "estado": ("Estado", 160),
            "propietario": ("Proceso Propietario (PID · Nombre)", 320),
        })
        self.tabla_recursos.grid(row=1, column=0, sticky="nsew")

    def _construir_pestana_estados(self):
        self.pestana_estados.columnconfigure(0, weight=1, uniform="grupo_estados")
        self.pestana_estados.columnconfigure(1, weight=1, uniform="grupo_estados")
        self.pestana_estados.rowconfigure(0, weight=1)

        # Panel izquierdo: Diagrama visual colorido de los 7 estados
        card_diag_ext, card_diag = self._crear_tarjeta(self.pestana_estados, padding=12)
        card_diag_ext.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        card_diag.rowconfigure(2, weight=1)
        card_diag.columnconfigure(0, weight=1)

        ttk.Label(card_diag, text="Diagrama Dinámico del Modelo de 7 Estados", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            card_diag,
            text="Seguimiento en vivo de procesos (ID · Nombre) por cada estado del sistema.",
            style="Muted.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(1, 6))

        self.diagrama = tk.Canvas(card_diag, background="#f5f3ff", highlightthickness=1, highlightbackground=BORDE)
        self.diagrama.grid(row=2, column=0, sticky="nsew")

        # Panel derecho: Registro Histórico amplio y seleccionable como texto
        card_log_ext, log_panel = self._crear_tarjeta(self.pestana_estados, padding=12)
        card_log_ext.grid(row=0, column=1, sticky="nsew")
        log_panel.rowconfigure(2, weight=1)
        log_panel.columnconfigure(0, weight=1)

        header_log = ttk.Frame(log_panel, style="Card.TFrame")
        header_log.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 2))
        ttk.Label(header_log, text="Registro Histórico de Eventos (CPU / MMU)", style="Section.TLabel").pack(side="left")

        ttk.Button(
            header_log,
            text="📋 Copiar historial",
            style="Primary.TButton",
            command=self._copiar_historial,
        ).pack(side="right")

        ttk.Label(
            log_panel,
            text="Selecciona líneas con el ratón y usa Ctrl+C, o haz clic en 'Copiar historial'.",
            style="Muted.TLabel",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 6))

        self.texto_eventos = tk.Text(
            log_panel,
            font=("Consolas", 9),
            background="#1e1b4b",
            foreground="#e0e7ff",
            selectbackground="#4f46e5",
            selectforeground="#ffffff",
            relief="flat",
            wrap="word",
            padx=10,
            pady=8,
            spacing3=4,
            cursor="xterm",
            state="disabled",
        )
        self.texto_eventos.grid(row=2, column=0, sticky="nsew")

        self.texto_eventos.tag_configure("fallo", foreground="#fca5a5", font=("Consolas", 9, "bold"))
        self.texto_eventos.tag_configure("exito", foreground="#6ee7b7", font=("Consolas", 9, "bold"))
        self.texto_eventos.tag_configure("mmu", foreground="#7dd3fc")
        self.texto_eventos.tag_configure("alerta", foreground="#fcd34d")
        self.texto_eventos.tag_configure("normal", foreground="#e0e7ff")

        self.texto_eventos.bind("<Control-c>", self._copiar_seleccion_eventos)
        self.texto_eventos.bind("<Control-C>", self._copiar_seleccion_eventos)

        self.menu_log = tk.Menu(self, tearoff=0)
        self.menu_log.add_command(label="Copiar selección", command=self._copiar_seleccion_eventos)
        self.menu_log.add_command(label="Copiar todo el historial", command=self._copiar_historial)
        self.texto_eventos.bind("<Button-3>", self._mostrar_menu_log)

        scrollbar = ttk.Scrollbar(log_panel, orient="vertical", command=self.texto_eventos.yview)
        scrollbar.grid(row=2, column=1, sticky="ns")
        self.texto_eventos.configure(yscrollcommand=scrollbar.set)

    def _mostrar_menu_log(self, evento):
        try:
            self.menu_log.tk_popup(evento.x_root, evento.y_root)
        finally:
            self.menu_log.grab_release()

    def _copiar_seleccion_eventos(self, _evento=None):
        try:
            seleccion = self.texto_eventos.get(tk.SEL_FIRST, tk.SEL_LAST)
            if seleccion:
                self.clipboard_clear()
                self.clipboard_append(seleccion)
        except tk.TclError:
            pass
        return "break"

    def _copiar_historial(self):
        contenido = self.texto_eventos.get("1.0", tk.END).strip()
        if not contenido:
            return
        self.clipboard_clear()
        self.clipboard_append(contenido)
        messagebox.showinfo("Copiado", "El registro histórico de eventos se copió al portapapeles.", parent=self)

    @staticmethod
    def _crear_tabla(parent, columnas, configuracion):
        tabla = ttk.Treeview(parent, columns=columnas, show="headings", selectmode="browse")
        for columna in columnas:
            titulo, ancho = configuracion[columna]
            tabla.heading(columna, text=titulo)
            tabla.column(columna, width=ancho, minwidth=45, anchor="w", stretch=True)
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
        nombre = self.form_vars["nombre"].get().strip()
        tamano_txt = self.form_vars["tamano"].get().strip()
        hilos_txt = self.form_vars["hilos"].get().strip()
        pasadas_txt = self.form_vars["pasadas"].get().strip()

        if not nombre:
            messagebox.showerror("Datos incompletos", "Ingresa un nombre válido para el proceso.", parent=self)
            return
        if not tamano_txt or not hilos_txt or not pasadas_txt:
            messagebox.showerror("Datos incompletos", "Tamaño, Hilos y Pasadas por CPU son obligatorios.", parent=self)
            return

        tamano = int(tamano_txt)
        hilos = int(hilos_txt)
        pasadas = int(pasadas_txt)

        if not (MIN_CAPACIDAD_MB <= tamano <= MAX_RAM_MB):
            messagebox.showerror("Tamaño fuera de límite", f"El tamaño debe estar entre {MIN_CAPACIDAD_MB} MB y {MAX_RAM_MB} MB.", parent=self)
            return
        if not (1 <= hilos <= MAX_HILOS):
            messagebox.showerror("Hilos fuera de límite", f"Los hilos deben estar entre 1 y {MAX_HILOS}.", parent=self)
            return
        if not (1 <= pasadas <= MAX_PASADAS_CPU):
            messagebox.showerror("Pasadas fuera de límite", f"Las pasadas deben estar entre 1 y {MAX_PASADAS_CPU}.", parent=self)
            return

        recursos_seleccionados = [
            rec for rec, var in self.recursos_check_vars.items() if var.get()
        ]

        try:
            proceso = self.simulador.crear_proceso(
                nombre=nombre,
                tamano_mb=tamano,
                recursos=recursos_seleccionados,
                prioritario=self.form_vars["prioritario"].get(),
                pasadas_cpu=pasadas,
                hilos=hilos,
            )
        except ValueError as error:
            messagebox.showerror("No se pudo crear el proceso", str(error), parent=self)
            return

        self.form_vars["nombre"].set("")
        for var in self.recursos_check_vars.values():
            var.set(False)
        self._refrescar()
        self.notebook.select(self.pestana_procesos)
        self.tabla_procesos.selection_set(proceso.id)
        self.tabla_procesos.see(proceso.id)

    def _aplicar_capacidades(self):
        memoria = self._extraer_entero(self.memoria_var.get())
        almacenamiento = self._extraer_entero(self.almacenamiento_var.get())
        modo = self.modo_memoria_var.get()
        marcos_fijos = self._extraer_entero(self.politica_fija_var.get())
        try:
            self.simulador.configurar_memoria(memoria, almacenamiento, modo, marcos_fijos)
        except ValueError as error:
            messagebox.showerror("No se pudo aplicar", str(error), parent=self)
            return
        self._refrescar()

    def _reiniciar_procesos(self):
        try:
            self.simulador.reiniciar_procesos()
        except ValueError as error:
            messagebox.showinfo("Sin procesos", str(error), parent=self)
            return
        self._refrescar()

    def _limpiar_todo(self):
        if messagebox.askyesno("Limpiar simulación", "¿Deseas reiniciar la simulación y borrar los procesos actuales?", parent=self):
            self.simulador.limpiar_simulacion()
            self._refrescar()

    def _alternar_cpu(self):
        self.ejecutando = not self.ejecutando
        if self.ejecutando:
            self.estado_cpu_var.set("● CPU ACTIVA")
            self.lbl_estado_cpu.configure(bg="#064e3b", fg="#34d399")
            self.cpu_toggle_button.configure(text="⏸ Pausar", style="Amber.TButton")
        else:
            self.estado_cpu_var.set("⏸ CPU PAUSADA")
            self.lbl_estado_cpu.configure(bg="#78350f", fg="#fcd34d")
            self.cpu_toggle_button.configure(text="▶ Reanudar", style="Success.TButton")
        self._programar_reloj()

    def _programar_reloj(self):
        if self.after_id is not None:
            self.after_cancel(self.after_id)
            self.after_id = None
        if self.ejecutando:
            try:
                raw = self.intervalo_var.get().strip()
                if not raw or raw.startswith(".") or raw.endswith("."):
                    raise ValueError
                segundos = float(raw)
                if not math.isfinite(segundos) or not (MIN_INTERVALO_S <= segundos <= MAX_INTERVALO_S):
                    raise ValueError
            except ValueError:
                self.estado_cpu_var.set(f"Tiempo ({MIN_INTERVALO_S}–{int(MAX_INTERVALO_S)}s)")
                self.lbl_estado_cpu.configure(bg="#7f1d1d", fg="#fca5a5")
                return
            self.estado_cpu_var.set("● CPU ACTIVA")
            self.lbl_estado_cpu.configure(bg="#064e3b", fg="#34d399")
            self.after_id = self.after(max(100, int(segundos * 1000)), self._avanzar_cpu)

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

    def _dibujar_barras_memoria(self):
        canvas = self.canvas_memoria
        canvas.delete("all")
        ancho_total = max(canvas.winfo_width(), 640)
        alto = canvas.winfo_height()
        mapa_procesos = {p.id: p for p in self.simulador.procesos}

        paleta_procesos = ["#4f46e5", "#0284c7", "#7c3aed", "#db2777", "#ea580c", "#0d9488"]

        if self.simulador.modo_memoria == MODO_PAGINACION:
            marcos = self.simulador.tabla_marcos_memoria()
            total = max(len(marcos), 1)
            ancho_marco = ancho_total / total
            for idx, _ini, _fin, pid, pagina in marcos:
                x1 = idx * ancho_marco
                x2 = x1 + ancho_marco
                if pid:
                    proc = mapa_procesos.get(pid)
                    num_pid = int(pid[1:]) if pid[1:].isdigit() else idx
                    color = COLOR_EJECUCION if (proc and proc.estado == Estado.EJECUCION) else paleta_procesos[num_pid % len(paleta_procesos)]
                    canvas.create_rectangle(x1 + 1, 2, x2 - 1, alto - 2, fill=color, outline="#ffffff", width=1)
                    canvas.create_text(
                        (x1 + x2) / 2, alto / 2,
                        text=f"M{idx}\n{pid}·P{pagina}",
                        fill="#ffffff", font=("TkDefaultFont", 8, "bold"),
                    )
                else:
                    canvas.create_rectangle(x1 + 1, 2, x2 - 1, alto - 2, fill="#e0e7ff", outline="#ffffff", width=1)
                    canvas.create_text(
                        (x1 + x2) / 2, alto / 2,
                        text=f"M{idx}\nLibre",
                        fill="#4338ca", font=("TkDefaultFont", 8),
                    )
        else:
            mem_total = max(self.simulador.memoria_mb, 1)
            for idx, (ini, fin, tam, pid) in enumerate(self.simulador.segmentos_particiones_dinamicas()):
                x1 = (ini / mem_total) * ancho_total
                x2 = ((fin + 1) / mem_total) * ancho_total
                if pid:
                    proc = mapa_procesos.get(pid)
                    num_pid = int(pid[1:]) if pid[1:].isdigit() else idx
                    color = COLOR_EJECUCION if (proc and proc.estado == Estado.EJECUCION) else paleta_procesos[num_pid % len(paleta_procesos)]
                    canvas.create_rectangle(x1 + 1, 2, x2 - 1, alto - 2, fill=color, outline="#ffffff", width=1)
                    if (x2 - x1) > 36:
                        canvas.create_text(
                            (x1 + x2) / 2, alto / 2,
                            text=f"{pid} ({tam}M)",
                            fill="#ffffff", font=("TkDefaultFont", 8, "bold"),
                        )
                else:
                    canvas.create_rectangle(x1 + 1, 2, x2 - 1, alto - 2, fill="#e0e7ff", outline="#a5b4fc", width=1)
                    if (x2 - x1) > 42:
                        canvas.create_text(
                            (x1 + x2) / 2, alto / 2,
                            text=f"Hueco\n{tam}M",
                            fill="#4338ca", font=("TkDefaultFont", 8),
                        )

    def _actualizar_consola_eventos(self):
        eventos = self.simulador.eventos[:150]
        if eventos == self._ultimo_historial:
            return
        self._ultimo_historial = list(eventos)

        self.texto_eventos.configure(state="normal")
        self.texto_eventos.delete("1.0", tk.END)

        total = len(eventos)
        for idx, evento in enumerate(eventos):
            num_evento = total - idx
            prefijo = f"[{num_evento:02d}] "
            linea = f"{prefijo}{evento}\n"

            tag = "normal"
            if "[Fallo Pág" in evento or "Bloqueado" in evento or "BLOQUEADO" in evento:
                tag = "fallo"
            elif "[Swap-In]" in evento or "entra a Ejecución" in evento or "terminó" in evento:
                tag = "exito"
            elif "[MMU]" in evento:
                tag = "mmu"
            elif "suspendido" in evento or "Suspendido" in evento or "desalojado" in evento:
                tag = "alerta"

            self.texto_eventos.insert(tk.END, linea, tag)

        self.texto_eventos.configure(state="disabled")

    def _refrescar(self):
        procesos = self.simulador.procesos
        mapa_procesos = {p.id: p for p in procesos}

        for item in self.tabla_procesos.get_children():
            self.tabla_procesos.delete(item)
            
        for p in procesos:
            tag = "TERMINADO"
            if p.estado == Estado.EJECUCION:
                tag = "EJECUCION"
            elif p.estado == Estado.BLOQUEADO:
                tag = "BLOQUEADO"
            elif p.estado == Estado.LISTO:
                tag = "LISTO"
            elif "SUSPENDIDO" in p.estado.name:
                tag = "SUSPENDIDO"

            if self.simulador.modo_memoria == MODO_PAGINACION:
                ram_tot = f"{len(p.tabla_paginas)}/{p.total_paginas} pág"
            else:
                ram_tot = "En RAM" if p.particion_ram else "En Swap"

            self.tabla_procesos.insert("", "end", iid=p.id, values=(
                p.id, p.nombre, p.tamano_mb, ram_tot, p.fallos_pagina, p.hilos, p.recursos,
                "Prioritario" if p.prioritario else "No prioritario",
                f"{p.restantes}/{p.pasadas_cpu}", p.estado.value
            ), tags=(tag,))

        actual = self.simulador.proceso_ejecutando
        self.cpu_actual_var.set(
            f"⚡ En CPU: {actual.id} · {actual.nombre} ({actual.hilos} hilo(s))"
            if actual
            else "CPU en espera"
        )

        filas_memoria = []
        if self.simulador.modo_memoria == MODO_PAGINACION:
            self.titulo_memoria.configure(text="Paginación en Memoria Principal (Política Fija · Reemplazo FIFO)")
            libres_lista = self.simulador.marcos_libres
            self.resumen_memoria.configure(
                text=f"RAM: {self.simulador.memoria_mb} MB ({self.simulador.total_marcos} marcos de "
                f"{self.simulador.tamano_marco_mb} MB) · Política fija: máx {self.simulador.marcos_fijos_por_proceso} marcos/proceso · "
                f"Marcos libres: {len(libres_lista)}"
            )
            for idx, ini_mb, fin_mb, pid, pagina in self.simulador.tabla_marcos_memoria():
                proceso = mapa_procesos.get(pid) if pid else None
                filas_memoria.append((
                    f"Marco {idx}",
                    f"{ini_mb}–{fin_mb} MB (0x{ini_mb * 1048576:08X})",
                    f"{pid} · {proceso.nombre}" if proceso else "Marco Libre",
                    f"Página virtual {pagina}" if pagina is not None else "—",
                    proceso.estado.value if proceso else "Disponible",
                ))
        else:
            self.titulo_memoria.configure(text="Particiones Dinámicas en Memoria Principal (Primer Ajuste)")
            frag = self.simulador.fragmentacion_externa_mb
            self.resumen_memoria.configure(
                text=f"RAM: {self.simulador.memoria_mb} MB · Usada: {self.simulador.memoria_usada_mb} MB · "
                f"Libre: {self.simulador.memoria_libre_mb} MB · Fragmentación externa: {frag} MB"
            )
            for i, (ini, fin, tam, pid) in enumerate(self.simulador.segmentos_particiones_dinamicas()):
                proceso = mapa_procesos.get(pid) if pid else None
                filas_memoria.append((
                    f"Partición {i}",
                    f"{ini}–{fin} MB (0x{ini * 1048576:08X})",
                    f"{pid} · {proceso.nombre}" if proceso else "Hueco Libre",
                    f"{tam} MB contiguos",
                    proceso.estado.value if proceso else ("Fragmento externo" if frag > 0 else "Libre"),
                ))

        self._reemplazar_filas(self.tabla_memoria, filas_memoria)
        self._dibujar_barras_memoria()

        self.resumen_virtual.configure(
            text=f"Disco / Swap: {self.simulador.almacenamiento_mb} MB totales · "
            f"Respaldo activo: {self.simulador.almacenamiento_usado_mb} MB · "
            f"Fallos de página (FIFO): {self.simulador.total_fallos_pagina}"
        )
        self._reemplazar_filas(self.tabla_virtual, self.simulador.tabla_memoria_virtual())

        filas_recursos = []
        for rec, disponible in self.simulador.recursos_disponibles.items():
            pid = self.simulador._recursos_ocupados.get(rec)
            proc = mapa_procesos.get(pid) if pid else None
            propietario_txt = f"{pid} · {proc.nombre}" if proc else "Ninguno"
            filas_recursos.append((
                rec,
                "True (Disponible)" if disponible else "False (Ocupado)",
                "LIBRE" if disponible else "EN USO",
                propietario_txt,
            ))
        self._reemplazar_filas(self.tabla_recursos, filas_recursos)

        self._actualizar_consola_eventos()
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
        ancho = max(canvas.winfo_width(), 520)
        alto = max(canvas.winfo_height(), 340)

        posiciones = {
            "Nuevo": (0.13, 0.16),
            Estado.LISTO_SUSPENDIDO.value: (0.14, 0.48),
            Estado.LISTO.value: (0.41, 0.48),
            Estado.EJECUCION.value: (0.67, 0.48),
            Estado.TERMINADO.value: (0.89, 0.48),
            Estado.BLOQUEADO_SUSPENDIDO.value: (0.14, 0.80),
            Estado.BLOQUEADO.value: (0.41, 0.80),
        }

        rx_corto = min(68, max(46, ancho * 0.105))
        rx_largo = min(78, max(54, ancho * 0.12))
        ry_base = min(34, max(26, alto * 0.085))

        nodos = {}
        for estado in ESTADOS:
            x, y = posiciones[estado]
            cx, cy = ancho * x, alto * y
            rx = rx_corto if len(estado) < 15 else rx_largo
            nodos[estado] = (cx, cy, rx, ry_base)

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
            start = (x1 + dx / distancia * (rx1 - 2), y1 + dy / distancia * (ry1 - 2))
            end = (x2 - dx / distancia * (rx2 + 3), y2 - dy / distancia * (ry2 + 3))
            canvas.create_line(*start, *end, fill="#6366f1", width=2, arrow=tk.LAST, arrowshape=(9, 11, 4))

        colores_estado = {
            "Nuevo": (COLOR_NUEVO, "#ede9fe"),
            Estado.LISTO_SUSPENDIDO.value: (COLOR_SUSPENDIDO, "#fef3c7"),
            Estado.LISTO.value: (COLOR_LISTO, "#dbeafe"),
            Estado.EJECUCION.value: (COLOR_EJECUCION, "#d1fae5"),
            Estado.TERMINADO.value: (COLOR_TERMINADO, "#e2e8f0"),
            Estado.BLOQUEADO_SUSPENDIDO.value: (COLOR_SUSPENDIDO, "#fef3c7"),
            Estado.BLOQUEADO.value: (COLOR_BLOQUEADO, "#fee2e2"),
        }

        procesos_por_estado = {estado: [] for estado in ESTADOS}
        for proceso in self.simulador.procesos:
            procesos_por_estado[proceso.estado.value].append(f"{proceso.id}·{proceso.nombre}")
        procesos_por_estado["Nuevo"] = []

        for estado, (cx, cy, rx, ry) in nodos.items():
            items = procesos_por_estado[estado]
            ocupado = bool(items)
            col_vivo, col_suave = colores_estado[estado]

            # Sombra suave
            canvas.create_oval(
                cx - rx + 2, cy - ry + 3, cx + rx + 2, cy + ry + 3,
                fill="#ddd6fe", outline="",
            )

            relleno = col_vivo if ocupado else col_suave
            texto_col = BLANCO if ocupado else TINTA
            grosor = 2.5 if ocupado else 1.8

            canvas.create_oval(
                cx - rx, cy - ry, cx + rx, cy + ry,
                fill=relleno, outline=col_vivo, width=grosor,
            )
            etiqueta = f"{estado}\n{', '.join(items)}" if ocupado else estado
            canvas.create_text(
                cx, cy, text=etiqueta, fill=texto_col, width=rx * 1.85,
                font=("TkDefaultFont", 8, "bold"), justify="center",
            )

    def _cerrar(self):
        if self.after_id is not None:
            self.after_cancel(self.after_id)
        self.destroy()


if __name__ == "__main__":
    Aplicacion().mainloop()