"""
Detecta revistas con recepción permanente de artículos (abiertas todo el año).

Se lee la página de directrices para autores del OJS ({base}/about/submissions,
con /about como alternativa) y se busca una afirmación de permanencia *en
contexto de recepción de trabajos*.

El contexto es imprescindible: buscar solo la palabra "permanente" produce
falsos positivos como "archivos permanentes en la revista con fines de
conservación", que habla del archivado LOCKSS, no de la recepción.

Ejemplos reales que sí cuentan:
  Hipertextos     "recibe artículos y otro tipo de contribuciones todo el año"
  Revista Paraguay "La convocatoria de artículos, reseñas y entrevistas
                    SE ENCUENTRA SIEMPRE ABIERTA"
"""
import truststore
truststore.inject_into_ssl()

import re
import time
import logging
import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

from database import (init_db, revistas_con_sitio, marcar_recepcion_permanente,
                      registrar_actualizacion)

logger = logging.getLogger(__name__)

from configuracion import HEADERS_NAVEGADOR as HEADERS
TIMEOUT = 20

# Marca de permanencia.
PERMANENCIA = re.compile(
    r'permanentemente|de\s+forma\s+permanente|de\s+manera\s+permanente|'
    r'car[áa]cter\s+permanente|recepci[óo]n\s+permanente|convocatoria\s+permanente|'
    r'siempre\s+(?:est[áa]\s+)?abiert[ao]|todo\s+el\s+a[ñn]o|'
    r'en\s+cualquier\s+momento|de\s+manera\s+continua|en\s+forma\s+continua|'
    r'flujo\s+continuo|continuamente|sin\s+fecha\s+l[íi]mite|'
    r'no\s+hay\s+fecha\s+l[íi]mite|abierta\s+de\s+forma\s+permanente',
    re.I)

# Debe haber recepción de trabajos cerca de la marca.
RECEPCION = re.compile(
    r'recib[ei]|recepci[óo]n|convocatoria|postulaci[óo]n|env[íi]o\s+de|'
    r'admite|acepta|se\s+reciben|remisi[óo]n|presentaci[óo]n\s+de\s+(?:trabajos|art)|'
    r'manuscrito|art[íi]culo|contribucion|colaboracion',
    re.I)

# Contextos que NO son recepción de artículos.
EXCLUIR = re.compile(
    r'archivo|lockss|clockss|preservaci[óo]n|conservaci[óo]n|restauraci[óo]n|'
    r'a\s+continuaci[óo]n|comit[ée]\s+permanente|personal\s+permanente|'
    r'enlace\s+permanente|link\s+permanente|url\s+permanente|identificador|'
    # Estadísticas de gestión editorial ("se rechazaron 62 artículos en todo
    # el año"), que describen el pasado y no la política de recepción.
    r'rechaz|se\s+publicaron|cola\s+de\s+edici[óo]n|tasa\s+de\s+aceptaci[óo]n|'
    # El proceso de evaluación puede correr todo el año aunque la recepción
    # tenga plazos; no es lo mismo que recibir trabajos todo el año.
    r'proceso\s+de\s+evaluaci[óo]n|evaluaci[óo]n\s+se\s+desarrollar',
    re.I)

BLOQUEO = re.compile(
    r"making sure you're not a bot|anubis|just a moment|checking your browser",
    re.I)

VENTANA = 160  # caracteres a cada lado de la marca


def base_ojs(url):
    u = url.strip().rstrip('/')
    return re.sub(r'/(index|home|about|issue/archive|announcement)$', '', u, flags=re.I)


def analizar(texto):
    """Devuelve (es_permanente, fragmento_de_evidencia)."""
    limpio = re.sub(r'\s+', ' ', texto)
    for m in PERMANENCIA.finditer(limpio):
        ini = max(0, m.start() - VENTANA)
        fin = min(len(limpio), m.end() + VENTANA)
        ctx = limpio[ini:fin]
        if EXCLUIR.search(ctx):
            continue
        if RECEPCION.search(ctx):
            return True, ctx.strip()
    return False, ''


def revisar(sesion, revista):
    """Busca la declaración de recepción permanente. (estado, permanente, evidencia)."""
    base = base_ojs(revista['sitio_url'])
    ultimo_estado = 'sin declaracion'

    # La portada ('') va última: algunas revistas declaran la permanencia ahí y
    # no en /about (p. ej. "Paraguay desde las ciencias sociales").
    for sufijo in ('/about/submissions', '/about', ''):
        url = base + sufijo
        try:
            r = sesion.get(url, timeout=TIMEOUT, allow_redirects=True)
        except requests.RequestException as e:
            ultimo_estado = f'inaccesible ({type(e).__name__})'
            continue

        if r.status_code != 200:
            ultimo_estado = f'http {r.status_code}'
            continue
        if '/login' in r.url.lower():
            return 'requiere login', False, ''
        if BLOQUEO.search(r.text[:4000]):
            return 'protegido (anti-bot)', False, ''

        soup = BeautifulSoup(r.content, 'html.parser')
        for t in soup(['script', 'style', 'nav', 'footer', 'header']):
            t.decompose()
        texto = (soup.find('main') or soup).get_text(' ', strip=True)

        permanente, evidencia = analizar(texto)
        if permanente:
            return 'ok', True, f"{evidencia}  [fuente: {url}]"
        ultimo_estado = 'sin declaracion'

    return ultimo_estado, False, ''


def detectar_permanentes(workers=8, progreso=None):
    init_db()
    revistas = revistas_con_sitio()
    sesion = requests.Session()
    sesion.headers.update(HEADERS)

    estados, permanentes = {}, 0

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futuros = {pool.submit(revisar, sesion, rv): rv for rv in revistas}
        for i, fut in enumerate(as_completed(futuros), 1):
            rv = futuros[fut]
            try:
                estado, es_perm, evid = fut.result()
            except Exception as e:
                estado, es_perm, evid = f'error ({type(e).__name__})', False, ''

            estados[estado] = estados.get(estado, 0) + 1
            if es_perm:
                permanentes += 1
                marcar_recepcion_permanente(rv['id'], True, evid)
            elif estado == 'sin declaracion':
                marcar_recepcion_permanente(rv['id'], False, '')

            if progreso and i % 10 == 0:
                progreso(i, len(revistas))
            time.sleep(0.02)

    registrar_actualizacion(
        "permanentes",
        f"{permanentes} revistas con recepción permanente de {len(revistas)} revisadas")
    return dict(revisadas=len(revistas), permanentes=permanentes, estados=estados)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
    r = detectar_permanentes(progreso=lambda i, t: print(f"  {i}/{t}", flush=True))
    print("\nRESUMEN:")
    print("  revisadas:", r['revisadas'])
    print("  con recepción permanente:", r['permanentes'])
    for e, n in sorted(r['estados'].items(), key=lambda x: -x[1]):
        print(f"    {n:4}  {e}")
