"""
Carga en la base los datos verificados a mano de datos_manuales.py.

Corre después del rastreo, en cada actualización: así lo cargado a mano no se
pierde y convive con lo detectado automáticamente. Las convocatorias quedan
marcadas con fuente 'manual', para poder distinguirlas.
"""
import logging
from datetime import date, timedelta

from database import (init_db, conectar, guardar_convocatoria,
                      marcar_recepcion_permanente, registrar_actualizacion,
                      desactivar_convocatorias_vencidas)
from datos_manuales import PERMANENTES, CONVOCATORIAS

logger = logging.getLogger(__name__)

# Una fecha más lejana que esto no es un plazo: es un tope administrativo con
# el que la revista declara recepción abierta (p. ej. 31/12/2029). Mostrarla
# diría «cierra en 780 días». Se guarda sin fecha; la descripción lo explica.
TOPE_DIAS = 366


def _id_revista(conn, nombre):
    """Busca la revista por nombre exacto y, si no, por coincidencia parcial."""
    f = conn.execute("SELECT id FROM revistas WHERE nombre = ?",
                     (nombre,)).fetchone()
    if f:
        return f['id']
    f = conn.execute("SELECT id FROM revistas WHERE nombre LIKE ? LIMIT 2",
                     (f'%{nombre}%',)).fetchone()
    return f['id'] if f else None


def cargar():
    init_db()
    conn = conectar()

    permanentes, convocatorias, faltantes = 0, 0, []

    for nombre, frase, fuente in PERMANENTES:
        rid = _id_revista(conn, nombre)
        if not rid:
            faltantes.append(f"permanente: {nombre}")
            continue
        marcar_recepcion_permanente(rid, True, f"{frase}  [fuente: {fuente}]")
        permanentes += 1

    for c in CONVOCATORIAS:
        rid = _id_revista(conn, c['revista'])
        if not rid:
            faltantes.append(f"convocatoria: {c['revista']}")
            continue
        fecha = c.get('fecha_cierre')
        if fecha and fecha > (date.today() + timedelta(days=TOPE_DIAS)).isoformat():
            fecha = None
        guardar_convocatoria(
            rid, c['titulo'], c.get('descripcion', ''), fecha,
            c.get('url', ''), f"manual · {c.get('fuente', '')}",
            es_dossier=1 if 'dossier' in c['titulo'].lower() else 0,
            tema=c.get('tema'))
        convocatorias += 1

    conn.close()

    # Lo cargado a mano llega DESPUÉS del rastreo, que es quien archiva las
    # vencidas: sin este paso, una convocatoria manual con plazo pasado queda
    # «abierta» para siempre.
    vencidas = desactivar_convocatorias_vencidas()

    if faltantes:
        logger.warning("No se encontraron en el catálogo: %s", faltantes)

    registrar_actualizacion(
        "manuales",
        f"{permanentes} recepciones permanentes y {convocatorias} convocatorias "
        f"cargadas a mano ({vencidas} vencidas archivadas)"
        + (f"; {len(faltantes)} sin revista en el catálogo" if faltantes else ""))
    return dict(permanentes=permanentes, convocatorias=convocatorias,
                vencidas=vencidas, faltantes=faltantes)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
    r = cargar()
    print("permanentes cargadas :", r['permanentes'])
    print("convocatorias cargadas:", r['convocatorias'])
    for f in r['faltantes']:
        print("  sin revista en el catálogo ->", f)
