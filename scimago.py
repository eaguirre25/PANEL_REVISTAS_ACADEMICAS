"""
Incorpora el ranking SCImago (SJR) desde los CSV descargados del sitio.

Por qué desde archivo y no por red: la descarga de scimagojr.com está detrás
de Cloudflare, que responde 403 a cualquier cliente automatizado y presenta un
desafío de seguridad en el navegador. En vez de forzarlo, el CSV se baja a
mano desde el sitio —una vez por año, cuando sale el ranking— y se deja en
`datos/`. El módulo lo lee de ahí.

Qué aporta que no teníamos: el **cuartil** (Q1–Q4) y el valor del SJR. Hasta
ahora «SciMago» se mostraba derivado de Scopus, que es correcto como
pertenencia pero no dice en qué posición está la revista.

Uso:
    python scimago.py --ver     # qué haría, sin tocar la base
    python scimago.py           # aplica

Los archivos se buscan en datos/ y en la carpeta de descargas.
"""
import os
import re
import csv
import glob
import logging

from database import (init_db, conectar, guardar_revista_externa,
                      registrar_actualizacion)

logger = logging.getLogger(__name__)

BASE = os.path.dirname(os.path.abspath(__file__))
CARPETAS = [os.path.join(BASE, 'datos'), r"D:\DESCARGAS"]

# Solo el ranking vigente. Mezclar años daría SJR y cuartiles de ediciones
# distintas en la misma tabla, que es peor que tener menos datos.
# Para pasar a otro año, cambiar acá.
ANIO = "2025"
PATRON = f"scimagojr {ANIO}*.csv"
PATRON_TODOS = "scimagojr*.csv"

# País del CSV -> como se nombra en el panel.
PAISES = {
    'Argentina': 'Argentina', 'Brazil': 'Brasil', 'Chile': 'Chile',
    'Colombia': 'Colombia', 'Mexico': 'México', 'Peru': 'Perú',
    'Venezuela': 'Venezuela', 'Ecuador': 'Ecuador', 'Cuba': 'Cuba',
    'Costa Rica': 'Costa Rica', 'Uruguay': 'Uruguay', 'Paraguay': 'Paraguay',
    'Bolivia': 'Bolivia', 'Panama': 'Panamá', 'Puerto Rico': 'Puerto Rico',
    'Trinidad and Tobago': 'Trinidad y Tobago', 'Jamaica': 'Jamaica',
    'Spain': 'España', 'Portugal': 'Portugal',
}

# Un archivo puede traer revistas de áreas ajenas al panel: el de
# «Multidisciplinary» incluye medicina y biología. Solo entran las que
# declaran alguna de estas áreas.
AREAS_VALIDAS = re.compile(
    r'social sciences|arts and humanities|psychology|economics|'
    r'business|decision sciences', re.I)


def archivos():
    """
    CSV de SCImago disponibles, del más nuevo al más viejo.

    El orden importa: al deduplicar por ISSN gana el primero, así que los
    archivos del ranking más reciente deben ir antes. Los nombres que publica
    SCImago empiezan con el año, así que ordenar al revés alcanza.
    """
    encontrados = []
    for c in CARPETAS:
        if os.path.isdir(c):
            encontrados += glob.glob(os.path.join(c, PATRON))
    if not encontrados:
        logger.warning("No hay CSV del ranking %s; se buscan otros años.", ANIO)
        for c in CARPETAS:
            if os.path.isdir(c):
                encontrados += glob.glob(os.path.join(c, PATRON_TODOS))
    vistos, unicos = set(), []
    for a in sorted(encontrados, reverse=True):
        n = os.path.basename(a).lower()
        if n not in vistos:
            vistos.add(n)
            unicos.append(a)
    return unicos


def _issns(campo):
    """'0718090X, 07161417' -> ['0718-090X', '0716-1417']"""
    out = []
    for bruto in str(campo or '').split(','):
        n = re.sub(r'[^0-9Xx]', '', bruto).upper()
        if len(n) == 8:
            out.append(f"{n[:4]}-{n[4:]}")
    return out


def _numero(v):
    """'0,975' -> 0.975 (el CSV usa coma decimal)."""
    v = str(v or '').strip().replace(',', '.')
    try:
        return float(v)
    except ValueError:
        return None


def leer():
    """Todas las revistas de los CSV, deduplicadas por ISSN."""
    filas, por_issn = [], {}
    for ruta in archivos():
        with open(ruta, encoding='utf-8-sig') as f:
            for r in csv.DictReader(f, delimiter=';'):
                areas = r.get('Areas') or ''
                categorias = r.get('Categories') or ''
                if not AREAS_VALIDAS.search(areas + ' ' + categorias):
                    continue
                # El panel es iberoamericano. Algunos CSV que SCImago ofrece
                # por categoría son globales: sin este filtro entrarían cientos
                # de revistas del Reino Unido, EE.UU. y Países Bajos, ajenas al
                # ámbito y sin ninguna posibilidad de que el rastreador las
                # siga.
                pais_csv = (r.get('Country') or '').strip()
                if pais_csv not in PAISES:
                    continue
                issns = _issns(r.get('Issn'))
                if not issns:
                    continue
                clave = issns[0]
                if clave in por_issn:      # ya vino en otro archivo
                    continue
                titulo = (r.get('Title') or '').strip()
                # SCImago marca así las que dejó de indizar.
                discontinuada = '(discontinued)' in titulo.lower()
                por_issn[clave] = True
                filas.append(dict(
                    titulo=re.sub(r'\s*\(discontinued\)\s*$', '', titulo,
                                  flags=re.I),
                    issns=issns,
                    sjr=_numero(r.get('SJR')),
                    cuartil=(r.get('SJR Best Quartile') or '').strip(),
                    h=int(r['H index']) if str(r.get('H index','')).isdigit() else None,
                    pais=PAISES.get((r.get('Country') or '').strip(),
                                    (r.get('Country') or '').strip()),
                    editorial=(r.get('Publisher') or '').strip(),
                    areas=areas.strip(),
                    discontinuada=discontinuada,
                    archivo=os.path.basename(ruta)))
    return filas


def _por_issn(conn, issns):
    """
    Igual que database.buscar_por_issn pero sobre la conexión abierta.

    Usar la de database abriría una segunda conexión mientras esta tiene una
    transacción en curso, y SQLite responde «database is locked».
    """
    if not issns:
        return None
    marcas = ','.join('?' * len(issns))
    f = conn.execute(
        f"""SELECT id FROM revistas
            WHERE issn_impreso IN ({marcas}) OR issn_online IN ({marcas})
            LIMIT 1""", issns * 2).fetchone()
    return f['id'] if f else None


def importar(aplicar=True):
    init_db()
    datos = leer()
    if not datos:
        logger.warning("No se encontró ningún CSV de SCImago en %s", CARPETAS)
        return dict(leidas=0, enriquecidas=0, nuevas=0, detalle=[])

    conn = conectar()
    enriquecidas, nuevas, detalle = 0, 0, []

    for d in datos:
        cuartil = d['cuartil'] if d['cuartil'] not in ('', '-') else None
        rid = _por_issn(conn, d['issns'])

        if rid:
            if aplicar:
                conn.execute(
                    """UPDATE revistas SET en_scimago=1, sjr=?, cuartil_sjr=?,
                       h_scimago=?, areas_scimago=?,
                       editorial=COALESCE(NULLIF(editorial,''), ?),
                       pais=COALESCE(pais, ?)
                       WHERE id=?""",
                    (d['sjr'], cuartil, d['h'], d['areas'], d['editorial'],
                     d['pais'], rid))
            enriquecidas += 1
            continue

        # No estaba: se incorpora. Son revistas iberoamericanas de ciencias
        # sociales y humanidades indizadas en Scopus, que es justo el ámbito
        # del panel.
        if aplicar:
            from datetime import datetime
            try:
                cur = conn.execute(
                    """INSERT INTO revistas
                       (nombre, pais, institucion, sitio_url, issn_impreso,
                        issn_online, indexacion_declarada, resolucion, origen,
                        area, fecha_actualizada, en_scimago, sjr, cuartil_sjr,
                        h_scimago, areas_scimago, editorial, en_scopus,
                        scopus_estado, nivel_conicet)
                       VALUES (?,?,?,'',?,?,?,?,'externa',?,?,1,?,?,?,?,?,1,?,1)""",
                    (d['titulo'], d['pais'], d['editorial'],
                     d['issns'][0],
                     d['issns'][1] if len(d['issns']) > 1 else '',
                     f"SCImago {cuartil or 's/cuartil'} · Scopus",
                     f"ranking SCImago {ANIO} ({d['archivo']})",
                     'Ciencias Sociales y Humanidades', datetime.now(),
                     d['sjr'], cuartil, d['h'], d['areas'], d['editorial'],
                     'Discontinued' if d['discontinuada'] else 'Active'))
                rid = cur.lastrowid
            except Exception as e:
                logger.warning("No se pudo agregar %s: %s", d['titulo'][:40], e)
                continue
        nuevas += 1
        detalle.append(f"{d['titulo'][:52]} ({d['pais']}, {cuartil or 's/c'})")

    if aplicar:
        conn.commit()
        registrar_actualizacion(
            "scimago",
            f"SCImago 2025: {enriquecidas} revistas enriquecidas con SJR y "
            f"cuartil, {nuevas} incorporadas")
    conn.close()
    return dict(leidas=len(datos), enriquecidas=enriquecidas, nuevas=nuevas,
                detalle=detalle)


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
    solo_ver = '--ver' in sys.argv
    print("archivos encontrados:")
    for a in archivos():
        print("  ", a)
    r = importar(aplicar=not solo_ver)
    print(f"\nrevistas del ranking en el ámbito del panel: {r['leidas']}")
    print(f"  {'se enriquecerían' if solo_ver else 'enriquecidas'}: {r['enriquecidas']}")
    print(f"  {'se agregarían' if solo_ver else 'agregadas'}   : {r['nuevas']}")
    for d in r['detalle'][:25]:
        print("     +", d)
    if len(r['detalle']) > 25:
        print(f"     ... y {len(r['detalle'])-25} más")
