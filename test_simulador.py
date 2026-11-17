import unittest

from simulador import (
    ORIGEN_BLOQUEADO,
    ORIGEN_EJECUCION,
    ORIGEN_NUEVO,
    Estado,
    Simulador,
)


class SimuladorTests(unittest.TestCase):
    def test_lista_recursos_parsea_por_comas(self):
        self.assertEqual(
            Simulador._lista_recursos("Impresora, Disco"), ["Impresora", "Disco"]
        )
        self.assertEqual(Simulador._lista_recursos("Ninguno"), [])
        self.assertEqual(Simulador._lista_recursos(""), [])
        self.assertEqual(Simulador._lista_recursos("Disco, Disco"), ["Disco"])
        self.assertEqual(
            Simulador._lista_recursos("  Impresora ,  , Disco , Ninguno"),
            ["Impresora", "Disco"],
        )

    def test_procesos_se_atienden_por_orden_de_llegada(self):
        simulador = Simulador(16, 32)
        primero = simulador.crear_proceso("Primero", 2, "", False, 3)
        segundo = simulador.crear_proceso("Segundo", 2, "", False, 2)

        self.assertEqual(simulador.proceso_ejecutando.id, primero.id)
        simulador.avanzar()
        self.assertEqual(simulador.proceso_ejecutando.id, segundo.id)
        simulador.avanzar()
        self.assertEqual(simulador.proceso_ejecutando.id, primero.id)
        simulador.avanzar()
        self.assertEqual(segundo.estado, Estado.EJECUCION)

    def test_creacion_rechaza_si_no_hay_espacio_contiguo(self):
        simulador = Simulador(4, 8)
        simulador.crear_proceso("Uno", 3, "", False, 3)
        with self.assertRaisesRegex(ValueError, "memoria"):
            simulador.crear_proceso("Dos", 2, "", False, 1)

    def test_suspender_libera_memoria_y_reanudar_la_reserva(self):
        simulador = Simulador(4, 8)
        proceso = simulador.crear_proceso("Trabajo", 3, "Disco", False, 2)
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
        primero = simulador.crear_proceso("Primero", 2, "", False, 2)
        segundo = simulador.crear_proceso("Segundo", 2, "", False, 2)
        simulador.suspender(segundo.id)

        self.assertEqual(segundo.estado, Estado.LISTO_SUSPENDIDO)
        simulador.reanudar(segundo.id)
        self.assertEqual(segundo.estado, Estado.LISTO)
        self.assertEqual(simulador.proceso_ejecutando.id, primero.id)
        simulador.avanzar()
        self.assertEqual(simulador.proceso_ejecutando.id, segundo.id)

    def test_bloqueo_y_desbloqueo_cambian_estado(self):
        simulador = Simulador(8, 16)
        proceso = simulador.crear_proceso("Trabajo", 2, "", False, 2)
        simulador.bloquear_ejecucion()
        self.assertEqual(proceso.estado, Estado.BLOQUEADO)
        simulador.desbloquear(proceso.id)
        self.assertEqual(proceso.estado, Estado.EJECUCION)

    def test_proceso_terminado_libera_memoria_y_almacenamiento(self):
        simulador = Simulador(4, 4)
        proceso = simulador.crear_proceso("Fin", 4, "", False, 1)
        simulador.avanzar()

        self.assertEqual(proceso.estado, Estado.TERMINADO)
        self.assertEqual(simulador.segmentos_memoria(), [(0, 3, None)])
        self.assertEqual(simulador.segmentos_almacenamiento(), [(0, 3, None)])


    # Requisito 2: un proceso sin recurso pasa directo a Ejecución.
    def test_proceso_sin_recurso_entra_a_ejecucion(self):
        simulador = Simulador(8, 16)
        proceso = simulador.crear_proceso("SinRecurso", 2, "Ninguno", False, 2)

        self.assertEqual(proceso.estado, Estado.EJECUCION)

    # Requisito 3: si el recurso está ocupado, el proceso pasa por Ejecución
    # y se bloquea sin descontar tiempo de CPU.
    def test_proceso_con_recurso_ocupado_se_bloquea_sin_consumir_cpu(self):
        simulador = Simulador(8, 16, probabilidad_soltar_recurso=0)
        primero = simulador.crear_proceso("Uno", 2, "Impresora", False, 3)
        segundo = simulador.crear_proceso("Dos", 2, "Impresora", False, 3)
        self.assertEqual(primero.estado, Estado.EJECUCION)

        restantes_segundo = segundo.restantes
        simulador.avanzar()

        self.assertEqual(segundo.estado, Estado.BLOQUEADO)
        self.assertEqual(segundo.restantes, restantes_segundo)
        self.assertIn("Impresora", segundo.espera_recursos)
        self.assertEqual(simulador._recursos_ocupados.get("Impresora"), primero.id)

    # Requisito 3 (secuencia explícita): el proceso recorre Listo → Ejecución →
    # Bloqueado sin descontar pasadas, y lo deja constar en un único evento legible.
    def test_bloqueo_por_recurso_pasa_por_listo_sin_consumir_cpu(self):
        simulador = Simulador(8, 16, probabilidad_soltar_recurso=0)
        primero = simulador.crear_proceso("Uno", 2, "Impresora", False, 3)
        segundo = simulador.crear_proceso("Dos", 2, "Impresora", False, 3)

        restantes_segundo = segundo.restantes
        simulador.avanzar()

        self.assertEqual(segundo.estado, Estado.BLOQUEADO)
        self.assertIn("Impresora", segundo.espera_recursos)
        self.assertEqual(segundo.restantes, restantes_segundo)
        self.assertEqual(simulador._recursos_ocupados.get("Impresora"), primero.id)

        evento = next(
            e for e in simulador.eventos if segundo.id in e and "sin consumir CPU" in e
        )
        self.assertIn("Listo", evento)
        self.assertIn("Ejecución", evento)
        self.assertIn("Bloqueado", evento)
        self.assertIn("sin consumir CPU", evento)
        self.assertIn(segundo.id, evento)
        self.assertIn("Impresora", evento)
        self.assertIn(primero.id, evento)

    # Requisito 4: con competencia, el proceso puede soltar el recurso al
    # terminar su turno y pasa a Bloqueado hasta que vuelva a liberarse.
    def test_proceso_suelta_recurso_al_competir_y_se_bloquea(self):
        simulador = Simulador(8, 16, probabilidad_soltar_recurso=1)
        primero = simulador.crear_proceso("Uno", 2, "Impresora", False, 3)
        segundo = simulador.crear_proceso("Dos", 2, "Impresora", False, 3)

        simulador.avanzar()

        self.assertEqual(primero.estado, Estado.BLOQUEADO)
        self.assertIn("Impresora", primero.espera_recursos)
        self.assertEqual(segundo.estado, Estado.EJECUCION)
        self.assertEqual(simulador._recursos_ocupados.get("Impresora"), segundo.id)

    # Requisito 4: si es el único que usa el recurso, no lo suelta.
    def test_proceso_solitario_no_suelta_el_recurso(self):
        simulador = Simulador(8, 16, probabilidad_soltar_recurso=1)
        unico = simulador.crear_proceso("Unico", 2, "Impresora", False, 3)

        simulador.avanzar()

        self.assertNotEqual(unico.estado, Estado.BLOQUEADO)
        self.assertEqual(simulador._recursos_ocupados.get("Impresora"), unico.id)

    # Requisito 4: el recurso alterna entre los competidores (no hay bloqueo eterno).
    def test_recurso_alterna_entre_procesos_competidores(self):
        simulador = Simulador(8, 16, probabilidad_soltar_recurso=1)
        primero = simulador.crear_proceso("Uno", 2, "Impresora", False, 6)
        segundo = simulador.crear_proceso("Dos", 2, "Impresora", False, 6)

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
        uno = simulador.crear_proceso("Uno", 2, "Impresora", False, 5)
        dos = simulador.crear_proceso("Dos", 2, "Impresora", False, 3)
        simulador.crear_proceso("Tres", 2, "Disco", False, 5)
        cuatro = simulador.crear_proceso("Cuatro", 2, "Disco", False, 3)

        simulador.avanzar()  # Uno cede turno; Dos se bloquea por la Impresora
        simulador.avanzar()  # Tres cede turno; Cuatro se bloquea por el Disco
        self.assertEqual(dos.estado, Estado.BLOQUEADO)
        self.assertEqual(cuatro.estado, Estado.BLOQUEADO)

        while uno.estado != Estado.TERMINADO:
            simulador.avanzar()

        # Al terminar Uno se libera la Impresora: Dos se desbloquea, Cuatro no.
        self.assertNotEqual(dos.estado, Estado.BLOQUEADO)
        self.assertEqual(cuatro.estado, Estado.BLOQUEADO)
        self.assertIn("Disco", cuatro.espera_recursos)

    # Requisito 5: ante una llegada simultánea, el orden es
    # Ejecución > Bloqueado > Nuevo.
    def test_prioridad_de_cola_por_origen_en_llegada_simultanea(self):
        simulador = Simulador(16, 32)
        ejecutando = simulador.crear_proceso("Base", 1, "Ninguno", False, 9)
        nuevo = simulador.crear_proceso("Nuevo", 1, "Ninguno", False, 9)
        bloqueado = simulador.crear_proceso("Bloqueado", 1, "Ninguno", False, 9)

        simulador._cola_listos.clear()
        simulador._instante = 100  # forzamos que los tres lleguen en el mismo instante
        simulador._encolar(nuevo.id, ORIGEN_NUEVO)
        simulador._encolar(bloqueado.id, ORIGEN_BLOQUEADO)
        simulador._encolar(ejecutando.id, ORIGEN_EJECUCION)

        self.assertEqual(
            simulador._cola_listos,
            [ejecutando.id, bloqueado.id, nuevo.id],
        )

    # Prioridad: un Prioritario se coloca delante de los No prioritarios en la
    # cola de Listos, respetando FIFO entre los de la misma prioridad.
    def test_prioritario_se_ordena_antes_en_la_cola(self):
        simulador = Simulador(16, 32)
        # Un Prioritario ocupa la CPU (no será desalojado por otro Prioritario),
        # así los demás quedan en la cola de Listos para observar su orden.
        simulador.crear_proceso("EnCPU", 1, "Ninguno", True, 9)
        normal1 = simulador.crear_proceso("Normal1", 1, "Ninguno", False, 9)
        normal2 = simulador.crear_proceso("Normal2", 1, "Ninguno", False, 9)
        prio = simulador.crear_proceso("Prio", 1, "Ninguno", True, 9)

        # El Prioritario, aun llegando último, va al frente de la cola de Listos;
        # los No prioritarios conservan su orden de llegada (FIFO) detrás.
        self.assertEqual(
            simulador._cola_listos, [prio.id, normal1.id, normal2.id]
        )

    # Prioridad preemptiva: un Prioritario que llega desaloja al No prioritario
    # en Ejecución, que vuelve a Listo sin perder su pasada.
    def test_prioritario_desaloja_a_no_prioritario_en_ejecucion(self):
        simulador = Simulador(16, 32)
        normal = simulador.crear_proceso("Normal", 1, "Ninguno", False, 9)
        self.assertEqual(normal.estado, Estado.EJECUCION)
        restantes_normal = normal.restantes

        prio = simulador.crear_proceso("Prio", 1, "Ninguno", True, 9)

        self.assertEqual(prio.estado, Estado.EJECUCION)
        self.assertEqual(normal.estado, Estado.LISTO)
        # El desalojado no perdió ninguna pasada.
        self.assertEqual(normal.restantes, restantes_normal)

    # Prioridad: un Prioritario NO desaloja a otro Prioritario en Ejecución.
    def test_prioritario_no_desaloja_a_otro_prioritario(self):
        simulador = Simulador(16, 32)
        prio1 = simulador.crear_proceso("Prio1", 1, "Ninguno", True, 9)
        self.assertEqual(prio1.estado, Estado.EJECUCION)

        prio2 = simulador.crear_proceso("Prio2", 1, "Ninguno", True, 9)

        self.assertEqual(prio1.estado, Estado.EJECUCION)
        self.assertEqual(prio2.estado, Estado.LISTO)

    # Multi-recurso: si uno de los recursos requeridos está ocupado, el proceso
    # no adquiere ninguno (todo-o-nada) y espera solo por el que falta.
    def test_multirecurso_todo_o_nada_bloquea_si_falta_uno(self):
        simulador = Simulador(16, 32, probabilidad_soltar_recurso=0)
        uno = simulador.crear_proceso("Uno", 2, "Disco", False, 3)
        dos = simulador.crear_proceso("Dos", 2, "Impresora, Disco", False, 3)

        self.assertEqual(uno.estado, Estado.EJECUCION)
        restantes_dos = dos.restantes
        simulador.avanzar()

        self.assertEqual(dos.estado, Estado.BLOQUEADO)
        self.assertEqual(dos.restantes, restantes_dos)
        # Solo falta el Disco (ocupado por Uno); no adquirió la Impresora.
        self.assertEqual(dos.espera_recursos, {"Disco"})
        self.assertNotIn("Impresora", simulador._recursos_ocupados)

    # Multi-recurso: con todos los recursos libres, los adquiere todos juntos.
    def test_multirecurso_adquiere_todos_si_estan_libres(self):
        simulador = Simulador(16, 32)
        proc = simulador.crear_proceso("Multi", 2, "Impresora, Disco", False, 3)

        self.assertEqual(proc.estado, Estado.EJECUCION)
        self.assertEqual(simulador._recursos_ocupados.get("Impresora"), proc.id)
        self.assertEqual(simulador._recursos_ocupados.get("Disco"), proc.id)

    # Multi-recurso: un proceso bloqueado por dos recursos de dueños distintos
    # solo despierta cuando ya no le falta ninguno.
    def test_multirecurso_desbloqueo_escalonado(self):
        simulador = Simulador(32, 64, probabilidad_soltar_recurso=0)
        duenoA = simulador.crear_proceso("DuenoA", 2, "Impresora", False, 3)
        duenoB = simulador.crear_proceso("DuenoB", 2, "Disco", False, 5)
        espera = simulador.crear_proceso("Espera", 2, "Impresora, Disco", False, 2)

        # DuenoA y DuenoB se turnan; cuando Espera intenta, ambos recursos
        # están ocupados, así que queda bloqueado esperando los dos.
        simulador.avanzar()
        simulador.avanzar()
        self.assertEqual(espera.estado, Estado.BLOQUEADO)
        self.assertEqual(espera.espera_recursos, {"Impresora", "Disco"})

        # Termina DuenoA (3 pasadas): libera Impresora, pero aún falta Disco.
        while duenoA.estado != Estado.TERMINADO:
            simulador.avanzar()
        self.assertEqual(espera.estado, Estado.BLOQUEADO)
        self.assertEqual(espera.espera_recursos, {"Disco"})

        # Termina DuenoB: se libera Disco; ya no falta ninguno -> despierta.
        while duenoB.estado != Estado.TERMINADO:
            simulador.avanzar()
        self.assertNotEqual(espera.estado, Estado.BLOQUEADO)
        self.assertEqual(espera.espera_recursos, set())

    # Multi-recurso (regla 2=c): al competir, suelta solo los recursos disputados
    # y conserva los que nadie más necesita.
    def test_multirecurso_suelta_solo_los_disputados(self):
        simulador = Simulador(32, 64, probabilidad_soltar_recurso=1)
        dueno = simulador.crear_proceso("Dueno", 2, "Impresora, Disco", False, 4)
        rival = simulador.crear_proceso("Rival", 2, "Disco", False, 4)

        simulador.avanzar()  # Dueno completa una pasada; Disco tiene competencia

        self.assertEqual(dueno.estado, Estado.BLOQUEADO)
        self.assertEqual(dueno.espera_recursos, {"Disco"})
        # Conserva la Impresora (nadie la disputa).
        self.assertEqual(simulador._recursos_ocupados.get("Impresora"), dueno.id)
        # Soltó el Disco: ahora lo tiene el rival.
        self.assertEqual(simulador._recursos_ocupados.get("Disco"), rival.id)

    # Multi-recurso: un proceso solitario con varios recursos no suelta ninguno.
    def test_multirecurso_solitario_no_suelta(self):
        simulador = Simulador(16, 32, probabilidad_soltar_recurso=1)
        solo = simulador.crear_proceso("Solo", 2, "Impresora, Disco", False, 3)

        simulador.avanzar()

        self.assertNotEqual(solo.estado, Estado.BLOQUEADO)
        self.assertEqual(simulador._recursos_ocupados.get("Impresora"), solo.id)
        self.assertEqual(simulador._recursos_ocupados.get("Disco"), solo.id)


if __name__ == "__main__":
    unittest.main()
