"""
Actualización automática semanal.

Uso: dejarlo corriendo en una terminal, o —mejor— usar el Programador de
tareas de Windows con configurar-automatico.bat, que no requiere que la
terminal quede abierta.
"""
import time
import logging
import schedule

from actualizar import actualizar_todo

logger = logging.getLogger(__name__)


def tarea():
    try:
        actualizar_todo()
    except Exception:
        logger.exception("Falló la actualización semanal")


if __name__ == "__main__":
    schedule.every().monday.at("10:00").do(tarea)
    logger.info("Scheduler activo: actualiza cada lunes a las 10:00.")
    while True:
        schedule.run_pending()
        time.sleep(60)
