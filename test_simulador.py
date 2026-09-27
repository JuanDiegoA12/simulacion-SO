import unittest

from simulador import Estado, Simulador


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


if __name__ == "__main__":
    unittest.main()
