import unittest

from simulador import (
    ORIGEN_BLOQUEADO,
    ORIGEN_EJECUCION,
    ORIGEN_NUEVO,
    Estado,
    Simulador,
)


class SimuladorTests(unittest.TestCase):
    def test_procesos_se_atienden_por_orden_de_llegada(self):
        simulador = Simulador(16, 32)
        primero = simulador.crear_proceso("Primero", 2, "", 1, 3)
        segundo = simulador.crear_proceso("Segundo", 2, "", 4, 2)

        self.assertEqual(simulador.proceso_ejecutando.id, primero.id)
        simulador.avanzar()
        self.assertEqual(simulador.proceso_ejecutando.id, segundo.id)
        simulador.avanzar()
        self.assertEqual(simulador.proceso_ejecutando.id, primero.id)
        simulador.avanzar()
        self.assertEqual(segundo.estado, Estado.EJECUCION)

    def test_creacion_rechaza_si_no_hay_espacio_contiguo(self):
        simulador = Simulador(4, 8)
        simulador.crear_proceso("Uno", 3, "", 1, 3)
        with self.assertRaisesRegex(ValueError, "memoria"):
            simulador.crear_proceso("Dos", 2, "", 1, 1)

    def test_suspender_libera_memoria_y_reanudar_la_reserva(self):
        simulador = Simulador(4, 8)
        proceso = simulador.crear_proceso("Trabajo", 3, "Disco", 1, 2)
        simulador.bloquear_ejecucion()
        simulador.suspender(proceso.id)

        self.assertEqual(proceso.estado, Estado.BLOQUEADO_SUSPENDIDO)
        self.assertEqual(simulador.segmentos_memoria(), [(0, 3, None)])
        simulador.reanudar(proceso.id)
        self.assertEqual(proceso.estado, Estado.BLOQUEADO)
        self.assertEqual(simulador.segmentos_memoria(), [(0, 2, proceso.id), (3, 3, None)])
        simulador.desbloquear(proceso.id)
        self.assertEqual(proceso.estado, Estado.EJECUCION)

    def test_suspendido_listo_reanuda_detras_de_la_cola(self):
        simulador = Simulador(8, 16)
        primero = simulador.crear_proceso("Primero", 2, "", 1, 2)
        segundo = simulador.crear_proceso("Segundo", 2, "", 1, 2)
        simulador.suspender(segundo.id)

        self.assertEqual(segundo.estado, Estado.LISTO_SUSPENDIDO)
        simulador.reanudar(segundo.id)
        self.assertEqual(segundo.estado, Estado.LISTO)
        self.assertEqual(simulador.proceso_ejecutando.id, primero.id)
        simulador.avanzar()
        self.assertEqual(simulador.proceso_ejecutando.id, segundo.id)

    def test_bloqueo_y_desbloqueo_cambian_estado(self):
        simulador = Simulador(8, 16)
        proceso = simulador.crear_proceso("Trabajo", 2, "", 1, 2)
        simulador.bloquear_ejecucion()
        self.assertEqual(proceso.estado, Estado.BLOQUEADO)
        simulador.desbloquear(proceso.id)
        self.assertEqual(proceso.estado, Estado.EJECUCION)

    def test_proceso_terminado_libera_memoria_y_almacenamiento(self):
        simulador = Simulador(4, 4)
        proceso = simulador.crear_proceso("Fin", 4, "", 1, 1)
        simulador.avanzar()

        self.assertEqual(proceso.estado, Estado.TERMINADO)
        self.assertEqual(simulador.segmentos_memoria(), [(0, 3, None)])
        self.assertEqual(simulador.segmentos_almacenamiento(), [(0, 3, None)])


    # Requisito 2: un proceso sin recurso pasa directo a Ejecución.
    def test_proceso_sin_recurso_entra_a_ejecucion(self):
        simulador = Simulador(8, 16)
        proceso = simulador.crear_proceso("SinRecurso", 2, "Ninguno", 1, 2)

        self.assertEqual(proceso.estado, Estado.EJECUCION)

    # Requisito 3: si el recurso está ocupado, el proceso pasa por Ejecución
    # y se bloquea sin descontar tiempo de CPU.
    def test_proceso_con_recurso_ocupado_se_bloquea_sin_consumir_cpu(self):
        simulador = Simulador(8, 16, probabilidad_soltar_recurso=0)
        primero = simulador.crear_proceso("Uno", 2, "Impresora", 1, 3)
        segundo = simulador.crear_proceso("Dos", 2, "Impresora", 1, 3)
        self.assertEqual(primero.estado, Estado.EJECUCION)

        restantes_segundo = segundo.restantes
        simulador.avanzar()

        self.assertEqual(segundo.estado, Estado.BLOQUEADO)
        self.assertEqual(segundo.restantes, restantes_segundo)
        self.assertEqual(segundo.espera_recurso, "Impresora")
        self.assertEqual(simulador._recursos_ocupados.get("Impresora"), primero.id)

    # Requisito 4: con competencia, el proceso puede soltar el recurso al
    # terminar su turno y pasa a Bloqueado hasta que vuelva a liberarse.
    def test_proceso_suelta_recurso_al_competir_y_se_bloquea(self):
        simulador = Simulador(8, 16, probabilidad_soltar_recurso=1)
        primero = simulador.crear_proceso("Uno", 2, "Impresora", 1, 3)
        segundo = simulador.crear_proceso("Dos", 2, "Impresora", 1, 3)

        simulador.avanzar()

        self.assertEqual(primero.estado, Estado.BLOQUEADO)
        self.assertEqual(primero.espera_recurso, "Impresora")
        self.assertEqual(segundo.estado, Estado.EJECUCION)
        self.assertEqual(simulador._recursos_ocupados.get("Impresora"), segundo.id)

    # Requisito 4: si es el único que usa el recurso, no lo suelta.
    def test_proceso_solitario_no_suelta_el_recurso(self):
        simulador = Simulador(8, 16, probabilidad_soltar_recurso=1)
        unico = simulador.crear_proceso("Unico", 2, "Impresora", 1, 3)

        simulador.avanzar()

        self.assertNotEqual(unico.estado, Estado.BLOQUEADO)
        self.assertEqual(simulador._recursos_ocupados.get("Impresora"), unico.id)

    # Requisito 4: el recurso alterna entre los competidores (no hay bloqueo eterno).
    def test_recurso_alterna_entre_procesos_competidores(self):
        simulador = Simulador(8, 16, probabilidad_soltar_recurso=1)
        primero = simulador.crear_proceso("Uno", 2, "Impresora", 1, 6)
        segundo = simulador.crear_proceso("Dos", 2, "Impresora", 1, 6)

        propietarios = set()
        for _ in range(6):
            simulador.avanzar()
            propietario = simulador._recursos_ocupados.get("Impresora")
            if propietario:
                propietarios.add(propietario)

        self.assertEqual(propietarios, {primero.id, segundo.id})

    # Requisito 4: liberar un recurso solo desbloquea a quien lo espera.
    def test_liberar_recurso_solo_desbloquea_a_quien_lo_espera(self):
        simulador = Simulador(32, 64, probabilidad_soltar_recurso=0)
        uno = simulador.crear_proceso("Uno", 2, "Impresora", 1, 5)
        dos = simulador.crear_proceso("Dos", 2, "Impresora", 1, 3)
        simulador.crear_proceso("Tres", 2, "Disco", 1, 5)
        cuatro = simulador.crear_proceso("Cuatro", 2, "Disco", 1, 3)

        simulador.avanzar()  # Uno cede turno; Dos se bloquea por la Impresora
        simulador.avanzar()  # Tres cede turno; Cuatro se bloquea por el Disco
        self.assertEqual(dos.estado, Estado.BLOQUEADO)
        self.assertEqual(cuatro.estado, Estado.BLOQUEADO)

        while uno.estado != Estado.TERMINADO:
            simulador.avanzar()

        # Al terminar Uno se libera la Impresora: Dos se desbloquea, Cuatro no.
        self.assertNotEqual(dos.estado, Estado.BLOQUEADO)
        self.assertEqual(cuatro.estado, Estado.BLOQUEADO)
        self.assertEqual(cuatro.espera_recurso, "Disco")

    # Requisito 5: ante una llegada simultánea, el orden es
    # Ejecución > Bloqueado > Nuevo.
    def test_prioridad_de_cola_por_origen_en_llegada_simultanea(self):
        simulador = Simulador(16, 32)
        ejecutando = simulador.crear_proceso("Base", 1, "Ninguno", 1, 9)
        nuevo = simulador.crear_proceso("Nuevo", 1, "Ninguno", 1, 9)
        bloqueado = simulador.crear_proceso("Bloqueado", 1, "Ninguno", 1, 9)

        simulador._cola_listos.clear()
        simulador._instante = 100  # forzamos que los tres lleguen en el mismo instante
        simulador._encolar(nuevo.id, ORIGEN_NUEVO)
        simulador._encolar(bloqueado.id, ORIGEN_BLOQUEADO)
        simulador._encolar(ejecutando.id, ORIGEN_EJECUCION)

        self.assertEqual(
            simulador._cola_listos,
            [ejecutando.id, bloqueado.id, nuevo.id],
        )


if __name__ == "__main__":
    unittest.main()
