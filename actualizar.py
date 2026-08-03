"""
Actualización completa: catálogo NBRA + búsqueda de convocatorias.
Se ejecuta manualmente o desde scheduler.py (semanalmente).
"""
import os
import logging
from datetime import datetime

from boletin import enviar_boletin
from catalogo import actualizar_catalogo
from convocatorias import buscar_convocatorias
from indizacion import actualizar_indizacion
from permanentes import detectar_permanentes
from externas import importar as importar_externas
from manuales import cargar as cargar_manuales
from latinrev import cosechar as cosechar_latinrev

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[logging.FileHandler('actualizaciones.log', encoding='utf-8'),
              logging.StreamHandler()])
logger = logging.getLogger(__name__)


def actualizar_todo():
    logger.info("=" * 60)
    logger.info("ACTUALIZACIÓN INICIADA %s", datetime.now())

    cat = actualizar_catalogo()
    logger.info("Catálogo NBRA: %s revistas (%s nuevas, %s con sitio)",
                cat['guardadas'], cat['nuevas'], cat['con_sitio'])

    ext = importar_externas()
    logger.info("Externas: %s revistas (%s Nivel 1, %s Scopus, %s SciELO, "
                "%s sin confirmar Scopus)",
                ext['total'], ext['nivel1'], ext['scopus'], ext['scielo'],
                len(ext['discrepancias']))

    conv = buscar_convocatorias()
    logger.info("Convocatorias: %s halladas (%s nuevas) en %s revistas; "
                "%s vencidas archivadas",
                conv['convocatorias'], conv['nuevas'],
                conv['estados'].get('ok', 0), conv['vencidas_desactivadas'])

    perm = detectar_permanentes()
    logger.info("Recepción permanente: %s revistas de %s revisadas",
                perm['permanentes'], perm['revisadas'])

    # LatinREV agrega convocatorias que no están en la página de anuncios de
    # cada revista. Si el sitio no responde, se informa y se sigue.
    lat = cosechar_latinrev()
    if lat['disponible']:
        logger.info("LatinREV: %s convocatorias (%s nuevas, %s revistas nuevas)",
                    lat['convocatorias'], lat['nuevas'], lat['revistas_nuevas'])
    else:
        logger.warning("LatinREV sin datos: %s", lat['motivo'])

    # Después del rastreo: lo verificado a mano no se pierde y pisa lo que el
    # rastreador no pudo leer (sitios con anti-bot, convocatorias en PDF).
    man = cargar_manuales()
    logger.info("Carga manual: %s permanentes, %s convocatorias",
                man['permanentes'], man['convocatorias'])

    ind = actualizar_indizacion()
    logger.info("Indización: Nivel 1 %s, Nivel 2 %s | Scopus %s, SciELO %s, DOAJ %s",
                ind['nivel1'], ind['nivel2'], ind['scopus'], ind['scielo'], ind['doaj'])

    # El sitio se regenera acá, con la base local, que es la más completa:
    # tiene lo que el robot de GitHub no puede conseguir. Para publicarlo hay
    # que correr publicar.bat, que además hace el push.
    from generar_sitio import generar
    ruta_sitio, stats_sitio, _, _ = generar()
    logger.info("Sitio regenerado: %s revistas, %s convocatorias",
                stats_sitio['revistas'], stats_sitio['convocatorias'])

    # El boletín va último: necesita los datos ya actualizados.
    bol = enviar_boletin()
    logger.info("Boletín: informe %s; %s correo(s) enviado(s)%s",
                os.path.basename(bol['informe']), bol['enviados'],
                "" if bol['correo_configurado'] else " (correo sin configurar)")

    logger.info("ACTUALIZACIÓN COMPLETADA")
    return cat, ext, conv, perm, man, ind, bol


if __name__ == "__main__":
    actualizar_todo()
