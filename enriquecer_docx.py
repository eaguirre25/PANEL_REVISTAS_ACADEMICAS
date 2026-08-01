"""
Completa el catálogo con los nombres y los sitios de revistas.docx.

El CSV de SCImago publica los títulos sin acentos y a veces abreviados
(«Politica Criminal», «Opiniao Publica», «Dados», «Iconos»), y no trae la
dirección de la revista. Sin sitio web el rastreador no puede seguir sus
convocatorias: quedan como catálogo de referencia.

revistas.docx tiene la misma lista, en el mismo orden, con los títulos
completos y —lo importante— un hipervínculo por revista. La correspondencia
con el CSV es por posición; se verifica que al quitar acentos coincidan antes
de tocar nada.

Uso:
    python enriquecer_docx.py --ver     # qué haría
    python enriquecer_docx.py           # aplica
"""
import os
import re
import csv
import zipfile
import logging
import unicodedata
from urllib.parse import urlparse, parse_qs, unquote

from database import init_db, conectar, registrar_actualizacion

logger = logging.getLogger(__name__)

BASE = os.path.dirname(os.path.abspath(__file__))
DOCX = [os.path.join(BASE, 'datos', 'revistas.docx'), r"D:\DESCARGAS\revistas.docx"]
CSV_PAREJA = [os.path.join(BASE, 'datos',
                           'scimagojr 2025  Subject Area - Social Sciences.csv'),
              r"D:\DESCARGAS\scimagojr 2025  Subject Area - Social Sciences.csv"]

# Word deja espacios de ancho cero y no separables que strip() no saca y que
# después rompen las búsquedas por nombre.
INVISIBLES = dict.fromkeys(map(ord, '\u200b\u200c\u200d\u2060\ufeff'), None)

# Las vi\u00f1etas de lista de Word son caracteres del \u00c1rea de Uso Privado
# (Wingdings): U+F0B7 y vecinos. No cuentan como espacio, as\u00ed que strip() no
# los saca y quedan pegados al comienzo de cada nombre.
USO_PRIVADO = re.compile(r'[\ue000-\uf8ff]')


def limpiar_texto(t):
    t = (t.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
          .replace('&quot;', '"').replace('&#39;', "'"))
    t = t.translate(INVISIBLES).replace('\u00a0', ' ')
    t = USO_PRIVADO.sub('', t)
    return re.sub(r'\s+', ' ', t).strip(' \t\u00b7\u2022-\u2013\u2014')


def limpiar_url(u):
    """
    Devuelve la URL real. Varios enlaces del documento son búsquedas de Google
    que envuelven la dirección verdadera (google.com/search?q=https://...).
    """
    if not u:
        return ''
    u = u.replace('&amp;', '&').strip()
    try:
        p = urlparse(u)
    except ValueError:
        return ''
    if 'google.' in (p.netloc or '') and p.path.startswith('/search'):
        q = parse_qs(p.query).get('q', [''])[0]
        q = unquote(q)
        if q.startswith('http'):
            return q.strip()
        return ''
    return u if u.startswith('http') else ''


def _plano(s):
    s = unicodedata.normalize('NFD', s or '')
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    return re.sub(r'[^a-z0-9]+', '', s.lower())


def _issns(campo):
    out = []
    for bruto in str(campo or '').split(','):
        n = re.sub(r'[^0-9Xx]', '', bruto).upper()
        if len(n) == 8:
            out.append(f"{n[:4]}-{n[4:]}")
    return out


def leer_docx(ruta):
    """[(nombre, url), ...] en el orden del documento."""
    with zipfile.ZipFile(ruta) as z:
        xml = z.read('word/document.xml').decode('utf-8', 'replace')
        rels = z.read('word/_rels/document.xml.rels').decode('utf-8', 'replace')

    destinos = dict(re.findall(
        r'Id="([^"]+)"[^>]*Target="([^"]+)"[^>]*TargetMode="External"', rels))

    filas = []
    for p in re.findall(r'<w:p[ >].*?</w:p>', xml, re.S):
        texto = limpiar_texto(''.join(re.findall(r'<w:t[^>]*>(.*?)</w:t>', p, re.S)))
        if not texto:
            continue
        url = ''
        for rid in re.findall(r'<w:hyperlink[^>]*r:id="([^"]+)"', p):
            url = limpiar_url(destinos.get(rid, ''))
            if url:
                break
        if not url:
            sueltas = re.findall(r'https?://[^\s<>"]+', p)
            url = limpiar_url(sueltas[0]) if sueltas else ''
        filas.append((texto, url))
    return filas


def enriquecer(aplicar=True):
    init_db()
    ruta_docx = next((d for d in DOCX if os.path.exists(d)), None)
    ruta_csv = next((c for c in CSV_PAREJA if os.path.exists(c)), None)
    if not ruta_docx or not ruta_csv:
        logger.warning("Falta revistas.docx o el CSV de Social Sciences.")
        return dict(nombres=0, sitios=0, sin_pareja=0, detalle=[])

    docx = leer_docx(ruta_docx)
    with open(ruta_csv, encoding='utf-8-sig') as f:
        filas = list(csv.DictReader(f, delimiter=';'))

    if len(docx) != len(filas):
        logger.warning("El docx trae %d entradas y el CSV %d: no se emparejan "
                       "por posición.", len(docx), len(filas))
        return dict(nombres=0, sitios=0, sin_pareja=abs(len(docx)-len(filas)),
                    detalle=[])

    conn = conectar()
    nombres = sitios = sin_pareja = descartadas = 0
    detalle = []

    for (bueno, url), fila in zip(docx, filas):
        crudo = re.sub(r'\s*\(discontinued\)\s*$', '', (fila['Title'] or '').strip(),
                       flags=re.I)
        issns = _issns(fila.get('Issn'))
        if not issns:
            continue

        marcas = ','.join('?' * len(issns))
        f = conn.execute(
            f"""SELECT id, nombre, sitio_url FROM revistas
                WHERE issn_impreso IN ({marcas}) OR issn_online IN ({marcas})
                LIMIT 1""", issns * 2).fetchone()
        if not f:
            sin_pareja += 1
            continue

        # El nombre solo se corrige si la revista conserva el del CSV: si ya
        # tenía nombre propio (del NBRA u otro listado), se respeta.
        renombrar = (_plano(f['nombre']) == _plano(crudo) and f['nombre'] != bueno)
        # El sitio solo se completa si falta: no se pisa uno ya verificado.
        completar = bool(url) and not (f['sitio_url'] or '').strip()

        if not renombrar and not completar:
            continue

        if aplicar:
            if renombrar:
                try:
                    conn.execute("UPDATE revistas SET nombre=? WHERE id=?",
                                 (bueno, f['id']))
                except Exception as e:
                    logger.warning("No se pudo renombrar %s: %s", crudo[:36], e)
                    descartadas += 1
                    renombrar = False
            if completar:
                conn.execute("UPDATE revistas SET sitio_url=? WHERE id=?",
                             (url, f['id']))
        nombres += renombrar
        sitios += completar
        if len(detalle) < 400:
            detalle.append((crudo, bueno if renombrar else None,
                            url if completar else None))

    if aplicar:
        conn.commit()
        registrar_actualizacion(
            "docx", f"{nombres} nombres corregidos y {sitios} sitios "
                    f"incorporados desde revistas.docx")
    conn.close()
    return dict(nombres=nombres, sitios=sitios, sin_pareja=sin_pareja,
                descartadas=descartadas, detalle=detalle)


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
    solo_ver = '--ver' in sys.argv
    r = enriquecer(aplicar=not solo_ver)
    print(("SIMULACIÓN" if solo_ver else "APLICADO"))
    print(f"  nombres corregidos : {r['nombres']}")
    print(f"  sitios incorporados: {r['sitios']}")
    if r['sin_pareja']:
        print(f"  sin pareja en la base: {r['sin_pareja']}")
    print()
    for crudo, nuevo, url in r['detalle'][:18]:
        print(f"  {crudo[:40]}")
        if nuevo:
            print(f"      nombre -> {nuevo[:60]}")
        if url:
            print(f"      sitio  -> {url[:66]}")
