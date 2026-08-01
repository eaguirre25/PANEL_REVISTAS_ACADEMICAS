"""
Recalcula sobre las convocatorias ya guardadas los campos que se derivan del
texto: si es dossier, su tema, cuándo reabre y si la revista sigue recibiendo.

Sirve para aplicar mejoras en la extracción sin volver a recorrer los ~500
sitios: el título y la descripción ya están en la base.
"""
import logging
from database import init_db, conectar, registrar_actualizacion
from convocatorias import (ES_DOSSIER, extraer_tema, extraer_reapertura,
                           sigue_recibiendo)

logger = logging.getLogger(__name__)


def recalcular():
    init_db()
    conn = conectar()
    filas = conn.execute(
        "SELECT id, titulo, descripcion FROM convocatorias").fetchall()

    dossiers = con_tema = con_reapertura = con_continuidad = 0
    for f in filas:
        desc = f['descripcion'] or ''
        es_dossier = bool(ES_DOSSIER.search(f['titulo'] or '')
                          or ES_DOSSIER.search(desc[:400]))
        tema = extraer_tema(f['titulo'] or '', desc) if es_dossier else None
        reapertura = extraer_reapertura(desc)
        continua = 1 if sigue_recibiendo(desc) else 0

        conn.execute("""UPDATE convocatorias SET es_dossier=?, tema=?,
                        fecha_reapertura=?, sigue_recibiendo=? WHERE id=?""",
                     (1 if es_dossier else 0, tema, reapertura, continua,
                      f['id']))
        dossiers += es_dossier
        con_tema += bool(tema)
        con_reapertura += bool(reapertura)
        con_continuidad += continua

    conn.commit()
    conn.close()
    registrar_actualizacion(
        "temas", f"{dossiers} dossiers, {con_tema} con tema, "
                 f"{con_reapertura} con fecha de reapertura, "
                 f"{con_continuidad} que siguen recibiendo")
    return dict(total=len(filas), dossiers=dossiers, con_tema=con_tema,
                con_reapertura=con_reapertura, con_continuidad=con_continuidad)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
    r = recalcular()
    for k, v in r.items():
        print(f"  {k}: {v}")
