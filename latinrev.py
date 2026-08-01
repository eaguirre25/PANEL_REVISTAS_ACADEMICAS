"""
Cosecha convocatorias del listado de LatinREV (FLACSO Argentina).

https://latinrev.flacso.org.ar/convocatorias reúne llamados a dossier, números
especiales y convocatorias permanentes de revistas de toda la región. Es una
fuente distinta a rastrear los sitios uno por uno: trae convocatorias de
revistas que el panel no tiene en su catálogo, y avisos que no están en la
página de anuncios del OJS.

ESTADO AL 01/08/2026
El sitio devuelve HTTP 500 con un error de base de datos de Drupal
(«PDOException: SQLSTATE[HY000] [2002] Connection refused»). No es un bloqueo:
está caído. El módulo detecta esa condición, la informa y no rompe la
actualización semanal. Cuando el sitio vuelva, empieza a traer datos solo.

Las convocatorias que llegan por acá se guardan con fuente 'LatinREV' y, si la
revista no está en el catálogo, se registra igual con el nombre que publica
LatinREV: perder el dato sería peor que tenerlo sin ficha.
"""
import truststore
truststore.inject_into_ssl()

import re
import time
import logging
import requests
from datetime import date
from bs4 import BeautifulSoup

from database import (init_db, conectar, guardar_convocatoria,
                      guardar_revista_externa, registrar_actualizacion)
from configuracion import HEADERS_NAVEGADOR as HEADERS
from convocatorias import (PALABRAS_CLAVE, ES_DOSSIER, extraer_tema,
                           extraer_fecha, parece_vieja, sigue_recibiendo,
                           extraer_reapertura)

logger = logging.getLogger(__name__)

BASE = "https://latinrev.flacso.org.ar"
LISTADO = f"{BASE}/convocatorias"
TIMEOUT = 30
PAGINAS_MAX = 12

CAIDO = re.compile(
    r'PDOException|SQLSTATE|Connection refused|The website encountered an '
    r'unexpected error|Error \| Drupal|Service Unavailable', re.I)


def _estado_sitio(r):
    """Devuelve None si responde bien, o el motivo por el que no sirve."""
    if r.status_code >= 500:
        if CAIDO.search(r.text[:2500]):
            return "el sitio de LatinREV está caído (error de base de datos)"
        return f"el sitio devolvió HTTP {r.status_code}"
    if r.status_code != 200:
        return f"HTTP {r.status_code}"
    if CAIDO.search(r.text[:2500]):
        return "el sitio de LatinREV está caído (error de base de datos)"
    return None


def _extraer_items(soup):
    """
    Cada convocatoria del listado. La estructura de Drupal varía entre temas,
    así que se prueban varios contenedores antes de caer al genérico.
    """
    items = []
    bloques = soup.select(
        '.view-content .views-row, article.node, .node-convocatoria, '
        '.item-list li, .views-row')
    for b in bloques:
        enc = b.find(['h2', 'h3', 'h4'])
        titulo = enc.get_text(strip=True) if enc else ''
        if not titulo or len(titulo) < 12:
            continue
        a = (enc.find('a', href=True) if enc else None) or b.find('a', href=True)
        enlace = a['href'] if a else ''
        if enlace and enlace.startswith('/'):
            enlace = BASE + enlace
        cuerpo = re.sub(r'\s+', ' ', b.get_text(' ', strip=True))
        items.append((titulo, cuerpo, enlace))
    return items


def _revista_de(titulo, cuerpo):
    """
    Nombre de la revista. LatinREV suele titular «Revista X: convocatoria…»
    o poner la revista antes de un guion o dos puntos.
    """
    for sep in ('|', ' - ', ' – ', ':'):
        if sep in titulo:
            izq = titulo.split(sep)[0].strip()
            if 6 < len(izq) < 90:
                return izq
    m = re.search(r'(Revista[^.,;|]{4,70})', titulo + ' ' + cuerpo[:200])
    return m.group(1).strip() if m else None


def _id_revista(conn, nombre):
    if not nombre:
        return None
    f = conn.execute("SELECT id FROM revistas WHERE nombre = ? COLLATE NOCASE",
                     (nombre,)).fetchone()
    if f:
        return f['id']
    # Coincidencia parcial solo si el nombre es lo bastante específico.
    if len(nombre) >= 12:
        f = conn.execute(
            "SELECT id FROM revistas WHERE nombre LIKE ? COLLATE NOCASE LIMIT 1",
            (f'%{nombre}%',)).fetchone()
        if f:
            return f['id']
    return None


def cosechar(progreso=None):
    init_db()
    sesion = requests.Session()
    sesion.headers.update(HEADERS)

    try:
        r = sesion.get(LISTADO, timeout=TIMEOUT)
    except requests.RequestException as e:
        motivo = f"no se pudo conectar ({type(e).__name__})"
        logger.warning("LatinREV: %s", motivo)
        registrar_actualizacion("latinrev", f"sin datos: {motivo}")
        return dict(disponible=False, motivo=motivo, convocatorias=0, nuevas=0)

    motivo = _estado_sitio(r)
    if motivo:
        logger.warning("LatinREV: %s", motivo)
        registrar_actualizacion("latinrev", f"sin datos: {motivo}")
        return dict(disponible=False, motivo=motivo, convocatorias=0, nuevas=0)

    conn = conectar()
    total, nuevas, sin_revista = 0, 0, 0

    for pagina in range(PAGINAS_MAX):
        url = LISTADO if pagina == 0 else f"{LISTADO}?page={pagina}"
        try:
            rp = sesion.get(url, timeout=TIMEOUT)
        except requests.RequestException:
            break
        if _estado_sitio(rp):
            break

        soup = BeautifulSoup(rp.content, 'html.parser')
        for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
            tag.decompose()
        items = _extraer_items(soup)
        if not items:
            break

        for titulo, cuerpo, enlace in items:
            if not PALABRAS_CLAVE.search(titulo) and not PALABRAS_CLAVE.search(cuerpo[:300]):
                continue
            if parece_vieja(titulo):
                continue

            nombre_rev = _revista_de(titulo, cuerpo)
            rid = _id_revista(conn, nombre_rev)
            if rid is None:
                if not nombre_rev:
                    continue
                # Revista que el panel no tenía: se registra con lo que hay.
                _, rid = guardar_revista_externa(
                    nombre_rev, None, '', '', '', '',
                    'no declarada', 'incorporada desde el listado de LatinREV')
                sin_revista += 1

            dossier = bool(ES_DOSSIER.search(titulo) or ES_DOSSIER.search(cuerpo[:400]))
            total += 1
            if guardar_convocatoria(
                    rid, titulo[:250], cuerpo[:600], extraer_fecha(cuerpo),
                    enlace or LISTADO, 'LatinREV',
                    es_dossier=1 if dossier else 0,
                    tema=extraer_tema(titulo, cuerpo) if dossier else None,
                    fecha_reapertura=extraer_reapertura(cuerpo),
                    sigue_recibiendo=1 if sigue_recibiendo(cuerpo) else 0):
                nuevas += 1

        if progreso:
            progreso(pagina + 1, PAGINAS_MAX)
        time.sleep(1.5)

    conn.close()
    registrar_actualizacion(
        "latinrev",
        f"{total} convocatorias de LatinREV ({nuevas} nuevas, "
        f"{sin_revista} revistas incorporadas)")
    return dict(disponible=True, motivo=None, convocatorias=total,
                nuevas=nuevas, revistas_nuevas=sin_revista)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
    r = cosechar(progreso=lambda i, t: print(f"  página {i}", flush=True))
    if not r['disponible']:
        print("LatinREV no disponible:", r['motivo'])
        print("No es un error del panel: se reintenta en la próxima "
              "actualización semanal.")
    else:
        print(f"convocatorias: {r['convocatorias']} ({r['nuevas']} nuevas)")
        print(f"revistas incorporadas: {r['revistas_nuevas']}")
