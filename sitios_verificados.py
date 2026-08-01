"""
Incorpora sitios oficiales verificados desde un CSV de relevamiento.

El ranking de SCImago no publica la dirección de las revistas, así que muchas
entraron al catálogo sin sitio y quedaron como referencia: el rastreador no
podía seguir sus convocatorias. Este módulo carga los CSV donde cada revista
trae su sitio oficial y cómo se lo verificó.

Formato esperado (separador ';'):
    Revista · ISSN · Editorial · País · Sitio web oficial ·
    Estado de verificación · Fuente de verificación · Observación

El emparejamiento es por ISSN, que es inequívoco. Si la revista no está en el
catálogo se incorpora; si está, solo se completa lo que falte —nunca se pisa
un sitio ya verificado por otra vía.
"""
import os
import re
import csv
import glob
import logging
from datetime import datetime

from database import init_db, conectar, registrar_actualizacion

logger = logging.getLogger(__name__)

BASE = os.path.dirname(os.path.abspath(__file__))
CARPETAS = [os.path.join(BASE, 'datos'), r"D:\DESCARGAS"]
PATRON = "nuevas_revistas_*.csv"

PAISES = {
    'Argentina': 'Argentina', 'Brazil': 'Brasil', 'Chile': 'Chile',
    'Colombia': 'Colombia', 'Mexico': 'México', 'México': 'México',
    'Peru': 'Perú', 'Perú': 'Perú', 'Venezuela': 'Venezuela',
    'Ecuador': 'Ecuador', 'Cuba': 'Cuba', 'Costa Rica': 'Costa Rica',
    'Uruguay': 'Uruguay', 'Paraguay': 'Paraguay', 'Bolivia': 'Bolivia',
    'Panama': 'Panamá', 'Panamá': 'Panamá', 'Puerto Rico': 'Puerto Rico',
    'Spain': 'España', 'España': 'España', 'Portugal': 'Portugal',
}


def archivos():
    out = []
    for c in CARPETAS:
        if os.path.isdir(c):
            out += glob.glob(os.path.join(c, PATRON))
    vistos, unicos = set(), []
    for a in sorted(out):
        n = os.path.basename(a).lower()
        if n not in vistos:
            vistos.add(n)
            unicos.append(a)
    return unicos


def _issns(campo):
    out = []
    for bruto in str(campo or '').split(','):
        n = re.sub(r'[^0-9Xx]', '', bruto).upper()
        if len(n) == 8:
            out.append(f"{n[:4]}-{n[4:]}")
    return out


def _columna(fila, *nombres):
    for n in nombres:
        for k in fila:
            if k and k.strip().lower() == n.lower():
                return (fila[k] or '').strip()
    return ''


def importar(aplicar=True):
    init_db()
    rutas = archivos()
    if not rutas:
        logger.warning("No se encontró ningún CSV de sitios verificados.")
        return dict(leidas=0, sitios=0, nuevas=0, sin_issn=0, detalle=[])

    conn = conectar()
    leidas = sitios = nuevas = sin_issn = 0
    detalle = []

    for ruta in rutas:
        with open(ruta, encoding='utf-8-sig') as f:
            for fila in csv.DictReader(f, delimiter=';'):
                nombre = _columna(fila, 'Revista', 'Title', 'Titulo')
                sitio = _columna(fila, 'Sitio web oficial', 'Sitio', 'URL')
                if not nombre or not sitio.startswith('http'):
                    continue
                leidas += 1

                issns = _issns(_columna(fila, 'ISSN', 'Issn'))
                if not issns:
                    sin_issn += 1
                    continue

                pais_csv = _columna(fila, 'País', 'Pais', 'Country')
                pais = PAISES.get(pais_csv, pais_csv or None)
                editorial = _columna(fila, 'Editorial', 'Publisher')
                verif = _columna(fila, 'Estado de verificación',
                                 'Estado de verificacion')
                fuente = _columna(fila, 'Fuente de verificación',
                                  'Fuente de verificacion')

                marcas = ','.join('?' * len(issns))
                f_rev = conn.execute(
                    f"""SELECT id, nombre, sitio_url FROM revistas
                        WHERE issn_impreso IN ({marcas})
                           OR issn_online IN ({marcas}) LIMIT 1""",
                    issns * 2).fetchone()

                if f_rev:
                    # Solo se completa lo que falta: un sitio ya verificado por
                    # el rastreo o por el NBRA no se pisa.
                    if (f_rev['sitio_url'] or '').strip():
                        continue
                    if aplicar:
                        conn.execute(
                            """UPDATE revistas SET sitio_url=?,
                               resolucion=COALESCE(NULLIF(resolucion,''), ?)
                               WHERE id=?""",
                            (sitio, f"sitio {verif.lower()} · {fuente}"[:250],
                             f_rev['id']))
                    sitios += 1
                    detalle.append(f"sitio  {f_rev['nombre'][:40]:42} {sitio[:52]}")
                else:
                    if aplicar:
                        try:
                            conn.execute(
                                """INSERT INTO revistas
                                   (nombre, pais, institucion, sitio_url,
                                    issn_impreso, issn_online, origen, area,
                                    indexacion_declarada, resolucion,
                                    fecha_actualizada, en_scimago, en_scopus,
                                    scopus_estado, nivel_conicet)
                                   VALUES (?,?,?,?,?,?,'externa',?,?,?,?,1,1,
                                           'Active',1)""",
                                (nombre, pais, editorial, sitio, issns[0],
                                 issns[1] if len(issns) > 1 else '',
                                 'Ciencias Sociales y Humanidades',
                                 'SCImago · Scopus',
                                 f"sitio {verif.lower()} · {fuente}"[:250],
                                 datetime.now()))
                        except Exception as e:
                            logger.warning("No se pudo agregar %s: %s",
                                           nombre[:36], e)
                            continue
                    nuevas += 1
                    detalle.append(f"NUEVA  {nombre[:40]:42} {sitio[:52]}")

    if aplicar:
        conn.commit()
        registrar_actualizacion(
            "sitios", f"{sitios} sitios completados y {nuevas} revistas "
                      f"incorporadas desde CSV de relevamiento")
    conn.close()
    return dict(leidas=leidas, sitios=sitios, nuevas=nuevas,
                sin_issn=sin_issn, detalle=detalle)


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
    solo_ver = '--ver' in sys.argv
    print("archivos:")
    for a in archivos():
        print("  ", os.path.basename(a))
    r = importar(aplicar=not solo_ver)
    print(f"\nfilas con sitio: {r['leidas']}")
    print(f"  sitios completados : {r['sitios']}")
    print(f"  revistas nuevas    : {r['nuevas']}")
    if r['sin_issn']:
        print(f"  sin ISSN (omitidas): {r['sin_issn']}")
    print()
    for d in r['detalle'][:20]:
        print("  ", d)
    if len(r['detalle']) > 20:
        print(f"   ... y {len(r['detalle'])-20} más")
