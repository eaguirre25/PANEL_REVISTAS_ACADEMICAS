"""
Detecta convocatorias y llamados a dossier abiertos en las revistas del catálogo.

La mayoría de las revistas del NBRA usan OJS (Open Journal Systems), que expone
sus anuncios en {base}/announcement. Se lee esa página y se filtran los anuncios
que son convocatorias, extrayendo la fecha de cierre cuando está declarada.

Se respetan las protecciones anti-scraping: si un sitio exige login o presenta un
desafío (Anubis, Cloudflare), se saltea y se marca para revisión manual.
"""
import truststore
truststore.inject_into_ssl()

import re
import time
import logging
import requests
from datetime import date, datetime
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

from database import (init_db, revistas_con_sitio, guardar_convocatoria,
                      marcar_chequeo, registrar_actualizacion,
                      desactivar_convocatorias_vencidas)

logger = logging.getLogger(__name__)

from configuracion import HEADERS_NAVEGADOR as HEADERS
TIMEOUT = 20

# Un anuncio es convocatoria si menciona alguno de estos términos.
PALABRAS_CLAVE = re.compile(
    r'convocatoria|dossier|dosier|call for papers|llamado|'
    r'recepci[óo]n de (art[íi]culos|trabajos|manuscritos|colaboraciones)|'
    r'n[úu]mero (tem[áa]tico|especial)|secci[óo]n tem[áa]tica|dossi[êe]',
    re.I)

# Señales de que la página no es realmente el listado de anuncios.
BLOQUEO = re.compile(
    r"making sure you're not a bot|anubis|just a moment|checking your browser|"
    r"cf-browser-verification|enable javascript and cookies", re.I)

MESES = {'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4, 'mayo': 5, 'junio': 6,
         'julio': 7, 'agosto': 8, 'septiembre': 9, 'setiembre': 9, 'octubre': 10,
         'noviembre': 11, 'diciembre': 12}


def base_ojs(url):
    """Normaliza la URL de la revista a la raíz de su instalación OJS."""
    u = url.strip().rstrip('/')
    u = re.sub(r'/(index|home|about|issue/archive|announcement)$', '', u, flags=re.I)
    return u


# Frases que anteceden al plazo de cierre en los textos de convocatoria.
CONTEXTO_PLAZO = re.compile(
    r'(fecha\s+l[íi]mite|fecha\s+de\s+cierre|hasta\s+el|plazo|cierre\s+de\s+la\s+convocatoria|'
    r'recepci[óo]n\s+(?:de\s+\w+\s+)?hasta|se\s+recibir[áa]n\s+hasta|env[íi]o\s+hasta|'
    r'deadline|vence)', re.I)


def _fechas_en(texto):
    """Todas las fechas con año explícito presentes en el texto."""
    t = texto.lower()
    out = []

    # "15 de marzo de 2026"
    for m in re.finditer(r'(\d{1,2})\s+de\s+([a-záéíóú]+)\s+de\s+(\d{4})', t):
        mes = MESES.get(m.group(2))
        if mes:
            try:
                out.append((m.start(), date(int(m.group(3)), mes, int(m.group(1)))))
            except ValueError:
                pass

    # "31/12/2026" o "31-12-2026"
    for m in re.finditer(r'\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b', t):
        try:
            out.append((m.start(), date(int(m.group(3)), int(m.group(2)), int(m.group(1)))))
        except ValueError:
            pass

    # "2026-12-31"
    for m in re.finditer(r'\b(\d{4})-(\d{1,2})-(\d{1,2})\b', t):
        try:
            out.append((m.start(), date(int(m.group(1)), int(m.group(2)), int(m.group(3)))))
        except ValueError:
            pass

    return out


def extraer_fecha(texto):
    """
    Busca la fecha de cierre. Devuelve 'YYYY-MM-DD' o None.

    Solo acepta fechas con año explícito: inferir el año produce plazos falsos
    (un aviso de 2017 sin año parecería vencer el año que viene). Prioriza las
    fechas precedidas por una frase de plazo ("fecha límite", "hasta el", ...).
    """
    if not texto:
        return None
    hoy = date.today()
    fechas = _fechas_en(texto)
    if not fechas:
        return None

    # Preferimos fechas cuyo contexto inmediato anterior hable de un plazo.
    con_contexto = [f for pos, f in fechas
                    if CONTEXTO_PLAZO.search(texto[max(0, pos - 120):pos])]

    for grupo in (con_contexto, [f for _, f in fechas]):
        futuras = sorted(f for f in grupo if f >= hoy)
        if futuras:
            return futuras[0].isoformat()
    return None


# Frases que anuncian cuándo vuelve a abrirse la recepción.
CONTEXTO_REAPERTURA = re.compile(
    r'pr[óo]xima\s+convocatoria|pr[óo]xima\s+recepci[óo]n|se\s+reabre|'
    r'reapertura|vuelve\s+a\s+abrir|nueva\s+convocatoria\s+(?:a\s+partir|en|desde)|'
    r'la\s+recepci[óo]n\s+se\s+reanuda|se\s+reanuda|'
    r'pr[óo]ximo\s+n[úu]mero\s+(?:se\s+)?recibe|a\s+partir\s+del?', re.I)

# Declaraciones de que, aunque cierre el dossier, la revista sigue recibiendo.
SIGUE_RECIBIENDO = re.compile(
    r'(?:secci[óo]n|convocatoria)\s+(?:de\s+)?(?:art[íi]culos\s+)?libres?|'
    r'temas\s+libres|art[íi]culos\s+libres|miscel[áa]nea|varia\b|'
    r'(?:se\s+)?contin[úu]a\s+recibiendo|sigue\s+recibiendo|'
    r'recepci[óo]n\s+permanente|flujo\s+continuo', re.I)


def extraer_reapertura(texto):
    """
    Fecha en que vuelve a abrirse la recepción, si el aviso la declara.

    Se busca solo cerca de una frase que anuncie la reapertura: cualquier fecha
    futura suelta en el texto podría ser la de publicación del número, no la de
    la próxima convocatoria.
    """
    if not texto:
        return None
    hoy = date.today()
    for pos, f in _fechas_en(texto):
        ventana = texto[max(0, pos - 130):pos]
        if CONTEXTO_REAPERTURA.search(ventana) and f > hoy:
            return f.isoformat()
    return None


def sigue_recibiendo(texto):
    """True si el aviso aclara que, más allá del dossier, se reciben trabajos."""
    if not texto:
        return False
    m = SIGUE_RECIBIENDO.search(texto)
    return bool(m)


def parece_vieja(titulo):
    """True si el título declara un año anterior al actual (aviso archivado)."""
    anios = [int(a) for a in re.findall(r'\b(20\d{2})\b', titulo)]
    return bool(anios) and max(anios) < date.today().year


ES_DOSSIER = re.compile(
    r'dossi[eê]r|dosier|n[úu]mero\s+(tem[áa]tico|especial|monogr[áa]fico)|'
    r'secci[óo]n\s+tem[áa]tica|monogr[áa]fico|special\s+issue', re.I)

# El tema suele venir entrecomillado o después de dos puntos.
ENTRECOMILLADO = re.compile(r'[«"“‘]([^»"”’]{12,140})[»"”’]')
TRAS_DOS_PUNTOS = re.compile(
    r'(?:dossi[eê]r|dosier|n[úu]mero\s+tem[áa]tico|monogr[áa]fico|'
    r'secci[óo]n\s+tem[áa]tica|special\s+issue)[^:.\n]{0,40}[:.–—-]\s*'
    r'([^.\n]{12,140})', re.I)


# Marcas que indican que el tema ya terminó y empieza otra sección del aviso.
COLA = re.compile(
    r'\s*(?:coordinador|coordinadora|editor|editora|fechas?\s*:|apertura|'
    r'plazo|env[íi]o|recepci[óo]n|fecha\s+l[íi]mite|convocatoria\s+abierta|'
    r'\bissn\b|http)', re.I)


def _limpiar_tema(t):
    """Normaliza el fragmento capturado y descarta lo que no es un tema."""
    t = re.sub(r'\s+', ' ', t).strip(' .,:;-–—«»"“”')
    # Quita un prefijo redundante: 'Dossier: X' -> 'X'.
    t = re.sub(r'^(dossi[eê]r|dosier|n[úu]mero\s+tem[áa]tico|monogr[áa]fico|'
               r'secci[óo]n\s+tem[áa]tica)\s*[:.–—-]\s*', '', t, flags=re.I)
    # Corta la cola administrativa ('... Coordinadores: Dr', '... Fechas: ...').
    m = COLA.search(t)
    if m and m.start() > 15:
        t = t[:m.start()]
    t = t.strip(' .,:;-–—')

    if len(t) < 15 or len(t.split()) < 3:
        return None
    if re.match(r'^\d', t):          # '04 CONVOCATORIA La revista...'
        return None
    if re.fullmatch(r'[\dNnºo°.,\s/-]+', t):
        return None
    return t


def extraer_tema(titulo, descripcion):
    """
    Tema del dossier, si se puede aislar del título o del cuerpo.

    Se prioriza el texto entrecomillado, que en los avisos de OJS casi siempre
    es exactamente el título temático del número. Si no hay, se toma lo que
    sigue a la palabra "dossier" tras dos puntos o guion. Todo lo capturado
    pasa por _limpiar_tema: sin ese filtro salían cosas como "autor universal"
    (un fragmento suelto entrecomillado) o el primer párrafo entero del aviso.
    """
    for patron in (ENTRECOMILLADO, TRAS_DOS_PUNTOS):
        for fuente in (titulo, descripcion or ''):
            for m in patron.finditer(fuente):
                tema = _limpiar_tema(m.group(1))
                if tema:
                    return tema
    return None


# Cada tema de OJS nombra distinto el bloque de un aviso. El tema por defecto
# usa .obj_announcement_summary; otros muy difundidos —el de revistas.unc.edu.ar,
# que aloja 32 revistas— usan .announcement-summary, con guion. Buscar solo el
# primero hacía que esas revistas figuraran como «sin convocatorias» teniendo
# dossiers publicados.
SELECTORES_ANUNCIO = ('.obj_announcement_summary, .announcement-summary, '
                      '.announcement, article.announcement, '
                      '.announcements .media, li.announcement')


def parsear_anuncios(html, url_base):
    """Extrae [(titulo, descripcion, url), ...] de la página de anuncios de OJS."""
    soup = BeautifulSoup(html, 'html.parser')
    for t in soup(['script', 'style', 'nav', 'footer', 'header']):
        t.decompose()

    anuncios = []
    bloques = soup.select(SELECTORES_ANUNCIO)

    for b in bloques:
        enc = b.find(['h2', 'h3', 'h4', 'h5'])
        titulo = enc.get_text(strip=True) if enc else ''
        if not titulo:
            continue
        cuerpo = b.get_text(' ', strip=True)
        enlace = ''
        a = b.find('a', href=True)
        if a:
            enlace = a['href']
        anuncios.append((titulo, cuerpo, enlace or url_base))

    # OJS 2 y temas alternativos: listado con h4/h3 sueltos bajo #content
    if not anuncios:
        cont = soup.find(id='content') or soup.find('main') or soup
        for enc in cont.find_all(['h3', 'h4']):
            titulo = enc.get_text(strip=True)
            if not titulo or len(titulo) < 12:
                continue
            trozos = []
            for sib in enc.find_next_siblings():
                if sib.name in ('h3', 'h4'):
                    break
                trozos.append(sib.get_text(' ', strip=True))
            a = enc.find('a', href=True)
            anuncios.append((titulo, ' '.join(trozos), a['href'] if a else url_base))

    return anuncios


def revisar_revista(sesion, revista):
    """Busca convocatorias en una revista. Devuelve (estado, [convocatorias])."""
    url = base_ojs(revista['sitio_url']) + '/announcement'
    try:
        r = sesion.get(url, timeout=TIMEOUT, allow_redirects=True)
    except requests.TooManyRedirects:
        return 'redirecciones', []
    except requests.RequestException as e:
        return f'inaccesible ({type(e).__name__})', []

    if r.status_code == 404:
        return 'sin pagina de anuncios', []
    if r.status_code != 200:
        return f'http {r.status_code}', []
    if '/login' in r.url.lower():
        return 'requiere login', []

    texto_pagina = r.text
    if BLOQUEO.search(texto_pagina[:4000]):
        return 'protegido (anti-bot) - revisar a mano', []

    encontradas = []
    for titulo, cuerpo, enlace in parsear_anuncios(texto_pagina, url):
        # La palabra clave debe estar en el título: buscarla en el cuerpo produce
        # falsos positivos (avisos que solo mencionan otra convocatoria de paso).
        if not PALABRAS_CLAVE.search(titulo):
            continue
        if parece_vieja(titulo):
            continue

        fecha = extraer_fecha(cuerpo)

        # Si el listado no declara el plazo, lo buscamos en la ficha del anuncio.
        if not fecha and enlace and enlace != url:
            detalle = _leer_detalle(sesion, enlace)
            if detalle:
                fecha = extraer_fecha(detalle)
                if len(detalle) > len(cuerpo):
                    cuerpo = detalle

        desc = re.sub(r'\s+', ' ', cuerpo)[:600]
        dossier = bool(ES_DOSSIER.search(titulo) or ES_DOSSIER.search(desc[:400]))
        tema = extraer_tema(titulo, desc) if dossier else None
        encontradas.append(dict(
            titulo=titulo[:250], descripcion=desc, fecha_cierre=fecha,
            url=enlace, es_dossier=1 if dossier else 0, tema=tema,
            fecha_reapertura=extraer_reapertura(cuerpo),
            sigue_recibiendo=1 if sigue_recibiendo(cuerpo) else 0))

    if not encontradas:
        return 'sin convocatorias', []
    return 'ok', encontradas


def _leer_detalle(sesion, url):
    """Texto de la ficha de un anuncio, para hallar el plazo de cierre."""
    try:
        r = sesion.get(url, timeout=TIMEOUT, allow_redirects=True)
        if r.status_code != 200 or '/login' in r.url.lower():
            return ''
        if BLOQUEO.search(r.text[:4000]):
            return ''
        s = BeautifulSoup(r.content, 'html.parser')
        for t in s(['script', 'style', 'nav', 'footer', 'header']):
            t.decompose()
        cont = (s.select_one('.obj_announcement_full, .announcement, #content, main')
                or s)
        return re.sub(r'\s+', ' ', cont.get_text(' ', strip=True))
    except requests.RequestException:
        return ''


def buscar_convocatorias(workers=8, progreso=None):
    """Recorre todas las revistas con sitio y guarda las convocatorias halladas."""
    init_db()
    revistas = revistas_con_sitio()
    logger.info("Revisando %d revistas...", len(revistas))

    sesion = requests.Session()
    sesion.headers.update(HEADERS)

    estados, nuevas, total = {}, 0, 0

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futuros = {pool.submit(revisar_revista, sesion, rv): rv for rv in revistas}
        for i, fut in enumerate(as_completed(futuros), 1):
            rv = futuros[fut]
            try:
                estado, convs = fut.result()
            except Exception as e:
                estado, convs = f'error ({type(e).__name__})', []

            estados[estado] = estados.get(estado, 0) + 1
            marcar_chequeo(rv['id'], estado)

            for c in convs:
                total += 1
                if guardar_convocatoria(
                        rv['id'], c['titulo'], c['descripcion'],
                        c['fecha_cierre'], c['url'], 'OJS/announcement',
                        es_dossier=c['es_dossier'], tema=c['tema'],
                        fecha_reapertura=c['fecha_reapertura'],
                        sigue_recibiendo=c['sigue_recibiendo']):
                    nuevas += 1

            if progreso and i % 10 == 0:
                progreso(i, len(revistas))
            time.sleep(0.02)

    vencidas = desactivar_convocatorias_vencidas()

    resumen = dict(revisadas=len(revistas), convocatorias=total, nuevas=nuevas,
                   vencidas_desactivadas=vencidas, estados=estados)
    registrar_actualizacion(
        "convocatorias",
        f"{total} convocatorias en {estados.get('ok', 0)} revistas "
        f"({nuevas} nuevas, {vencidas} vencidas archivadas)")
    return resumen


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
    res = buscar_convocatorias(progreso=lambda i, t: print(f"  {i}/{t}", flush=True))
    print("\nRESUMEN:")
    for k, v in res.items():
        if k != 'estados':
            print(f"  {k}: {v}")
    print("  estados:")
    for e, n in sorted(res['estados'].items(), key=lambda x: -x[1]):
        print(f"    {n:4}  {e}")
