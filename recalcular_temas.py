"""
Recalcula es_dossier y tema sobre las convocatorias ya guardadas.

Sirve para aplicar mejoras en la extracción sin volver a recorrer los ~500
sitios: el título y la descripción ya están en la base.
"""
import logging
from database import init_db, conectar, registrar_actualizacion
from convocatorias import ES_DOSSIER, extraer_tema

logger = logging.getLogger(__name__)


def recalcular():
    init_db()
    conn = conectar()
    filas = conn.execute(
        "SELECT id, titulo, descripcion FROM convocatorias").fetchall()

    dossiers = con_tema = 0
    for f in filas:
        desc = f['descripcion'] or ''
        es_dossier = bool(ES_DOSSIER.search(f['titulo'] or '')
                          or ES_DOSSIER.search(desc[:400]))
        tema = extraer_tema(f['titulo'] or '', desc) if es_dossier else None
        conn.execute("UPDATE convocatorias SET es_dossier=?, tema=? WHERE id=?",
                     (1 if es_dossier else 0, tema, f['id']))
        dossiers += es_dossier
        con_tema += bool(tema)

    conn.commit()
    conn.close()
    registrar_actualizacion(
        "temas", f"{dossiers} dossiers, {con_tema} con tema identificado")
    return dict(total=len(filas), dossiers=dossiers, con_tema=con_tema)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
    print(recalcular())
