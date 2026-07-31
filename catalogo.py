"""
Descarga el catálogo real del Núcleo Básico de Revistas Argentinas (CAICYT-CONICET).

Fuente: https://www.caicyt-conicet.gov.ar/sitio/comunicacion-cientifica/nucleo-basico/revistas-integrantes/

Cada revista tiene una ficha propia en el sitio de CAICYT con su área temática,
ISSN y el enlace al sitio real de la publicación.
"""
import truststore
truststore.inject_into_ssl()  # usa el almacén de certificados de Windows (antivirus con TLS)

import re
import time
import logging
import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

from database import init_db, guardar_revista, registrar_actualizacion

logger = logging.getLogger(__name__)

INDICE = ("https://www.caicyt-conicet.gov.ar/sitio/comunicacion-cientifica/"
          "nucleo-basico/revistas-integrantes/")
from configuracion import HEADERS_NAVEGADOR as HEADERS
AREA_OBJETIVO = "Ciencias Sociales y Humanidades"
TIMEOUT = 25


def _sesion():
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


def listar_fichas(sesion):
    """Devuelve [(nombre, url_ficha), ...] de las 429 revistas del NBRA."""
    r = sesion.get(INDICE, timeout=TIMEOUT)
    r.raise_for_status()
    soup = BeautifulSoup(r.content, 'html.parser')

    vistas, fichas = set(), []
    for p in soup.select('p.pt-cv-title'):
        a = p.find('a', href=True)
        if not a:
            continue
        nombre = a.get_text(strip=True)
        href = a['href']
        if nombre and href not in vistas:
            vistas.add(href)
            fichas.append((nombre, href))
    return fichas


def leer_ficha(sesion, nombre, url):
    """Extrae área, ISSN, institución y sitio real de la revista desde su ficha."""
    try:
        r = sesion.get(url, timeout=TIMEOUT)
        r.raise_for_status()
    except Exception as e:
        logger.warning("ficha inaccesible %s: %s", nombre, e)
        return None

    soup = BeautifulSoup(r.content, 'html.parser')
    for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
        tag.decompose()
    cuerpo = soup.find('article') or soup.find('main') or soup
    texto = cuerpo.get_text('\n', strip=True)

    # Área temática: aparece como primera línea de la ficha.
    area = ""
    for linea in texto.split('\n')[:6]:
        if 'Ciencias' in linea and len(linea) < 70:
            area = linea.strip()
            break

    # ISSN impreso / en línea.
    issn_impreso = issn_online = ""
    for m in re.finditer(r'ISSN\s*(\d{4}-\d{3}[\dXx])(.{0,40})', texto, re.S):
        cod, cola = m.group(1), m.group(2).lower()
        if 'línea' in cola or 'linea' in cola or 'online' in cola:
            issn_online = issn_online or cod
        elif 'impres' in cola:
            issn_impreso = issn_impreso or cod
        elif not issn_impreso:
            issn_impreso = cod

    # Sitio real: el enlace "Ver publicación".
    sitio = ""
    for a in cuerpo.find_all('a', href=True):
        if 'ver publicaci' in a.get_text(strip=True).lower():
            sitio = a['href']
            break
    if not sitio:
        for a in cuerpo.find_all('a', href=True):
            h = a['href']
            if h.startswith('http') and 'caicyt' not in h and not re.search(
                    r'facebook|twitter|linkedin|whatsapp|google|conicet\.gov\.ar/sitio', h):
                sitio = h
                break

    # Institución editora: línea suelta antes de "Ver publicación".
    institucion = ""
    for linea in texto.split('\n'):
        l = linea.strip()
        if (len(l) > 12 and not l.startswith('ISSN') and 'Ciencias' not in l
                and 'Núcleo' not in l and not re.match(r'^\d', l)
                and 'Ver ' not in l and 'Comparte' not in l and 'Haz clic' not in l
                and l.lower() != 'admin'):
            institucion = l
            break

    return dict(nombre=nombre, ficha_url=url, sitio_url=sitio,
                issn_impreso=issn_impreso, issn_online=issn_online,
                area=area, institucion=institucion)


def actualizar_catalogo(solo_sociales=True, workers=6, progreso=None):
    """Descarga el catálogo completo y lo guarda. Devuelve un resumen."""
    init_db()
    sesion = _sesion()

    logger.info("Descargando índice del NBRA...")
    fichas = listar_fichas(sesion)
    logger.info("Fichas encontradas: %d", len(fichas))

    resultados = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futuros = {pool.submit(leer_ficha, sesion, n, u): n for n, u in fichas}
        for i, fut in enumerate(as_completed(futuros), 1):
            datos = fut.result()
            if datos:
                resultados.append(datos)
            if progreso and i % 10 == 0:
                progreso(i, len(fichas))
            time.sleep(0.02)  # cortesía con el servidor

    nuevas = actualizadas = 0
    guardadas = []
    for d in resultados:
        if solo_sociales and AREA_OBJETIVO.lower() not in (d['area'] or '').lower():
            continue
        estado = guardar_revista(d['nombre'], d['ficha_url'], d['sitio_url'],
                                 d['issn_impreso'], d['issn_online'],
                                 d['area'], d['institucion'])
        guardadas.append(d)
        if estado == 'nueva':
            nuevas += 1
        else:
            actualizadas += 1

    resumen = dict(fichas=len(fichas), leidas=len(resultados),
                   guardadas=len(guardadas), nuevas=nuevas,
                   actualizadas=actualizadas,
                   con_sitio=sum(1 for d in guardadas if d['sitio_url']))

    registrar_actualizacion(
        "catalogo",
        f"{resumen['guardadas']} revistas de {AREA_OBJETIVO} "
        f"({nuevas} nuevas, {actualizadas} actualizadas, "
        f"{resumen['con_sitio']} con sitio web)")
    return resumen


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
    r = actualizar_catalogo(progreso=lambda i, t: print(f"  ficha {i}/{t}", flush=True))
    print("\nRESUMEN:", r)
