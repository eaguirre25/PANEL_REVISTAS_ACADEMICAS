"""
Lee las revistas cuya protección impide la lectura automática, usando un
navegador real con sesión persistente.

CÓMO FUNCIONA
El panel abre esas revistas en un perfil de Chrome propio (carpeta
`perfil-revistas/`, separada del perfil personal). La primera vez la ventana
queda a la vista: si aparece una verificación, la resolvés vos. Hecho eso, las
cookies quedan guardadas en ese perfil y las corridas siguientes reutilizan la
sesión mientras siga vigente. Cuando vence, el programa avisa qué dominio hay
que renovar en lugar de insistir.

QUÉ NO HACE
No usa complementos «stealth», no altera la huella del navegador, no rota
proxies, no resuelve CAPTCHAs ni manipula encabezados para disimular que es
Playwright. La verificación la pasa una persona; el programa solo aprovecha la
sesión que quedó abierta. Si un sitio vuelve a desafiar, esa fuente queda
pendiente y se informa.

POR QUÉ AGRUPA POR DOMINIO
La protección suele estar a nivel de servidor: revistas.unc.edu.ar aloja
varias revistas y comparten el mismo muro. Resolver la verificación una vez
habilita todas las de ese dominio.
"""
import os
import re
import time
import logging
from datetime import datetime, date

from database import (init_db, revistas_bloqueadas, guardar_convocatoria,
                      marcar_chequeo, marcar_recepcion_permanente,
                      registrar_actualizacion)
from convocatorias import (PALABRAS_CLAVE, ES_DOSSIER, extraer_tema,
                           extraer_fecha, parece_vieja, base_ojs)
from permanentes import analizar as analizar_permanente

logger = logging.getLogger(__name__)

BASE = os.path.dirname(os.path.abspath(__file__))
PERFIL = os.path.join(BASE, 'perfil-revistas')

DESAFIO = re.compile(
    r"making sure you're not a bot|anubis|just a moment|checking your browser|"
    r"verificando que|cf-browser-verification|captcha", re.I)

ESPERA_ENTRE_PAGINAS = 2.5   # segundos, para no golpear el servidor
ESPERA_DESAFIO = 60          # segundos que se le dan a la persona para resolver

# Playwright envuelve todo en Error; el motivo real viene en el texto.
MOTIVOS = [
    (r'ERR_CERT', 'certificado inválido o vencido'),
    (r'ERR_CONNECTION_TIMED_OUT|Timeout', 'el servidor no responde'),
    (r'ERR_NAME_NOT_RESOLVED', 'el dominio no existe'),
    (r'ERR_CONNECTION_REFUSED', 'conexión rechazada'),
    (r'ERR_CONNECTION_RESET', 'conexión cortada'),
    (r'ERR_TOO_MANY_REDIRECTS', 'demasiadas redirecciones'),
    (r'ERR_EMPTY_RESPONSE', 'respuesta vacía'),
    (r'ERR_SSL', 'error de SSL'),
]


def _motivo(e):
    """Traduce el error de Playwright a algo accionable."""
    t = str(e)
    for patron, texto in MOTIVOS:
        if re.search(patron, t, re.I):
            return texto
    return f'error de navegación ({t.splitlines()[0][:60]})'


def _texto_visible(page):
    try:
        return page.inner_text('body', timeout=8000)
    except Exception:
        return ''


def _hay_desafio(page):
    return bool(DESAFIO.search(_texto_visible(page)[:3000]))


def _extraer_anuncios(page, url):
    """Anuncios de la página ya cargada, con la misma lógica que el rastreador."""
    anuncios = []
    try:
        bloques = page.query_selector_all(
            '.obj_announcement_summary, .announcement, article.announcement')
        for b in bloques:
            enc = b.query_selector('h2, h3, h4, h5')
            titulo = (enc.inner_text().strip() if enc else '')
            if not titulo:
                continue
            cuerpo = re.sub(r'\s+', ' ', b.inner_text())
            a = b.query_selector('a[href]')
            enlace = a.get_attribute('href') if a else url
            anuncios.append((titulo, cuerpo, enlace or url))
    except Exception as e:
        logger.warning("No se pudieron leer los anuncios de %s: %s", url, e)
    return anuncios


def _procesar_revista(page, rv):
    """Visita una revista y devuelve (estado, convocatorias, permanente)."""
    base = base_ojs(rv['sitio_url'])
    url = base + '/announcement'
    try:
        page.goto(url, wait_until='domcontentloaded', timeout=60000)
    except Exception as e:
        return f'inaccesible: {_motivo(e)}', [], None

    if _hay_desafio(page):
        return 'desafio', [], None
    if '/login' in page.url.lower():
        return 'requiere login', [], None

    encontradas = []
    for titulo, cuerpo, enlace in _extraer_anuncios(page, url):
        if not PALABRAS_CLAVE.search(titulo) or parece_vieja(titulo):
            continue
        fecha = extraer_fecha(cuerpo)
        dossier = bool(ES_DOSSIER.search(titulo) or ES_DOSSIER.search(cuerpo[:400]))
        encontradas.append(dict(
            titulo=titulo[:250], descripcion=re.sub(r'\s+', ' ', cuerpo)[:600],
            fecha_cierre=fecha, url=enlace,
            es_dossier=1 if dossier else 0,
            tema=extraer_tema(titulo, cuerpo) if dossier else None))

    # De paso, la página de envíos: si declara recepción permanente, se anota.
    permanente = None
    try:
        page.goto(base + '/about/submissions',
                  wait_until='domcontentloaded', timeout=45000)
        if not _hay_desafio(page):
            es_perm, evidencia = analizar_permanente(_texto_visible(page))
            if es_perm:
                permanente = f"{evidencia}  [fuente: {base}/about/submissions]"
    except Exception:
        pass

    return ('ok' if encontradas else 'sin convocatorias'), encontradas, permanente


def revisar(dominios=None, espera_desafio=ESPERA_DESAFIO, progreso=None):
    """
    Recorre las revistas bloqueadas con el navegador asistido.

    `dominios`: lista opcional para limitar a algunos. Sin ella, todos.
    """
    from playwright.sync_api import sync_playwright

    init_db()
    cola = revistas_bloqueadas()
    if dominios:
        cola = {d: v for d, v in cola.items() if d in dominios}
    if not cola:
        logger.info("No hay revistas pendientes.")
        return dict(dominios=0, revisadas=0, convocatorias=0, nuevas=0,
                    permanentes=0, pendientes=[], detalle={})

    total = sum(len(v) for v in cola.values())
    logger.info("Pendientes: %d revistas en %d dominios", total, len(cola))

    os.makedirs(PERFIL, exist_ok=True)
    resumen = dict(dominios=len(cola), revisadas=0, convocatorias=0, nuevas=0,
                   permanentes=0, pendientes=[], detalle={})
    hechas = 0

    with sync_playwright() as p:
        contexto = p.chromium.launch_persistent_context(
            PERFIL,
            channel='chrome',       # usa el Chrome instalado, no descarga otro
            headless=False,         # la ventana debe verse para poder resolver
            viewport=None,
            # Muchos OJS universitarios tienen el certificado vencido o emitido
            # para otro nombre. Tolerarlo no evade ninguna protección: son
            # sitios públicos que el navegador abre igual tras una advertencia.
            ignore_https_errors=True,
            args=['--start-maximized'])
        page = contexto.pages[0] if contexto.pages else contexto.new_page()

        try:
            for dominio, revistas in cola.items():
                logger.info("── %s (%d revistas)", dominio, len(revistas))

                # Primer contacto con el dominio: si desafía, se le da tiempo a
                # la persona para resolverlo en la ventana abierta.
                primera = revistas[0]
                try:
                    page.goto(base_ojs(primera['sitio_url']),
                              wait_until='domcontentloaded', timeout=60000)
                except Exception as e:
                    motivo = _motivo(e)
                    logger.warning("  %s", motivo)
                    resumen['pendientes'].append(f"{dominio}: {motivo}")
                    for rv in revistas:
                        marcar_chequeo(rv['id'], f'inaccesible: {motivo}')
                    continue

                if _hay_desafio(page):
                    logger.warning(
                        "  VERIFICACIÓN PENDIENTE en %s — resolvela en la "
                        "ventana. Esperando hasta %ds...", dominio, espera_desafio)
                    limite = time.time() + espera_desafio
                    while time.time() < limite and _hay_desafio(page):
                        time.sleep(2)
                    if _hay_desafio(page):
                        logger.warning("  sin resolver; se saltea %s", dominio)
                        resumen['pendientes'].append(
                            f"{dominio}: verificación sin resolver "
                            f"({len(revistas)} revistas)")
                        for rv in revistas:
                            marcar_chequeo(rv['id'],
                                           'protegido (anti-bot) - revisar a mano')
                        continue
                    logger.info("  verificación resuelta; sesión guardada")

                for rv in revistas:
                    estado, convs, permanente = _procesar_revista(page, rv)
                    hechas += 1

                    if estado == 'desafio':
                        # La sesión venció a mitad del dominio.
                        resumen['pendientes'].append(
                            f"{dominio}: la sesión venció durante la revisión")
                        marcar_chequeo(rv['id'],
                                       'protegido (anti-bot) - revisar a mano')
                        break

                    marcar_chequeo(rv['id'], estado, metodo='navegador asistido')
                    resumen['revisadas'] += 1

                    for c in convs:
                        resumen['convocatorias'] += 1
                        if guardar_convocatoria(
                                rv['id'], c['titulo'], c['descripcion'],
                                c['fecha_cierre'], c['url'],
                                'navegador asistido', es_dossier=c['es_dossier'],
                                tema=c['tema']):
                            resumen['nuevas'] += 1
                    if permanente:
                        marcar_recepcion_permanente(rv['id'], True, permanente)
                        resumen['permanentes'] += 1

                    resumen['detalle'][rv['nombre']] = (
                        f"{estado} · {len(convs)} convocatoria(s)")
                    if progreso:
                        progreso(hechas, total, rv['nombre'])
                    time.sleep(ESPERA_ENTRE_PAGINAS)
        finally:
            contexto.close()

    registrar_actualizacion(
        "navegador",
        f"{resumen['revisadas']}/{total} revistas leídas con navegador asistido; "
        f"{resumen['convocatorias']} convocatorias ({resumen['nuevas']} nuevas)"
        + (f"; {len(resumen['pendientes'])} dominios pendientes"
           if resumen['pendientes'] else ""))
    return resumen


def estado_cola():
    """Resumen de la cola, para mostrar antes de abrir el navegador."""
    init_db()   # asegura las columnas nuevas antes de consultarlas
    cola = revistas_bloqueadas()
    lineas = []
    for dom, rs in sorted(cola.items(), key=lambda x: -len(x[1])):
        con_sesion = sum(1 for r in rs if r['ultima_revision_ok'])
        lineas.append((dom, len(rs), con_sesion))
    return lineas


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')

    if '--cola' in sys.argv:
        filas = estado_cola()
        total = sum(n for _, n, _ in filas)
        print(f"{total} fuentes pendientes en {len(filas)} dominios\n")
        for dom, n, ok in filas:
            print(f"  {n:3} revistas  {dom:42} "
                  f"{'(' + str(ok) + ' con lectura previa)' if ok else ''}")
        sys.exit(0)

    doms = [a for a in sys.argv[1:] if not a.startswith('--')]
    r = revisar(dominios=doms or None,
                progreso=lambda i, t, n: print(f"  [{i}/{t}] {n[:52]}", flush=True))
    print("\nRESUMEN")
    for k in ('dominios', 'revisadas', 'convocatorias', 'nuevas', 'permanentes'):
        print(f"  {k}: {r[k]}")
    for p in r['pendientes']:
        print("  PENDIENTE:", p)
