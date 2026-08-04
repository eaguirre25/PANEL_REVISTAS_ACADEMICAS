"""
Genera el sitio estático para GitHub Pages (carpeta docs/).

GitHub Pages solo sirve archivos estáticos, así que no puede ejecutar la app
Streamlit. Lo que se publica es una *instantánea* navegable de los datos: el
buscador y los filtros corren en el navegador, y la cuenta regresiva de cada
convocatoria se calcula con la fecha del visitante, así no queda desactualizada
entre regeneraciones.

NUNCA se exporta la tabla de suscriptores: contiene correos personales.
"""
import os
import re
import json
import logging
from datetime import date, datetime

from database import conectar, contar, obtener_convocatorias_cerradas

logger = logging.getLogger(__name__)

BASE = os.path.dirname(os.path.abspath(__file__))
DOCS = os.path.join(BASE, 'docs')
CONFIG_SITIO = os.path.join(BASE, 'config_sitio.json')
REPO = "https://github.com/eaguirre25/PANEL_REVISTAS_ACADEMICAS"
SITIO = "https://eaguirre25.github.io/PANEL_REVISTAS_ACADEMICAS"


def _config():
    if os.path.exists(CONFIG_SITIO):
        try:
            with open(CONFIG_SITIO, encoding='utf-8') as f:
                return json.load(f)
        except (OSError, ValueError):
            pass
    return {}


def formulario_suscripcion():
    """
    HTML del formulario del boletín.

    Un sitio estático no puede recibir los datos por sí mismo: hace falta un
    servicio que acepte el POST y le avise al administrador. La URL se define
    en config_sitio.json bajo "formulario_endpoint".

    Con endpoint configurado el envío es directo: el visitante completa,
    aprieta el botón y listo. Sin endpoint queda el modo de reserva, que abre
    un correo ya escrito en el cliente del visitante — funciona sin depender
    de nadie, pero le traslada el trabajo de enviarlo.

    Los campos que empiezan con guion bajo son de FormSubmit; otros servicios
    los ignoran sin romperse.
    """
    cfg = _config()
    endpoint = (cfg.get('formulario_endpoint') or '').strip()

    # Cada campo lleva su <label>: el placeholder se borra al escribir, así que
    # no alcanza como etiqueta para un lector de pantalla.
    campos = '''
      <label class="vo" for="susNombre">Nombre completo</label>
      <input type="text" name="nombre" id="susNombre" required
             placeholder="Nombre completo" autocomplete="name">
      <label class="vo" for="susEmail">Correo electrónico</label>
      <input type="email" name="email" id="susEmail" required
             placeholder="Correo electrónico" autocomplete="email">
      <button type="submit">Suscribirme</button>'''

    if endpoint:
        return (
            f'<form class="susForm" id="susForm" action="{endpoint}" '
            f'method="POST">{campos}'
            '<input type="hidden" name="_subject" '
            'value="Nueva suscripcion al panel de revistas">'
            '<input type="hidden" name="_template" value="table">'
            '<input type="hidden" name="_captcha" value="false">'
            f'<input type="hidden" name="_next" value="{SITIO}/gracias.html">'
            # Trampa para robots: un campo que una persona nunca completa.
            '<input type="text" name="_honey" style="display:none" '
            'tabindex="-1" autocomplete="off" aria-hidden="true">'
            '</form>')

    return f'<form class="susForm" id="susForm" data-modo="correo">{campos}</form>'


# La base no trae disciplina: la columna `area` dice «Ciencias Sociales y
# Humanidades» en las 1007 revistas, y `areas_scimago` solo distingue «Arts and
# Humanities» de «Social Sciences». Así que el tema se deduce de las palabras
# del nombre de la revista y del título de la convocatoria.
#
# Esto es una ayuda de búsqueda, NO una clasificación disciplinar: una revista
# de sociología cuyo nombre no diga «sociología» no va a quedar etiquetada. En
# el panel se rotula como «por palabras del título» para que nadie lo lea como
# un campo verificado.
DISCIPLINAS = {
    'Educación': r'educa|pedagog|docen|enseñan|didáctic|didactic|curricul|escolar|escuela',
    'Sociología': r'sociolog|sociedad|social(es)?\b',
    'Historia': r'histor',
    'Filosofía': r'filosof|filosóf|ética|epistemolog',
    'Antropología': r'antropolog|etnograf|etnolog',
    'Ciencia política': r'polít|politic|gobierno|democracia|estado\b|ciudadan',
    'Economía': r'economí|económ|econom|desarrollo productivo|trabajo y empleo',
    'Comunicación': r'comunicac|periodis|medios\b|mediátic',
    'Psicología': r'psicolog|psicoanál|psicoanal|psíqu|salud mental',
    'Derecho': r'derecho|juríd|juridic|legal|justicia',
    'Geografía y territorio': r'geograf|territor|urban|espacio|región|regional',
    'Letras y literatura': r'literat|letras\b|narrativ|poétic|poetic',
    'Lingüística': r'lingüíst|linguist|lengua|discurs|semiót',
    'Artes': r'\barte|artes\b|estétic|música|musica|visual|cine\b|teatr|diseño',
    'Género y feminismos': r'género|genero\b|feminis|mujer|masculinid|diversidad sexual',
    'Trabajo social': r'trabajo social|intervención social|servicio social',
    'Salud': r'\bsalud|sanitar|médic|medicin|enfermer',
    'Ambiente': r'ambient|ecolog|climát|climatic|sustentab|sostenib',
    'Religión': r'religi|teolog|eclesiást|espiritual',
    'Migraciones': r'migrac|migrant|refugiad|diáspora|movilidad human',
    'Ciencia y tecnología': r'tecnolog|científic|cientific|innovación|digital',
}
_DISC = {n: re.compile(p, re.I) for n, p in DISCIPLINAS.items()}


def disciplinas(*textos):
    """Etiquetas temáticas deducidas del texto. Devuelve lista, puede ser vacía."""
    t = ' '.join(x for x in textos if x)
    return [n for n, rx in _DISC.items() if rx.search(t)]


def _linea_base():
    """Fecha desde la cual una convocatoria puede considerarse «nueva».

    El historial de detección empieza cuando se armó el catálogo, así que en la
    primera corrida TODAS las convocatorias serían «nuevas», lo cual no informa
    nada. Se fija una línea de base al generar el sitio por primera vez con
    esta función: de ahí en adelante, «nueva» significa detectada después.
    """
    ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'linea_base.txt')
    if os.path.exists(ruta):
        with open(ruta, encoding='utf-8') as f:
            valor = f.read().strip()
        if valor:
            return valor
    valor = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with open(ruta, 'w', encoding='utf-8') as f:
        f.write(valor + '\n')
    return valor


def reunir_datos():
    conn = conectar()

    revistas = [dict(f) for f in conn.execute("""
        SELECT nombre, COALESCE(pais,'Argentina') AS pais,
               COALESCE(origen,'NBRA') AS origen, institucion,
               issn_impreso, issn_online, sitio_url, ficha_url,
               nivel_conicet, en_scopus, scopus_estado, en_scielo, en_doaj,
               COALESCE(wos_declarado,0) AS wos_declarado,
               COALESCE(en_scimago,0) AS en_scimago, sjr, cuartil_sjr,
               recepcion_permanente, evidencia_permanente, estado_chequeo,
               ultima_revision_ok, ultimo_chequeo, metodo_revision
        FROM revistas ORDER BY nombre""")]

    # Una revista "requiere revisión manual" si no se pudo leer: su sitio no
    # responde, cambió de dirección o exige registrarse. Las que antes caían
    # acá por protección anti-bot ahora se leen con el navegador asistido.
    # Un solo criterio para toda la app: si no es ninguno de los tres
    # resultados de una lectura exitosa, es porque no se pudo leer. Definirlo
    # por lo que NO es evita que dos partes del código cuenten distinto.
    LEIDA_OK = {'ok', 'sin convocatorias', 'sin pagina de anuncios'}
    for r in revistas:
        estado = r['estado_chequeo']
        r['revision_manual'] = (
            1 if (r['sitio_url'] and estado and estado not in LEIDA_OK) else 0)

    convocatorias = [dict(f) for f in conn.execute("""
        SELECT c.titulo, c.descripcion, c.fecha_cierre, c.url,
               COALESCE(c.es_dossier,0) AS es_dossier, c.tema,
               c.fecha_encontrada, c.fuente,
               r.nombre AS revista, COALESCE(r.pais,'Argentina') AS pais,
               r.nivel_conicet, r.en_scopus, r.scopus_estado,
               r.en_scielo, r.en_doaj, COALESCE(r.wos_declarado,0) AS wos_declarado,
               COALESCE(r.en_scimago,0) AS en_scimago, r.sjr, r.cuartil_sjr,
               r.ultima_revision_ok, r.estado_chequeo
        FROM convocatorias c JOIN revistas r ON r.id = c.revista_id
        WHERE c.activa = 1
        ORDER BY c.fecha_cierre IS NULL, c.fecha_cierre""")]

    cerradas = obtener_convocatorias_cerradas(meses=8)

    linea_base = _linea_base()
    for c in convocatorias:
        c['disc'] = disciplinas(c['revista'], c['titulo'], c['tema'])
        c['nueva'] = 1 if (c['fecha_encontrada'] or '') > linea_base else 0
    for r in revistas:
        r['disc'] = disciplinas(r['nombre'])

    estados = [dict(f) for f in conn.execute("""
        SELECT COALESCE(estado_chequeo,'no revisada') AS estado, COUNT(*) AS n
        FROM revistas GROUP BY estado ORDER BY n DESC""")]

    conn.close()

    stats = {
        'revistas': len(revistas),
        'nbra': sum(1 for r in revistas if r['origen'] == 'NBRA'),
        'externas': sum(1 for r in revistas if r['origen'] == 'externa'),
        'paises': len({r['pais'] for r in revistas}),
        'convocatorias': len(convocatorias),
        'dossiers': sum(1 for c in convocatorias if c['es_dossier']),
        'con_tema': sum(1 for c in convocatorias if c['tema']),
        'con_fecha': sum(1 for c in convocatorias if c['fecha_cierre']),
        'permanentes': sum(1 for r in revistas if r['recepcion_permanente'] == 1),
        # Con sitio web el rastreador puede seguir sus convocatorias; sin él,
        # la revista entra al catálogo como referencia.
        'con_seguimiento': sum(1 for r in revistas if r['sitio_url']),
        'solo_referencia': sum(1 for r in revistas if not r['sitio_url']),
        'con_sjr': sum(1 for r in revistas if r['en_scimago']),
        'q1': sum(1 for r in revistas if r['cuartil_sjr'] == 'Q1'),
        'q2': sum(1 for r in revistas if r['cuartil_sjr'] == 'Q2'),
        'q3': sum(1 for r in revistas if r['cuartil_sjr'] == 'Q3'),
        'q4': sum(1 for r in revistas if r['cuartil_sjr'] == 'Q4'),
        'sin_cuartil': sum(1 for r in revistas
                           if r['en_scimago'] and not r['cuartil_sjr']),
        # Partición del catálogo: las cuatro categorías siguientes son
        # excluyentes y suman el total. Sin esto, las métricas del encabezado
        # mezclan convocatorias con revistas y no hay forma de que cierren.
        'rev_con_conv': sum(
            1 for r in revistas if r['sitio_url'] and r['estado_chequeo'] == 'ok'),
        'rev_sin_conv': sum(
            1 for r in revistas
            if r['sitio_url'] and r['estado_chequeo'] == 'sin convocatorias'),
        'rev_sin_pagina': sum(
            1 for r in revistas
            if r['sitio_url'] and r['estado_chequeo'] == 'sin pagina de anuncios'),
        # Tienen dirección pero el rastreador todavía no pasó: aparecen al
        # incorporar sitios nuevos, entre una corrida semanal y la siguiente.
        # Sin esta categoría la partición no cierra.
        'rev_sin_revisar': sum(
            1 for r in revistas if r['sitio_url'] and not r['estado_chequeo']),
        'cerradas': len(cerradas),
        'cerradas_sigue_abierta': sum(
            1 for c in cerradas if c['revista_permanente'] or c['sigue_recibiendo']),
        'revision_manual': sum(1 for r in revistas if r['revision_manual']),
        'nuevas': sum(1 for c in convocatorias if c['nueva']),
        'linea_base': linea_base[:10],
        'nivel1': sum(1 for r in revistas if r['nivel_conicet'] == 1),
        'nivel2': sum(1 for r in revistas if r['nivel_conicet'] == 2),
        'scopus': sum(1 for r in revistas if r['en_scopus']),
        'scielo': sum(1 for r in revistas if r['en_scielo']),
        'doaj': sum(1 for r in revistas if r['en_doaj']),
        'generado': datetime.now().strftime('%d/%m/%Y %H:%M'),
    }
    return revistas, convocatorias, cerradas, estados, stats


CSS = """
*,*::before,*::after{box-sizing:border-box}
:root{
  --a1:#0891b2; --a2:#059669; --a3:#7c3aed;
  --grad:linear-gradient(135deg,var(--a1),var(--a2));
  --pag:#fbfbfe; --sup:rgba(255,255,255,.72); --sup2:rgba(255,255,255,.62);
  --borde:rgba(255,255,255,.75); --borde2:rgba(24,20,37,.12);
  --fg:#181425; --fg2:#4b5265; --fg3:#6b7280; --fg4:#9ca3af;
  --chip:#eef2f6; --chipFg:#475569;
  --sombra:0 6px 20px rgba(15,23,42,.06);
  --sombraAlta:0 16px 40px rgba(8,145,178,.28);
  --op:.30;
  /* Colores de señal. Van como variables y no como reglas sueltas porque el
     tema oscuro llega por dos caminos —el interruptor y la preferencia del
     sistema— y una regla escrita solo para [data-theme=dark] deja sin
     corregir a quien nunca toca el interruptor, que son casi todos. */
  --amb:#b45309; --rojoTxt:#b91c1c; --verdeTxt:#047857; --violTxt:#6d28d9;
  --markBg:rgba(8,145,178,.22);
  --ojoBg:rgba(245,158,11,.10); --reabreBg:rgba(21,128,61,.10);
}
:root[data-theme=dark]{
  --a1:#22d3ee; --a2:#34d399; --a3:#a78bfa;
  --pag:#0b0d12; --sup:rgba(30,35,45,.72); --sup2:rgba(30,35,45,.55);
  --borde:rgba(255,255,255,.09); --borde2:rgba(255,255,255,.14);
  --fg:#eceef4; --fg2:#b3bccb; --fg3:#8e99ab; --fg4:#6b7688;
  --chip:rgba(255,255,255,.08); --chipFg:#b3bccb;
  --sombra:0 6px 20px rgba(0,0,0,.35);
  --sombraAlta:0 16px 40px rgba(0,0,0,.5);
  --op:.20;
  --amb:#fcd34d; --rojoTxt:#fca5a5; --verdeTxt:#6ee7a0; --violTxt:#c4b5fd;
  --markBg:rgba(34,211,238,.26);
  --ojoBg:rgba(252,211,77,.10); --reabreBg:rgba(110,231,160,.10);
}
@media (prefers-color-scheme:dark){
  :root:not([data-theme=light]){
    --a1:#22d3ee; --a2:#34d399; --a3:#a78bfa;
    --pag:#0b0d12; --sup:rgba(30,35,45,.72); --sup2:rgba(30,35,45,.55);
    --borde:rgba(255,255,255,.09); --borde2:rgba(255,255,255,.14);
    --fg:#eceef4; --fg2:#b3bccb; --fg3:#8e99ab; --fg4:#6b7688;
    --chip:rgba(255,255,255,.08); --chipFg:#b3bccb;
    --sombra:0 6px 20px rgba(0,0,0,.35);
    --sombraAlta:0 16px 40px rgba(0,0,0,.5);
    --op:.20;
    --amb:#fcd34d; --rojoTxt:#fca5a5; --verdeTxt:#6ee7a0; --violTxt:#c4b5fd;
    --markBg:rgba(34,211,238,.26);
    --ojoBg:rgba(252,211,77,.10); --reabreBg:rgba(110,231,160,.10);
  }
}

@keyframes drift1{0%,100%{transform:translate(-4%,-6%) scale(1)}
  50%{transform:translate(7%,5%) scale(1.18)}}
@keyframes drift2{0%,100%{transform:translate(5%,4%) scale(1.1)}
  50%{transform:translate(-7%,-8%) scale(.95)}}
@keyframes drift3{0%,100%{transform:translate(-4%,5%) scale(1)}
  50%{transform:translate(8%,-5%) scale(1.15)}}

html{scroll-behavior:smooth}
body{margin:0;background:var(--pag);color:var(--fg);
  font:16px/1.55 Manrope,system-ui,-apple-system,"Segoe UI",sans-serif;
  -webkit-font-smoothing:antialiased}
.env{max-width:1180px;margin:0 auto;padding:0 22px}
.bgfx{position:fixed;inset:0;z-index:0;overflow:hidden;pointer-events:none}
.bgfx div{position:absolute;border-radius:50%;filter:blur(50px);opacity:var(--op)}
.b1{top:-12%;left:-12%;width:58vw;height:58vw;
  background:radial-gradient(circle,#7c3aed,transparent 70%);
  animation:drift1 22s ease-in-out infinite}
.b2{top:8%;right:-16%;width:52vw;height:52vw;
  background:radial-gradient(circle,#0891b2,transparent 70%);
  animation:drift2 26s ease-in-out infinite}
.b3{bottom:-16%;left:18%;width:50vw;height:50vw;
  background:radial-gradient(circle,#059669,transparent 70%);
  animation:drift3 30s ease-in-out infinite}
.b4{bottom:2%;right:8%;width:38vw;height:38vw;
  background:radial-gradient(circle,#f59e0b,transparent 70%);
  animation:drift1 24s ease-in-out infinite reverse}
.wrap{position:relative;z-index:1}
@media (prefers-reduced-motion:reduce){.bgfx div{animation:none}}

header{padding:34px 0 20px}
/* El botón de tema sale del flujo para que el título mida lo mismo que el
   texto de abajo y que la franja del boletín: si va como hermano flex, se
   lleva su ancho y el h1 queda más corto que todo lo demás. */
.hcab{position:relative}
#tema{position:absolute;top:0;right:0}
h1{font-family:'Bricolage Grotesque',system-ui,sans-serif;font-weight:800;
  font-size:clamp(27px,4.4vw,48px);line-height:1.06;letter-spacing:-.02em;
  margin:0 0 12px;padding-right:56px;background:var(--grad);
  -webkit-background-clip:text;background-clip:text;color:transparent}
/* Sin max-width: el texto de presentación y el aviso ocupan el mismo ancho
   que el título y la franja del boletín, en lugar de cortarse antes. */
.sub{margin:0 0 9px;color:var(--fg2);font-size:16px}
.sub b{color:var(--fg)}
.firma{margin:0 0 16px;color:var(--fg3);font-size:13.5px}
.firma b{color:var(--fg)}
/* Señalador de la última corrida automática. */
.sello{display:inline-flex;align-items:center;gap:8px;background:var(--sup2);
  border:1px solid var(--borde);border-radius:999px;padding:6px 15px;
  font-size:13px;color:var(--fg2);margin:0 0 14px}
.sello .punto{width:8px;height:8px;border-radius:50%;background:var(--a2);
  box-shadow:0 0 0 3px rgba(5,150,105,.22);flex:none}
.sello b{color:var(--fg)}
/* Advertencia principal: es lo que evita que alguien confíe de más. */
.ojo{border:2px solid var(--amb);background:var(--ojoBg);
  border-radius:14px;padding:15px 19px;margin:0 0 20px}
.ojo b{color:var(--amb);letter-spacing:.02em}
.ojo p{margin:6px 0 0;color:var(--fg2);font-size:14.5px;line-height:1.55}
.firma a,.enlaces a,.tarj a,.rcard a{color:var(--a1);text-decoration:none;
  font-weight:650}
.firma a:hover,.enlaces a:hover,.tarj a:hover,.rcard a:hover{
  text-decoration:underline}
#tema{background:var(--sup2);border:1px solid var(--borde);color:var(--fg);
  border-radius:11px;width:44px;height:44px;font-size:17px;cursor:pointer;
  flex:none}

.stats{display:grid;gap:10px;grid-template-columns:repeat(auto-fit,minmax(150px,1fr))}
.st{background:var(--sup2);border:1.5px solid var(--borde);border-radius:14px;
  padding:13px 15px;text-align:left;cursor:pointer;font-family:inherit;
  box-shadow:var(--sombra);transition:transform .15s}
.st:hover{transform:translateY(-2px)}
.st:focus-visible{outline:2px solid var(--a1);outline-offset:2px}
.st b{display:block;font-family:'Bricolage Grotesque',system-ui,sans-serif;
  font-size:25px;letter-spacing:-.02em;color:var(--fg)}
.st span{color:var(--fg3);font-size:12.5px}
.st.urg{background:rgba(220,38,38,.09);border-color:rgba(220,38,38,.35)}
.st.urg b,.st.urg span{color:var(--rojoTxt)}
.st.man{background:rgba(180,83,9,.1);border-color:rgba(180,83,9,.32)}
.st.man b,.st.man span{color:var(--amb)}
.st.ok{background:rgba(5,150,105,.10);border-color:rgba(5,150,105,.30)}
.st.ok b,.st.ok span{color:var(--verdeTxt)}
.st.ref{background:var(--chip);border-color:transparent;opacity:.85}
/* Rótulo que dice qué unidad cuenta el grupo de abajo: sin esto las cajas de
   convocatorias y las de revistas se leen como una sola serie sumable. */
.rotulo{margin:20px 0 8px;font-size:12.5px;text-transform:uppercase;
  letter-spacing:.09em;color:var(--fg3);font-weight:700;
  font-family:'Bricolage Grotesque',system-ui,sans-serif}
.rotulo b{color:var(--fg);font-size:14px}
.rotulo .acota{display:block;text-transform:none;letter-spacing:0;
  font-weight:500;font-size:12.5px;color:var(--fg4);margin-top:2px}
.acota.suelta{margin:10px 0 0;font-size:13px;color:var(--fg3);line-height:1.55;
  max-width:78ch;background:var(--bg2);border-radius:9px;padding:11px 14px}
.acota.suelta b{color:var(--fg)}
/* Desglose del catálogo, en Cobertura: cada línea explica qué significa esa
   categoría, que en una caja de dos palabras no entra. */
.desglose{display:grid;gap:2px;margin-bottom:18px}
.dl{display:grid;grid-template-columns:66px 1fr;gap:12px;align-items:baseline;
  padding:9px 11px;border-radius:8px;cursor:pointer}
.dl:hover{background:var(--bg2)}
.dl b{font-family:'Bricolage Grotesque',system-ui,sans-serif;font-size:19px;
  text-align:right;font-variant-numeric:tabular-nums}
.dl span{color:var(--fg2);font-size:13.5px;line-height:1.5}
.stats2{margin:12px 0 0;display:flex;gap:2px;flex-wrap:wrap;color:var(--fg3);
  font-size:13px;align-items:center}
.stats2 button{background:none;border:0;font-family:inherit;font-size:13px;
  color:var(--fg3);cursor:pointer;padding:4px 9px;border-radius:7px}
.stats2 button:hover{background:var(--chip);color:var(--fg)}
.stats2 b{color:var(--fg)}
.enlaces{display:flex;gap:18px;flex-wrap:wrap;margin-top:18px}
.enlaces a{font-size:14px}

nav{position:sticky;top:0;z-index:20;background:var(--pag);
  border-bottom:1px solid var(--borde2)}
@supports (backdrop-filter:blur(1px)){
  nav{background:color-mix(in srgb,var(--pag) 80%,transparent);
    backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px)}
}
nav .env{padding:10px 22px;display:flex;gap:14px;flex-wrap:wrap;
  align-items:center}
.segs{display:flex;gap:4px;background:var(--chip);padding:4px;
  border-radius:12px}
.segs button{background:none;color:var(--fg2);border:0;border-radius:9px;
  padding:9px 16px;font-size:14.5px;font-weight:650;cursor:pointer;
  font-family:inherit;white-space:nowrap}
.segs button[aria-selected=true]{background:var(--grad);color:#fff}
input[type=search],select{background:var(--sup);border:1px solid var(--borde2);
  border-radius:11px;padding:11px 14px;font-size:15px;font-family:inherit;
  min-height:44px;color:var(--fg)}
input[type=search]{flex:1;min-width:200px}
/* El buscador salió de la barra fija y ahora abre los resultados, debajo del
   aviso de lo que cierra esta semana. Fuera de un contenedor flex necesita
   pedir el ancho explícitamente. */
#q{width:100%;margin:0 0 2px}
input:focus-visible,select:focus-visible{outline:2px solid var(--a1);
  outline-offset:-1px}

main{padding:24px 0 80px}
.conteo{color:var(--fg3);font-size:13.5px;margin:0 0 12px}
.urgente{background:rgba(220,38,38,.09);border:1px solid rgba(220,38,38,.35);
  border-radius:14px;padding:14px 18px;margin-bottom:18px;color:var(--rojoTxt);
  font-weight:650;font-size:15px}
.urgente.man{background:rgba(180,83,9,.1);border-color:rgba(180,83,9,.32);
  color:var(--amb);font-weight:400}
.grupo{margin:28px 0 12px;display:flex;align-items:baseline;gap:10px}
.grupo h2{margin:0;font-size:13px;text-transform:uppercase;letter-spacing:.08em;
  color:var(--fg3);font-weight:700;
  font-family:'Bricolage Grotesque',system-ui,sans-serif}
.grupo .n{color:var(--fg4);font-size:12.5px}
.grupo::after{content:"";flex:1;height:1px;
  background:linear-gradient(90deg,var(--borde2),transparent)}

/* Las tarjetas NO llevan backdrop-filter: con 174 en pantalla el desenfoque
   se recalcula en cada scroll y traba el desplazamiento en equipos modestos.
   El efecto de vidrio se reserva para el nav y los bloques grandes. */
.tarj{display:grid;grid-template-columns:88px 1fr;background:var(--sup);
  border:1px solid var(--borde);border-radius:16px;margin-bottom:11px;
  box-shadow:var(--sombra);overflow:hidden}
.gutter{padding:14px 6px;display:flex;flex-direction:column;align-items:center;
  justify-content:center;gap:2px}
.gnum{font-family:'Bricolage Grotesque',system-ui,sans-serif;font-weight:800;
  font-size:24px;line-height:1}
.gtxt{font-size:10px;text-transform:uppercase;letter-spacing:.05em;
  font-weight:700;opacity:.9}
.cuerpo{padding:15px 18px;min-width:0}
.rev{font-weight:700;font-size:15px}
.tit{margin-top:5px;line-height:1.5;color:var(--fg2)}
.tema{margin-top:10px;padding:11px 14px;background:rgba(124,58,237,.09);
  border-radius:10px;font-size:14.5px;line-height:1.5}
.tema b{color:var(--a1)}
.meta{margin-top:10px;display:flex;flex-wrap:wrap;gap:6px;align-items:center}
.meta>span.fecha{color:var(--fg3);font-size:12.5px}
.pais{color:var(--fg4);font-size:12px}
.chip{background:var(--chip);color:var(--chipFg);border-radius:20px;
  padding:3px 10px;font-size:11.5px;font-weight:650}
.cita{font-style:italic;color:var(--fg3);font-size:14px;line-height:1.5;
  border-left:3px solid #15803d;padding-left:12px;margin-top:10px}
.acciones{display:flex;gap:14px;flex-wrap:wrap;align-items:center;margin-top:10px}
.acciones>a{margin-top:0}
/* Agendar es secundario: no debe competir con el enlace a la convocatoria,
   que es lo que la persona vino a abrir. */
a.cal{display:inline-flex;align-items:center;gap:6px;font-size:13px;
  color:var(--fg2)!important;border:1px solid var(--borde2);border-radius:9px;
  padding:6px 12px;background:var(--sup2)}
a.cal:hover{color:var(--a1)!important;border-color:var(--a1);
  text-decoration:none!important}
a.cal svg{flex:none}
/* Lo que sigue vigente pese al cierre: reapertura o recepción abierta. */
.reabre{margin-top:10px;padding:10px 13px;background:var(--reabreBg);
  border-radius:9px;font-size:14px;line-height:1.5}

.revgrid{display:grid;gap:13px;
  grid-template-columns:repeat(auto-fill,minmax(320px,1fr))}
.rcard{background:var(--sup);border:1px solid var(--borde);border-radius:14px;
  padding:15px 18px;display:flex;flex-direction:column;gap:8px;
  box-shadow:var(--sombra)}
.rcard .top{display:flex;justify-content:space-between;gap:10px;
  align-items:baseline}
.rcard .nombre{font-weight:700;font-size:14.5px}
.rcard .inst{color:var(--fg3);font-size:12.5px}
.rcard .issn{color:var(--fg4);font-size:12px}
.rcard .motivo{color:var(--amb);font-size:12.5px;font-weight:650}
.masbtn{display:block;margin:18px auto 0;background:var(--sup);
  border:1px solid var(--borde2);border-radius:11px;padding:11px 22px;
  font-size:14px;font-weight:650;font-family:inherit;cursor:pointer;
  color:var(--a1)}

/* ── boletín ─────────────────────────────────────────────────────── */
.boletin{margin:26px 0 30px;padding:26px 28px;border-radius:20px;
  background:var(--grad);color:#fff;box-shadow:var(--sombraAlta)}
.boletin h3{margin:0 0 8px;
  font-family:'Bricolage Grotesque',system-ui,sans-serif;font-size:21px}
.boletin p{margin:0 0 16px;opacity:.94;max-width:62ch;font-size:15px}
.boletin a{color:#fff;text-decoration:underline}
.boletin .nota{margin:14px 0 0;font-size:12.5px;opacity:.82}
.susForm{display:flex;gap:9px;flex-wrap:wrap}
.susForm input{flex:1;min-width:190px;background:rgba(255,255,255,.96);
  border:0;border-radius:11px;padding:13px 15px;font-size:15px;
  font-family:inherit;color:#181425;min-height:48px}
.susForm input:focus-visible{outline:3px solid rgba(255,255,255,.6);
  outline-offset:1px}
.susForm button{background:#fff;color:var(--a1);border:0;border-radius:11px;
  padding:13px 26px;font-size:15px;font-weight:750;cursor:pointer;
  font-family:inherit;min-height:48px;white-space:nowrap}
.susForm button:hover{transform:translateY(-1px)}
.susOk{background:rgba(255,255,255,.18);border-radius:11px;padding:13px 16px;
  font-size:14.5px;margin:0}

.cobertura{margin-top:32px;background:var(--sup2);border:1px solid var(--borde);
  border-radius:16px;padding:22px 24px}
.cobertura h3{font-family:'Bricolage Grotesque',system-ui,sans-serif;
  font-size:16px;margin:0 0 14px}
.barra{display:flex;width:100%;height:14px;border-radius:8px;overflow:hidden;
  background:var(--chip)}
.leyenda{display:flex;flex-wrap:wrap;gap:14px;margin-top:14px;font-size:13px;
  color:var(--fg2)}
.leyenda .dot{width:9px;height:9px;border-radius:3px;display:inline-block;
  margin-right:6px}

.aviso{background:var(--sup2);border:1px solid var(--borde);
  border-left:4px solid #b45309;border-radius:16px;padding:22px 24px;
  margin:28px 0}
.aviso h3{margin:0 0 14px;font-size:15.5px;
  font-family:'Bricolage Grotesque',system-ui,sans-serif}
.aviso ol{margin:0;padding-left:20px}
.aviso li{margin-bottom:10px;color:var(--fg2);line-height:1.55}
.aviso li b{color:var(--fg)}
footer{border-top:1px solid var(--borde2);color:var(--fg3);font-size:13.5px;
  padding:26px 0 50px;line-height:1.6}
footer a{color:var(--a1)}
/* !important porque hay reglas posteriores con display propio (.expo, .facetas):
   sin esto ganaban por orden de aparición y el bloque seguía ocupando lugar
   aun estando «oculto». */
.oculto{display:none!important}

/* ── barra de filtros ─────────────────────────────────────────────── */
/* Un <details> por faceta: se pueden combinar varias condiciones a la vez,
   que antes era imposible porque un único <select> solo admite una. */
.facetas{display:flex;gap:7px;flex-wrap:wrap;align-items:center;
  margin:14px 0 0}
.fac{position:relative}
.fac>summary{list-style:none;cursor:pointer;background:var(--sup);
  border:1px solid var(--borde2);border-radius:10px;padding:9px 13px;
  font-size:13.5px;font-weight:600;color:var(--fg2);white-space:nowrap;
  min-height:40px;display:flex;align-items:center;gap:6px}
.fac>summary::-webkit-details-marker{display:none}
.fac>summary::after{content:"▾";font-size:10px;opacity:.6}
.fac[open]>summary{border-color:var(--a1);color:var(--fg)}
.fac>summary:focus-visible{outline:2px solid var(--a1);outline-offset:2px}
.fac>summary .cuenta{background:var(--a1);color:#fff;border-radius:20px;
  padding:1px 7px;font-size:11px;font-weight:700}
.menu{position:absolute;z-index:30;top:calc(100% + 6px);left:0;min-width:230px;
  max-height:340px;overflow:auto;background:var(--pag);
  border:1px solid var(--borde2);border-radius:12px;padding:7px;
  box-shadow:0 12px 34px rgba(15,23,42,.18)}
.menu label{display:flex;align-items:center;gap:9px;padding:9px 10px;
  border-radius:8px;font-size:14px;cursor:pointer;min-height:40px;
  color:var(--fg2)}
.menu label:hover{background:var(--chip);color:var(--fg)}
.menu input{accent-color:var(--a1);width:17px;height:17px;flex:none}
.menu .sep{border-top:1px solid var(--borde2);margin:5px 0}

/* Filtros activos: sin esto no hay forma de saber qué condiciones se están
   aplicando ni de sacar una sola sin empezar de nuevo. */
.activos{display:flex;gap:7px;flex-wrap:wrap;align-items:center;margin:12px 0 0}
.fchip{display:inline-flex;align-items:center;gap:7px;background:var(--sup);
  border:1px solid var(--a1);color:var(--fg);border-radius:20px;
  padding:5px 6px 5px 13px;font-size:13px;font-weight:600}
.fchip button{background:var(--chip);border:0;border-radius:50%;width:22px;
  height:22px;cursor:pointer;color:var(--fg2);font-size:14px;line-height:1;
  font-family:inherit;display:flex;align-items:center;justify-content:center}
.fchip button:hover{background:#dc2626;color:#fff}
.limpiar{background:none;border:0;color:var(--a1);font-family:inherit;
  font-size:13px;font-weight:700;cursor:pointer;padding:6px 10px;
  border-radius:8px;min-height:36px}
.limpiar:hover{background:var(--chip)}

.barrares{display:flex;justify-content:space-between;align-items:center;
  gap:14px;flex-wrap:wrap;margin:18px 0 12px}
.barrares .conteo{margin:0}
.conteo b{color:var(--fg);font-size:15px}
.ordenar{display:flex;align-items:center;gap:7px;font-size:13px;
  color:var(--fg3)}
.ordenar select{padding:7px 11px;font-size:13.5px;min-height:38px}

mark{background:var(--markBg);color:var(--fg);border-radius:3px;
  padding:0 2px;font-weight:700}

/* Estado vacío: decir qué quitar es más útil que «sin resultados». */
.vacio{background:var(--sup2);border:1px dashed var(--borde2);
  border-radius:16px;padding:30px 26px;text-align:center}
.vacio h3{margin:0 0 8px;font-size:17px;
  font-family:'Bricolage Grotesque',system-ui,sans-serif}
.vacio p{margin:0 0 16px;color:var(--fg2);font-size:14.5px}
.vacio .acc{display:flex;gap:10px;justify-content:center;flex-wrap:wrap}
.vacio button{background:var(--sup);border:1px solid var(--borde2);
  border-radius:10px;padding:10px 18px;font-family:inherit;font-size:14px;
  font-weight:650;cursor:pointer;color:var(--a1);min-height:44px}

/* Guardar: la selección vive en el navegador, sin cuenta ni registro. */
.guardar{display:inline-flex;align-items:center;gap:6px;font-size:13px;
  background:var(--sup2);border:1px solid var(--borde2);border-radius:9px;
  padding:6px 12px;cursor:pointer;font-family:inherit;color:var(--fg2);
  min-height:36px}
.guardar:hover{border-color:var(--a1);color:var(--a1)}
.guardar[aria-pressed=true]{background:rgba(245,158,11,.14);
  border-color:#d97706;color:var(--amb)}
.reportar{font-size:12.5px;color:var(--fg4)!important;font-weight:500!important}
.expo{margin:0 0 18px}
.expoBotones{display:flex;gap:10px;flex-wrap:wrap}
.notaGuard{margin:11px 0 0;font-size:12.5px;color:var(--fg3);line-height:1.5;
  max-width:78ch}
.notaGuard b{color:var(--fg)}
.expo button{background:var(--sup);border:1px solid var(--borde2);
  border-radius:10px;padding:10px 16px;font-family:inherit;font-size:13.5px;
  font-weight:650;cursor:pointer;color:var(--a1);min-height:44px}
.expo button:hover{border-color:var(--a1)}

/* Verificación por tarjeta: más útil que repetir la advertencia general. */
/* --fg3 y no --fg4: a 12px, --fg4 se quedaba en 4,23 de contraste sobre el
   fondo oscuro y el mínimo AA para texto normal es 4,5. */
.verif{margin-top:9px;font-size:12px;color:var(--fg3);display:flex;
  align-items:center;gap:6px}
.verif.mal{color:var(--amb)}
.chip.nueva{background:rgba(5,150,105,.16);color:var(--verdeTxt)}
.chip.dos{background:rgba(124,58,237,.14);color:var(--violTxt)}

/* Franja compacta del boletín, intercalada entre resultados. */
.franja{display:flex;align-items:center;justify-content:space-between;gap:14px;
  flex-wrap:wrap;background:var(--grad);color:#fff;border-radius:14px;
  padding:15px 20px;margin:16px 0;box-shadow:var(--sombra)}
.franja p{margin:0;font-size:14.5px;font-weight:600}
.franja a{background:#fff;color:var(--a1);text-decoration:none;font-weight:750;
  border-radius:10px;padding:9px 18px;font-size:14px;white-space:nowrap}

.saltar{position:absolute;left:-9999px;background:var(--a1);color:#fff;
  padding:12px 20px;border-radius:0 0 10px 0;z-index:99;font-weight:700}
.saltar:focus{left:0;top:0}
/* Etiquetas para lectores de pantalla: el placeholder desaparece al escribir,
   así que no sirve como etiqueta del campo. */
.vo{position:absolute;width:1px;height:1px;padding:0;margin:-1px;
  overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap;border:0}

/* Las cajas de conteos van SIEMPRE visibles. Solo en pantallas chicas se
   pliegan detrás de un botón, porque ahí empujaban la primera convocatoria
   fuera de la vista.
   No se usa <details> a propósito: para dejarlo desplegado en escritorio hay
   que anular el plegado nativo con display:contents, y eso no se comporta
   igual en todos los navegadores. Un div más un botón que solo existe en
   móvil da el mismo resultado sin depender de eso. */
.verMas{display:none}

@media(max-width:760px){
  .tarj{grid-template-columns:70px 1fr}
  .gnum{font-size:21px}
  header{padding:20px 0 12px}
  .env{padding:0 16px}
  nav .env{padding:10px 16px;gap:9px}
  .segs{width:100%;justify-content:space-between}
  .segs button{flex:1;padding:9px 6px;font-size:13px}
  /* Buscador en una fila entera: en una sola fila con los filtros quedaba
     ilegible ("Tod...", "Tod..."). */
  input[type=search]{flex:1 0 100%;min-width:0}
  select{flex:1 1 0;min-width:0}
  .boletin{padding:20px 18px}
  .susForm input,.susForm button{flex:1 0 100%}
  /* Las facetas se apilan, pero el menú desplegable NO puede ir dentro de un
     contenedor con overflow: lo recortaría. Por eso se deja que envuelvan. */
  .fac>summary{padding:9px 11px;font-size:13px}
  .menu{min-width:0;width:max-content;max-width:min(300px,86vw);max-height:52vh}
  .fac:nth-child(n+3) .menu{left:auto;right:0}
  .barrares{align-items:flex-start}
  /* Lo que se sacrifica en el encabezado es lo que ya está dicho en otro
     lado: el subtítulo repite las cifras de las cajas, y la firma completa
     está en el pie. La advertencia se queda, más compacta. */
  .sub{display:none}
  h1{font-size:23px;margin-bottom:9px;padding-right:46px}
  .sello{font-size:11.5px;padding:5px 11px;margin-bottom:9px}
  .firma{font-size:12px;margin-bottom:11px}
  .ojo{padding:11px 13px;margin-bottom:13px;border-width:1.5px}
  .ojo b{font-size:14px}
  .ojo p{font-size:12.5px;margin-top:4px}
  #tema{width:38px;height:38px}
  .franja{flex-direction:column;align-items:stretch;padding:12px 15px;gap:10px;
    margin:10px 0 14px}
  .franja p{font-size:13.5px}
  .franja a{text-align:center;padding:10px 16px;font-size:13.5px}
  .verMas{display:flex;align-items:center;justify-content:center;gap:7px;
    width:100%;background:var(--sup);border:1px solid var(--borde2);
    border-radius:11px;padding:12px 15px;font-family:inherit;font-size:14px;
    font-weight:700;color:var(--a1);cursor:pointer;min-height:44px;
    margin:0 0 14px}
  .verMas::after{content:"▾";font-size:11px}
  .verMas[aria-expanded=true]::after{content:"▴"}
  .metricas{display:none}
  .metricas.abierto{display:block}
}
"""

JS = """
// Los datos se cargan desde datos.json en vez de incrustarse en el HTML:
// al inlinear ~400 KB de JSON el parser cortaba el <script> a la mitad.
let D = {revistas:[], convocatorias:[], estadisticas:{}};
let seccion = 'conv';
const PAGINA = 40;
let limite = PAGINA;
const hoy = new Date(); hoy.setHours(0,0,0,0);

// Estado de la búsqueda. Vive en un solo objeto para poder volcarlo a la URL
// y reconstruirlo al recargar: antes los filtros existían solo en el DOM y una
// recarga los perdía.
const F = {q:'', pais:[], tipo:[], plazo:'', disc:[], indiz:[], cuartil:[],
           nivel:[], estado:'', nuevas:false, orden:''};

const LISTA = ['pais','tipo','disc','indiz','cuartil','nivel'];

// Las convocatorias guardadas viven en el navegador: no hay cuenta ni registro,
// y por lo tanto tampoco datos personales del lado del sitio.
let guardadas = [];
try{ guardadas = JSON.parse(localStorage.getItem('guardadas')||'[]'); }catch(e){}
function idConv(c){ return c.url || (c.revista+'|'+c.titulo); }
function estaGuardada(c){ return guardadas.indexOf(idConv(c))>=0; }
function alternarGuardada(c){
  const i = guardadas.indexOf(idConv(c));
  if(i>=0) guardadas.splice(i,1); else guardadas.push(idConv(c));
  try{ localStorage.setItem('guardadas', JSON.stringify(guardadas)); }catch(e){}
  document.querySelectorAll('[data-guard]').forEach(b=>{
    b.textContent = ' Guardadas ('+guardadas.length+')';
  });
}
function convGuardadas(){
  const t = (D.convocatorias||[]).concat(D.cerradas||[]);
  const vistos = {};
  return t.filter(c=>{
    const k=idConv(c);
    if(!estaGuardada(c) || vistos[k]) return false;
    vistos[k]=1; return true;
  });
}

function dias(f){
  if(!f) return null;
  const p = String(f).slice(0,10).split('-');
  if(p.length!==3) return null;
  const d = new Date(+p[0], +p[1]-1, +p[2]); d.setHours(0,0,0,0);
  return Math.round((d-hoy)/86400000);
}
function nivelUrg(d){
  if(d===null) return 4;
  if(d<=3) return 0;
  if(d<=7) return 1;
  if(d<=21) return 2;
  return 3;
}
const GUTTER=[{bg:'#fee2e2',fg:'#b91c1c'},{bg:'#ffe4cc',fg:'#c2410c'},
  {bg:'#fef3c7',fg:'#a16207'},{bg:'#dcfce7',fg:'#15803d'},
  {bg:'#eef2f6',fg:'#64748b'}];
const GRUPOS=[{t:'Cierran en 3 días o menos',u:0},{t:'Esta semana',u:1},
  {t:'Este mes',u:2},{t:'Más adelante',u:3},
  {t:'Sin fecha de cierre declarada',u:4}];

function plazoPartes(d){
  if(d===null) return ['—','sin fecha'];
  if(d<0) return ['—','vencida'];
  if(d===0) return ['hoy','cierra'];
  return [String(d), d===1?'día':'días'];
}
function esc(s){
  return String(s==null?'':s).replace(/[&<>"']/g,
    c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

// Búsqueda sin tildes. Se normaliza carácter por carácter para que el texto
// normalizado tenga las mismas posiciones que el original: así el resaltado
// puede cortar sobre el texto real sin desalinearse.
function norm(s){
  let r='';
  for(const ch of String(s==null?'':s)){
    const d = ch.normalize('NFD').replace(/[\\u0300-\\u036f]/g,'');
    r += (d.length===1 ? d : ch).toLowerCase();
  }
  return r;
}
function palabras(q){ return norm(q).split(/\\s+/).filter(Boolean); }
// Coincide si están todas las palabras, en cualquier orden y no contiguas.
function coincide(txt, ts){
  if(!ts.length) return true;
  const n = norm(txt);
  return ts.every(t=>n.indexOf(t)>=0);
}
function resaltar(txt, ts){
  const s = String(txt==null?'':txt);
  if(!ts.length) return esc(s);
  const n = norm(s), marcas = [];
  ts.forEach(t=>{
    let i = n.indexOf(t);
    while(i>=0){ marcas.push([i, i+t.length]); i = n.indexOf(t, i+t.length); }
  });
  if(!marcas.length) return esc(s);
  marcas.sort((a,b)=>a[0]-b[0]);
  const unidos = [marcas[0]];
  for(const m of marcas.slice(1)){
    const u = unidos[unidos.length-1];
    if(m[0] <= u[1]) u[1] = Math.max(u[1], m[1]); else unidos.push(m);
  }
  let out='', pos=0;
  for(const [a,b] of unidos){
    out += esc(s.slice(pos,a)) + '<mark>' + esc(s.slice(a,b)) + '</mark>';
    pos = b;
  }
  return out + esc(s.slice(pos));
}

const MES = ['ene.','feb.','mar.','abr.','may.','jun.','jul.','ago.','sep.',
             'oct.','nov.','dic.'];
// «31 ago. 2026» se lee de un vistazo; «2026-08-31» hay que decodificarlo.
function fechaLeg(f){
  if(!f) return '';
  const p = String(f).slice(0,10).split('-');
  if(p.length!==3) return String(f);
  return (+p[2]) + ' ' + (MES[+p[1]-1]||p[1]) + ' ' + p[0];
}
function badges(r){
  const b=[];
  if(r.nivel_conicet===1) b.push(['Nivel 1','#fef3c7','#a16207','']);
  else if(r.nivel_conicet===2) b.push(['Nivel 2','','','']);
  if(r.en_scopus){
    const activa = String(r.scopus_estado||'').toLowerCase()==='active';
    b.push([activa ? 'Scopus' : 'Scopus ('+r.scopus_estado+')',
            '#e0e7ff','#4338ca','']);
  }
  // SCImago con el cuartil del ranking, que es el dato que importa: ya no se
  // deriva de Scopus, viene del CSV oficial del ranking.
  if(r.en_scimago){
    const q = r.cuartil_sjr;
    const col = {Q1:['#ede9fe','#5b21b6'], Q2:['#f3e8ff','#7e22ce'],
                 Q3:['#faf5ff','#9333ea'], Q4:['#fdf4ff','#a855f7']}[q]
                || ['#f5f3ff','#7c3aed'];
    b.push(['SciMago'+(q?' '+q:''), col[0], col[1],
            r.sjr ? 'SJR '+Number(r.sjr).toFixed(3)+' · ranking SCImago 2025'
                  : 'Ranking SCImago 2025']);
  }
  if(r.en_scielo) b.push(['SciELO','#dcfce7','#15803d','']);
  if(r.en_doaj) b.push(['DOAJ','#fce7f3','#a21caf','']);
  // WoS va aparte y con asterisco: la lista pública de Clarivate solo se
  // consulta por una API interna que rechaza las peticiones externas, así que
  // esto es lo que declara la fuente del listado, sin verificar.
  if(r.wos_declarado) b.push(['WoS*','#fee2e2','#b91c1c',
    'Declarado por la fuente del listado, sin verificar contra Clarivate']);
  return b;
}
function chip(b){
  const st = b[1] ? ' style="background:'+b[1]+';color:'+b[2]+'"' : '';
  const ti = b[3] ? ' title="'+esc(b[3])+'"' : '';
  return '<span class="chip"'+st+ti+'>'+esc(b[0])+'</span>';
}

// Google Calendar acepta los datos del evento por URL: no hace falta nada del
// lado del servidor. Solo tiene sentido si la convocatoria declara su plazo.
function urlCalendario(c){
  if(!c.fecha_cierre) return null;
  const p = String(c.fecha_cierre).slice(0,10).split('-');
  if(p.length!==3) return null;
  const ini = p[0]+p[1]+p[2];
  // Evento de día completo: en Google el fin es exclusivo, va el día siguiente.
  const f = new Date(+p[0], +p[1]-1, +p[2]+1);
  const dd = n => String(n).padStart(2,'0');
  const fin = f.getFullYear()+dd(f.getMonth()+1)+dd(f.getDate());

  const partes = [c.titulo];
  if(c.tema) partes.push('Tema: '+c.tema);
  if(c.url) partes.push(c.url);
  partes.push('', 'Verificá el plazo en el sitio de la revista antes de enviar.',
              'Agregado desde el Panel de revistas académicas iberoamericanas.');

  return 'https://calendar.google.com/calendar/render?action=TEMPLATE'
    + '&text=' + encodeURIComponent('Cierra convocatoria · '+c.revista)
    + '&dates=' + ini + '/' + fin
    + '&details=' + encodeURIComponent(partes.join('\\n'))
    + (c.url ? '&location=' + encodeURIComponent(c.url) : '');
}

function botonCalendario(c){
  const u = urlCalendario(c);
  if(!u) return '';
  return '<a class="cal" href="'+u+'" target="_blank" rel="noopener" '
    +'title="Agendar el cierre en Google Calendar">'
    +'<svg viewBox="0 0 24 24" width="15" height="15" fill="none" '
    +'stroke="currentColor" stroke-width="2" stroke-linecap="round" '
    +'stroke-linejoin="round" aria-hidden="true">'
    +'<rect x="3" y="4" width="18" height="18" rx="2"></rect>'
    +'<path d="M16 2v4M8 2v4M3 10h18"></path></svg>Agendar</a>';
}

// Estado de la última lectura de la fuente, por tarjeta. Repetir la
// advertencia general no le dice a nadie si ESTE dato está fresco.
function lineaVerif(c){
  const LEIDA = ['ok','sin convocatorias','sin pagina de anuncios'];
  if(String(c.fuente||'').indexOf('manual')===0)
    return '<div class="verif">✎ Incorporada a mano tras verificarla</div>';
  if(c.estado_chequeo && LEIDA.indexOf(c.estado_chequeo)<0)
    return '<div class="verif mal">⚠ La fuente no respondió en la última '
      +'revisión · última lectura correcta: '
      +(c.ultima_revision_ok?fechaLeg(c.ultima_revision_ok):'sin registro')+'</div>';
  if(!c.ultima_revision_ok) return '';
  const d = dias(c.ultima_revision_ok);
  const cuando = d===0 ? 'hoy' : (d===-1 ? 'ayer' : 'el '+fechaLeg(c.ultima_revision_ok));
  return '<div class="verif">✓ Fuente verificada '+esc(cuando)+'</div>';
}

function botonGuardar(c){
  const g = estaGuardada(c);
  return '<button class="guardar" data-id="'+esc(idConv(c))+'" '
    +'aria-pressed="'+(g?'true':'false')+'">'+(g?'★ Guardada':'☆ Guardar')
    +'</button>';
}

// Reportar un error: se abre un correo con los datos ya cargados, así el aviso
// llega identificando exactamente qué convocatoria está mal.
function botonReportar(c){
  return '<a class="reportar" href="#" data-rep="'+esc(idConv(c))+'">'
    +'Reportar un error</a>';
}

function tarjetaConv(c, ts){
  ts = ts || [];
  const d=dias(c.fecha_cierre), col=GUTTER[nivelUrg(d)], p=plazoPartes(d);
  let h='<article class="tarj"><div class="gutter" style="background:'+col.bg
    +';color:'+col.fg+'"><span class="gnum">'+esc(p[0])
    +'</span><span class="gtxt">'+esc(p[1])+'</span></div><div class="cuerpo">';
  h+='<div class="rev">'+resaltar(c.revista, ts)+'</div>';
  h+='<div class="tit">'+resaltar(c.titulo, ts)+'</div>';
  if(c.tema) h+='<div class="tema"><b>Tema:</b> '+resaltar(c.tema, ts)+'</div>';
  // «Dossier» va como palabra: el emoji solo no puede cargar con el dato.
  const marcas=[];
  if(c.es_dossier) marcas.push('<span class="chip dos">📑 Dossier</span>');
  if(c.nueva) marcas.push('<span class="chip nueva">Nueva</span>');
  h+='<div class="meta">'
    +(c.fecha_cierre?'<span class="fecha">Cierra el '+esc(fechaLeg(c.fecha_cierre))
      +'</span>':'<span class="fecha">Sin fecha de cierre declarada</span>')
    +marcas.join('')+badges(c).map(chip).join('')
    +'<span class="pais">'+esc(c.pais)+'</span></div>';
  const acciones=[];
  if(c.url) acciones.push('<a href="'+esc(c.url)
    +'" target="_blank" rel="noopener">Abrir convocatoria →</a>');
  acciones.push(botonGuardar(c));
  const cal = botonCalendario(c);
  if(cal) acciones.push(cal);
  acciones.push(botonReportar(c));
  h+='<div class="acciones">'+acciones.join('')+'</div>';
  h+=lineaVerif(c);
  return h+'</div></article>';
}

function tarjetaPerm(r){
  let frase=(r.evidencia_permanente||'').split('[fuente:')[0].trim();
  let fuente=(r.evidencia_permanente||'').split('[fuente:')[1];
  fuente = fuente ? fuente.replace(']','').trim() : '';
  let h='<article class="tarj"><div class="gutter" '
    +'style="background:#dcfce7;color:#15803d">'
    +'<span class="gnum">∞</span><span class="gtxt">abierta</span></div>'
    +'<div class="cuerpo"><div class="rev">'+esc(r.nombre)+'</div>'
    +'<div class="meta">'+badges(r).map(chip).join('')
    +'<span class="pais">'+esc(r.pais)+'</span></div>';
  if(frase) h+='<div class="cita">…'+esc(frase)+'…</div>';
  const ls=[];
  if(r.sitio_url) ls.push('<a href="'+esc(r.sitio_url)
    +'" target="_blank" rel="noopener">Ir a la revista →</a>');
  if(fuente && /^https?:/.test(fuente)) ls.push('<a href="'+esc(fuente)
    +'" target="_blank" rel="noopener">Ver la fuente →</a>');
  if(ls.length) h+='<div style="display:flex;gap:16px;margin-top:9px;'
    +'flex-wrap:wrap">'+ls.join('')+'</div>';
  return h+'</div></article>';
}

function tarjetaCerrada(c){
  const d = dias(c.fecha_cierre);
  const hace = d===null ? '' : (d===-1 ? 'ayer' : 'hace '+Math.abs(d)+' días');
  let h='<article class="tarj"><div class="gutter" '
    +'style="background:var(--chip);color:var(--fg3)">'
    +'<span class="gnum">✕</span><span class="gtxt">cerrada</span></div>'
    +'<div class="cuerpo"><div class="rev">'+esc(c.revista)+'</div>'
    +'<div class="tit">'+(c.es_dossier?'📑 ':'')+esc(c.titulo)+'</div>';
  if(c.tema) h+='<div class="tema"><b>Dossier:</b> '+esc(c.tema)+'</div>';

  // Lo útil de una convocatoria cerrada: si vuelve, y si la revista recibe igual.
  const notas=[];
  if(c.fecha_reapertura)
    notas.push('<b>Reabre el '+esc(fechaLeg(c.fecha_reapertura))+'</b>');
  if(c.revista_permanente)
    notas.push('La revista <b>recibe artículos todo el año</b>');
  else if(c.sigue_recibiendo)
    notas.push('El aviso indica que <b>se siguen recibiendo trabajos</b>');
  if(notas.length)
    h+='<div class="reabre">'+notas.join('<br>')+'</div>';
  else
    h+='<div class="meta"><span class="fecha">No declara reapertura ni '
      +'recepción abierta</span></div>';

  h+='<div class="meta"><span class="fecha">Cerró el '+esc(fechaLeg(c.fecha_cierre))
    +(hace?' · '+hace:'')+'</span>'+badges(c).map(chip).join('')
    +'<span class="pais">'+esc(c.pais)+'</span></div>';
  const acc=[];
  if(c.url) acc.push('<a href="'+esc(c.url)
    +'" target="_blank" rel="noopener">Ver la convocatoria →</a>');
  acc.push(botonGuardar(c));
  h+='<div class="acciones">'+acc.join('')+'</div>';
  return h+'</div></article>';
}

function tarjetaRev(r, manual, ts){
  ts = ts || [];
  const issn=[r.issn_impreso,r.issn_online].filter(Boolean).join(' / ')||'—';
  let h='<div class="rcard"><div class="top"><div class="nombre">'
    +resaltar(r.nombre, ts)+'</div><div class="pais">'+esc(r.pais)+'</div></div>';
  if(manual) h+='<div class="motivo">'+esc(r.estado_chequeo||'—')+'</div>';
  else h+='<div style="display:flex;flex-wrap:wrap;gap:6px">'
    +badges(r).map(chip).join('')+'</div>';
  h+='<div class="inst">'+resaltar(r.institucion||'—', ts)+'</div>';
  if(!manual) h+='<div class="issn">ISSN '+resaltar(issn, ts)+'</div>';
  if(r.sitio_url) h+='<a href="'+esc(r.sitio_url)
    +'" target="_blank" rel="noopener">Ir al sitio →</a>';
  if(r.ultima_revision_ok)
    h+='<div class="verif">✓ Leída el '+esc(fechaLeg(r.ultima_revision_ok))+'</div>';
  return h+'</div>';
}

function colorCobertura(l){
  l=(l||'').toLowerCase();
  if(l==='ok') return '#15803d';
  if(l.includes('protegido')) return '#c2410c';
  if(l.includes('no revisada')) return '#a16207';
  if(l.includes('sin convocatorias')) return '#64748b';
  if(l.includes('sin pagina')) return '#94a3b8';
  if(l.includes('redirec')) return '#2563eb';
  return '#b91c1c';
}

// ── facetas ────────────────────────────────────────────────────────
// Cada faceta es independiente: dentro de una, las opciones suman (O); entre
// facetas, se cruzan (Y). Eso permite «Argentina o Chile + Q1 o Q2 + dossier»,
// que con un único <select> de una opción por vez era imposible.
const ESTADOS = [
  ['seguidas','Con seguimiento de convocatorias'],
  ['conconv','Con convocatoria detectada'],
  ['sinconv','Revisadas, hoy sin convocatoria'],
  ['sinpagina','Sin sección de avisos'],
  ['sinrevisar','Pendientes de la próxima corrida'],
  ['manual','No se pudieron leer'],
  ['referencia','Sin dirección conocida'],
  ['perm','Recepción permanente']];

function opcionesPais(){
  const fuente = seccion==='conv' ? D.convocatorias
    : seccion==='cerr' ? (D.cerradas||[])
    : seccion==='guard' ? convGuardadas() : D.revistas;
  return [...new Set(fuente.map(x=>x.pais).filter(Boolean))].sort()
    .map(p=>[p,p]);
}
function opcionesDisc(){
  const fuente = seccion==='rev'||seccion==='perm' ? D.revistas
    : seccion==='guard' ? convGuardadas()
    : seccion==='cerr' ? (D.cerradas||[]) : D.convocatorias;
  const s=new Set();
  fuente.forEach(x=>(x.disc||[]).forEach(d=>s.add(d)));
  return [...s].sort().map(d=>[d,d]);
}

function facetasDe(){
  const f=[];
  f.push({id:'pais', rot:'País', opts:opcionesPais()});
  if(seccion==='conv'||seccion==='guard'){
    const t=[['dossier','Dossier'],['general','Convocatoria general'],
             ['confecha','Con fecha de cierre declarada']];
    // «Nueva» compara contra la línea de base, que se fijó al estrenar esta
    // función. Mientras no haya ninguna posterior, la opción no se ofrece:
    // un filtro que siempre devuelve cero no informa, confunde.
    if((D.estadisticas||{}).nuevas>0)
      t.splice(2,0,['nueva','Nueva desde la última actualización']);
    f.push({id:'tipo', rot:'Tipo', opts:t});
  }
  if(seccion==='cerr')
    f.push({id:'tipo', rot:'Tipo', opts:[['dossier','Dossier'],
      ['sigue','La revista sigue recibiendo'],['reabre','Con fecha de reapertura']]});
  if(seccion==='conv'||seccion==='guard')
    f.push({id:'plazo', rot:'Plazo', unica:true, opts:[['7','Cierran en 7 días'],
      ['30','Cierran en 30 días'],['90','Cierran en 90 días'],
      ['sin','Sin fecha declarada']]});
  const od=opcionesDisc();
  if(od.length) f.push({id:'disc', rot:'Tema', opts:od,
    pie:'Deducido de las palabras del título, no es una clasificación oficial.'});
  f.push({id:'indiz', rot:'Indización', opts:[['scopus','Scopus'],
    ['scielo','SciELO'],['doaj','DOAJ'],['scimago','SCImago'],['wos','WoS (declarado)']]});
  f.push({id:'cuartil', rot:'SCImago', opts:[['Q1','Q1'],['Q2','Q2'],['Q3','Q3'],
    ['Q4','Q4'],['sin','En SCImago, sin cuartil']]});
  f.push({id:'nivel', rot:'Nivel CONICET', opts:[['1','Nivel 1'],['2','Nivel 2']]});
  if(seccion==='rev')
    f.push({id:'estado', rot:'Seguimiento', unica:true, opts:ESTADOS});
  return f;
}

function pintarFacetas(){
  const cont=document.getElementById('facetas');
  // Se repinta en cada búsqueda para actualizar los contadores, así que hay
  // que devolver la faceta abierta a su estado: si no, tildar una opción
  // cerraría el menú y habría que reabrirlo para tildar la siguiente.
  const abierta = (cont.querySelector('.fac[open]')||{}).dataset;
  const idAbierta = abierta ? abierta.fac : null;
  const desplazada = idAbierta
    ? cont.querySelector('.fac[open] .menu').scrollTop : 0;
  cont.innerHTML = facetasDe().map(f=>{
    const sel = f.unica ? (F[f.id]?[F[f.id]]:[]) : F[f.id];
    const n = sel.length;
    return '<details class="fac" data-fac="'+f.id+'">'
      +'<summary>'+esc(f.rot)
      +(n?'<span class="cuenta">'+n+'</span>':'')+'</summary>'
      +'<div class="menu" role="group" aria-label="'+esc(f.rot)+'">'
      + f.opts.map(o=>'<label><input type="'+(f.unica?'radio':'checkbox')+'" '
          +(f.unica?'name="'+f.id+'" ':'')
          +'value="'+esc(o[0])+'"'+(sel.indexOf(o[0])>=0?' checked':'')
          +'>'+esc(o[1])+'</label>').join('')
      + (f.pie?'<div class="sep"></div><div style="padding:6px 10px;'
          +'font-size:11.5px;color:var(--fg4);line-height:1.45">'
          +esc(f.pie)+'</div>':'')
      +'</div></details>';
  }).join('');

  if(idAbierta){
    const d=cont.querySelector('.fac[data-fac="'+idAbierta+'"]');
    if(d){ d.open=true; d.querySelector('.menu').scrollTop=desplazada; }
  }

  cont.querySelectorAll('input').forEach(inp=>{
    inp.onchange=()=>{
      const id=inp.closest('.fac').dataset.fac;
      if(inp.type==='radio'){
        F[id] = (F[id]===inp.value) ? '' : inp.value;
        ultimoFiltro = F[id] ? [id,''] : null;
      } else {
        const a=F[id], i=a.indexOf(inp.value);
        if(inp.checked && i<0){ a.push(inp.value); ultimoFiltro=[id,inp.value]; }
        if(!inp.checked && i>=0) a.splice(i,1);
      }
      limite=PAGINA; pinta();
    };
  });
  // Una sola faceta abierta por vez.
  cont.querySelectorAll('.fac').forEach(d=>{
    d.addEventListener('toggle',()=>{
      if(d.open) cont.querySelectorAll('.fac').forEach(o=>{if(o!==d) o.open=false;});
    });
  });
}

const ROTULO={pais:'País',tipo:'Tipo',plazo:'Plazo',disc:'Tema',
  indiz:'Indización',cuartil:'SCImago',nivel:'Nivel',estado:'Seguimiento'};
const TEXTO={dossier:'Dossier',general:'Convocatoria general',nueva:'Nuevas',
  confecha:'Con fecha',sigue:'Sigue recibiendo',reabre:'Con reapertura',
  '7':'Cierran en 7 días','30':'Cierran en 30 días','90':'Cierran en 90 días',
  sin:'Sin cuartil',scopus:'Scopus',scielo:'SciELO',doaj:'DOAJ',
  scimago:'SCImago',wos:'WoS','1':'Nivel 1','2':'Nivel 2'};
function textoOpc(id,v){
  if(id==='plazo' && v==='sin') return 'Sin fecha declarada';
  if(id==='estado'){const e=ESTADOS.find(x=>x[0]===v); return e?e[1]:v;}
  return TEXTO[v]||v;
}

let ultimoFiltro=null;

function pintarActivos(){
  const cont=document.getElementById('activos');
  const chips=[];
  if(F.q) chips.push(['q','', 'Búsqueda: “'+F.q+'”']);
  LISTA.forEach(id=>F[id].forEach(v=>
    chips.push([id, v, ROTULO[id]+': '+textoOpc(id,v)])));
  ['plazo','estado'].forEach(id=>{ if(F[id])
    chips.push([id,'', ROTULO[id]+': '+textoOpc(id,F[id])]); });
  cont.innerHTML = chips.length
    ? chips.map(c=>'<span class="fchip">'+esc(c[2])
        +'<button data-qf="'+esc(c[0])+'" data-qv="'+esc(c[1])
        +'" aria-label="Quitar filtro '+esc(c[2])+'">×</button></span>').join('')
      +'<button class="limpiar" id="limpiar">Limpiar todos los filtros</button>'
    : '';
  cont.querySelectorAll('[data-qf]').forEach(b=>b.onclick=()=>{
    quitar(b.dataset.qf, b.dataset.qv); });
  const l=document.getElementById('limpiar');
  if(l) l.onclick=limpiarTodo;
}

function quitar(id, v){
  if(id==='q'){ F.q=''; document.getElementById('q').value=''; }
  else if(LISTA.indexOf(id)>=0){ const i=F[id].indexOf(v); if(i>=0) F[id].splice(i,1); }
  else F[id]='';
  limite=PAGINA; pinta();
}
function limpiarTodo(){
  F.q=''; document.getElementById('q').value='';
  LISTA.forEach(id=>F[id].length=0);
  F.plazo=''; F.estado=''; F.orden='';
  ultimoFiltro=null; limite=PAGINA; pinta();
}

// ── estado en la URL ───────────────────────────────────────────────
function escribirURL(){
  const p=new URLSearchParams();
  if(seccion!=='conv') p.set('seccion', seccion);
  if(F.q) p.set('q', F.q);
  LISTA.forEach(id=>{ if(F[id].length) p.set(id, F[id].join(',')); });
  if(F.plazo) p.set('plazo', F.plazo);
  if(F.estado) p.set('estado', F.estado);
  if(F.orden) p.set('orden', F.orden);
  const s=p.toString();
  history.replaceState(null,'', s ? '?'+s : location.pathname);
}
function leerURL(){
  const p=new URLSearchParams(location.search);
  if(p.get('seccion')) seccion=p.get('seccion');
  F.q=p.get('q')||'';
  LISTA.forEach(id=>{
    F[id].length=0;
    (p.get(id)||'').split(',').filter(Boolean).forEach(v=>F[id].push(v));
  });
  F.plazo=p.get('plazo')||''; F.estado=p.get('estado')||'';
  F.orden=p.get('orden')||'';
  const q=document.getElementById('q'); if(q) q.value=F.q;
}

// ── filtrado ───────────────────────────────────────────────────────
function pasaIndiz(x){
  if(!F.indiz.length) return true;
  return F.indiz.some(v=> v==='scopus'?x.en_scopus : v==='scielo'?x.en_scielo
    : v==='doaj'?x.en_doaj : v==='scimago'?x.en_scimago
    : v==='wos'?x.wos_declarado : false);
}
function pasaCuartil(x){
  if(!F.cuartil.length) return true;
  return F.cuartil.some(v=> v==='sin' ? (x.en_scimago && !x.cuartil_sjr)
                                      : x.cuartil_sjr===v);
}
function pasaNivel(x){
  return !F.nivel.length || F.nivel.some(v=>String(x.nivel_conicet)===v);
}
function pasaDisc(x){
  return !F.disc.length || (x.disc||[]).some(d=>F.disc.indexOf(d)>=0);
}
function pasaPais(x){ return !F.pais.length || F.pais.indexOf(x.pais)>=0; }
function pasaPlazo(c){
  if(!F.plazo) return true;
  const d=dias(c.fecha_cierre);
  if(F.plazo==='sin') return d===null;
  return d!==null && d>=0 && d<=(+F.plazo);
}
function pasaTipoConv(c){
  if(!F.tipo.length) return true;
  return F.tipo.some(v=> v==='dossier'?c.es_dossier : v==='general'?!c.es_dossier
    : v==='nueva'?c.nueva : v==='confecha'?!!c.fecha_cierre : false);
}
function pasaTipoCerr(c){
  if(!F.tipo.length) return true;
  return F.tipo.some(v=> v==='dossier'?c.es_dossier
    : v==='sigue'?(c.revista_permanente||c.sigue_recibiendo)
    : v==='reabre'?!!c.fecha_reapertura : false);
}
function pasaEstadoRev(r){
  const v=F.estado; if(!v) return true;
  if(v==='seguidas') return !!r.sitio_url;
  if(v==='referencia') return !r.sitio_url;
  if(v==='conconv') return r.sitio_url && r.estado_chequeo==='ok';
  if(v==='sinconv') return r.sitio_url && r.estado_chequeo==='sin convocatorias';
  if(v==='sinpagina') return r.sitio_url && r.estado_chequeo==='sin pagina de anuncios';
  if(v==='sinrevisar') return r.sitio_url && !r.estado_chequeo;
  if(v==='manual') return r.revision_manual===1;
  if(v==='perm') return r.recepcion_permanente===1;
  return true;
}

function ordenar(l, campoTexto){
  const o=F.orden;
  if(o==='revista') return l.slice().sort((a,b)=>
    String(a[campoTexto]||'').localeCompare(String(b[campoTexto]||''),'es'));
  if(o==='nuevas') return l.slice().sort((a,b)=>
    String(b.fecha_encontrada||'').localeCompare(String(a.fecha_encontrada||'')));
  if(o==='sjr') return l.slice().sort((a,b)=>(b.sjr||0)-(a.sjr||0));
  return l;
}

function vacio(msg){
  const sug=[];
  if(ultimoFiltro) sug.push('<button id="quitarUlt">Quitar el último filtro</button>');
  sug.push('<button id="limpiarVacio">Limpiar todos los filtros</button>');
  return '<div class="vacio"><h3>No encontramos nada con esos criterios</h3>'
    +'<p>'+esc(msg)+'</p><div class="acc">'+sug.join('')+'</div></div>';
}

// La franja del boletín es una sola, fija bajo el aviso principal. Antes se
// intercalaba tras la octava tarjeta; teniéndola arriba, repetirla dentro de
// los resultados sería mostrar dos veces lo mismo.

function pinta(){
  const ts=palabras(F.q);
  const cont=document.getElementById('lista');
  const aviso=document.getElementById('urgente');
  const conteo=document.getElementById('conteo');
  const expo=document.getElementById('expo');
  // Sin nada guardado, los botones de exportar no tendrían qué exportar: el
  // estado vacío ya explica cómo empezar.
  expo.classList.toggle('oculto', seccion!=='guard' || !guardadas.length);
  document.getElementById('cobertura').classList.toggle('oculto', seccion!=='rev');
  escribirURL();
  pintarActivos();

  if(seccion==='conv' || seccion==='guard'){
    const base = seccion==='guard' ? convGuardadas() : D.convocatorias;
    let l=base.filter(c=> pasaPais(c) && pasaTipoConv(c) && pasaPlazo(c)
      && pasaDisc(c) && pasaIndiz(c) && pasaCuartil(c) && pasaNivel(c)
      && coincide(c.revista+' '+c.titulo+' '+(c.tema||'')+' '+(c.descripcion||''), ts));
    conteo.innerHTML='<b>'+l.length+'</b> convocatoria'+(l.length===1?'':'s')
      + (seccion==='guard'?' guardada'+(l.length===1?'':'s'):'')
      + (l.length>limite?' · mostrando '+limite:'');

    const urg=l.filter(c=>{const d=dias(c.fecha_cierre);
      return d!==null&&d>=0&&d<=7;}).length;
    aviso.className='urgente'+(urg?'':' oculto');
    aviso.innerHTML = urg ? '⏰ <b>'+urg+'</b> convocatoria'+(urg===1?'':'s')
      +' cierra'+(urg===1?'':'n')+' en 7 días o menos' : '';

    if(!l.length){
      cont.innerHTML = seccion==='guard' && !guardadas.length
        ? '<div class="vacio"><h3>Todavía no guardaste ninguna</h3><p>Tocá '
          +'<b>☆ Guardar</b> en cualquier convocatoria y va a quedar acá, en '
          +'este navegador. No hace falta crear una cuenta.</p></div>'
        : vacio('Probá quitar el cuartil, ampliar el plazo o usar una palabra '
          +'más general.');
    } else if(F.orden){
      cont.innerHTML = ordenar(l,'revista').slice(0,limite)
        .map(c=>tarjetaConv(c,ts)).join('') + botonMas(l.length);
    } else {
      // Sin orden explícito se agrupa por urgencia, que es la lectura por
      // defecto: lo que cierra primero, primero.
      let html='', puestas=0;
      GRUPOS.forEach(g=>{
        const sub=l.filter(c=>nivelUrg(dias(c.fecha_cierre))===g.u);
        if(!sub.length || puestas>=limite) return;
        html+='<div class="grupo"><h2>'+esc(g.t)+'</h2><span class="n">'
          +sub.length+'</span></div>';
        for(const c of sub){
          if(puestas>=limite) break;
          html+=tarjetaConv(c,ts); puestas++;
        }
      });
      cont.innerHTML = html + botonMas(l.length);
    }

  } else if(seccion==='cerr'){
    let l=(D.cerradas||[]).filter(c=> pasaPais(c) && pasaTipoCerr(c)
      && pasaDisc(c) && pasaIndiz(c) && pasaCuartil(c) && pasaNivel(c)
      && coincide(c.revista+' '+c.titulo+' '+(c.tema||''), ts));
    conteo.innerHTML='<b>'+l.length+'</b> convocatoria'+(l.length===1?'':'s')
      +' cerrada'+(l.length===1?'':'s')+' en los últimos meses'
      +(l.length>limite?' · mostrando '+limite:'');
    const sigue=l.filter(c=>c.revista_permanente||c.sigue_recibiendo).length;
    aviso.className='urgente man'+(sigue?'':' oculto');
    aviso.innerHTML = sigue
      ? '♾️ De estas, <b>'+sigue+'</b> son de revistas que <b>siguen recibiendo '
        +'artículos</b> pese al cierre del dossier.' : '';
    cont.innerHTML = l.length
      ? ordenar(l,'revista').slice(0,limite).map(tarjetaCerrada).join('')
        + botonMas(l.length)
      : vacio('Probá quitar algún filtro o buscar otra palabra.');

  } else if(seccion==='perm'){
    let l=D.revistas.filter(r=>r.recepcion_permanente===1)
      .filter(r=> pasaPais(r) && pasaDisc(r) && pasaIndiz(r) && pasaCuartil(r)
        && pasaNivel(r)
        && coincide(r.nombre+' '+(r.institucion||''), ts));
    conteo.innerHTML='<b>'+l.length+'</b> revista'+(l.length===1?'':'s')
      +' con recepción permanente'+(l.length>limite?' · mostrando '+limite:'');
    aviso.className='urgente oculto';
    cont.innerHTML = l.length
      ? ordenar(l,'nombre').slice(0,limite).map(tarjetaPerm).join('')
        + botonMas(l.length)
      : vacio('Probá quitar algún filtro o buscar otra palabra.');

  } else {
    const manual = F.estado==='manual';
    let l=D.revistas.filter(r=> pasaPais(r) && pasaDisc(r) && pasaIndiz(r)
      && pasaCuartil(r) && pasaNivel(r) && pasaEstadoRev(r)
      && coincide(r.nombre+' '+(r.institucion||'')+' '+(r.issn_impreso||'')+' '
        +(r.issn_online||'')+' '+r.pais, ts));
    conteo.innerHTML='<b>'+l.length+'</b> revista'+(l.length===1?'':'s')
      +(l.length>limite?' · mostrando '+limite:'');
    aviso.className='urgente man'+(manual?'':' oculto');
    aviso.innerHTML = manual
      ? '🔍 Estas revistas <b>no se pudieron leer</b>: su servidor no responde, '
        +'cambió de dirección o exige registrarse. Si tienen convocatoria '
        +'abierta, no aparece en este panel — conviene mirarlas a mano.' : '';
    cont.innerHTML = l.length
      ? '<div class="revgrid">'
        + ordenar(l,'nombre').slice(0,limite).map(r=>tarjetaRev(r,manual,ts)).join('')
        + '</div>' + botonMas(l.length)
      : vacio('Probá quitar el cuartil o la indización, o buscar el nombre '
        +'sin la institución.');
  }
  conectarBotones();
}

function botonMas(total){
  if(total<=limite) return '';
  const resto=total-limite;
  return '<button class="masbtn" id="mas">Mostrar '
    +Math.min(PAGINA,resto)+' más ('+resto+' restantes)</button>';
}

function conectarBotones(){
  const mas=document.getElementById('mas');
  if(mas) mas.onclick=()=>{
    // Se mantiene la posición: sumar resultados no debe mover la página.
    const y=window.scrollY; limite+=PAGINA; pinta(); window.scrollTo(0,y);
  };
  const qu=document.getElementById('quitarUlt');
  if(qu) qu.onclick=()=>{ if(ultimoFiltro) quitar(ultimoFiltro[0],ultimoFiltro[1]);
    ultimoFiltro=null; };
  const lv=document.getElementById('limpiarVacio');
  if(lv) lv.onclick=limpiarTodo;
  document.querySelectorAll('.guardar').forEach(b=>b.onclick=()=>{
    const todas=(D.convocatorias||[]).concat(D.cerradas||[]);
    const c=todas.find(x=>idConv(x)===b.dataset.id);
    if(c){ alternarGuardada(c);
      const g=estaGuardada(c);
      b.setAttribute('aria-pressed', g?'true':'false');
      b.textContent = g?'★ Guardada':'☆ Guardar';
      if(seccion==='guard') pinta();
    }
  });
  document.querySelectorAll('[data-rep]').forEach(a=>a.onclick=ev=>{
    ev.preventDefault();
    const todas=(D.convocatorias||[]).concat(D.cerradas||[]);
    const c=todas.find(x=>idConv(x)===a.dataset.rep);
    if(c) reportar(c);
  });
  pintarFacetas();
}

function reportar(c){
  const DIR=['aguirre.elias.gonzalo','gmail.com'].join('@');
  const cuerpo=['Encontré un problema en esta convocatoria del panel:','',
    'Revista: '+c.revista, 'Convocatoria: '+c.titulo,
    'Fecha de cierre publicada: '+(c.fecha_cierre||'sin fecha'),
    'Enlace: '+(c.url||'sin enlace'), '',
    'Tipo de problema (dejá el que corresponda):',
    '  - ya está vencida', '  - la fecha es incorrecta',
    '  - no es una convocatoria', '  - el enlace está roto',
    '  - está duplicada', '  - otro:', '', 'Comentario:', ''].join('\\n');
  location.href='mailto:'+DIR+'?subject='
    +encodeURIComponent('Panel de revistas · error en una convocatoria')
    +'&body='+encodeURIComponent(cuerpo);
}

// ── exportar lo guardado ───────────────────────────────────────────
function bajar(nombre, tipo, texto){
  const b=new Blob([texto],{type:tipo+';charset=utf-8'});
  const u=URL.createObjectURL(b), a=document.createElement('a');
  a.href=u; a.download=nombre; document.body.appendChild(a); a.click();
  document.body.removeChild(a); setTimeout(()=>URL.revokeObjectURL(u),1000);
}
function csvCampo(v){
  const s=String(v==null?'':v);
  return /[",\\n;]/.test(s) ? '"'+s.replace(/"/g,'""')+'"' : s;
}
function exportarCSV(){
  const l=convGuardadas();
  if(!l.length) return;
  const cab=['Revista','Convocatoria','Tema','Cierre','Dossier','País','Enlace'];
  const filas=l.map(c=>[c.revista,c.titulo,c.tema||'',c.fecha_cierre||'',
    c.es_dossier?'sí':'no',c.pais,c.url||''].map(csvCampo).join(','));
  // BOM para que Excel en Windows abra los acentos bien.
  bajar('convocatorias-guardadas.csv','text/csv',
    '\\ufeff'+[cab.join(',')].concat(filas).join('\\r\\n'));
}
// El RFC 5545 pide líneas de hasta 75 octetos: las más largas se parten y
// continúan con un espacio inicial. Sin esto, un título largo con acentos
// puede hacer que el calendario rechace el archivo entero.
function plegarICS(linea){
  const enc=new TextEncoder(), dec=new TextDecoder();
  const b=enc.encode(linea);
  if(b.length<=73) return linea;
  const partes=[]; let i=0;
  while(i<b.length){
    let n=Math.min(73, b.length-i);
    // Nunca cortar en medio de un carácter de varios bytes.
    while(n>0 && i+n<b.length && (b[i+n]&0xC0)===0x80) n--;
    partes.push(dec.decode(b.slice(i,i+n)));
    i+=n;
  }
  return partes.join('\\r\\n ');
}

function exportarICS(){
  const l=convGuardadas().filter(c=>c.fecha_cierre);
  if(!l.length){ alert('Ninguna de las guardadas declara fecha de cierre.'); return; }
  const dd=n=>String(n).padStart(2,'0');
  const sello=new Date().toISOString().replace(/[-:]/g,'').split('.')[0]+'Z';
  const ev=l.map((c,i)=>{
    const p=String(c.fecha_cierre).slice(0,10).split('-');
    const f=new Date(+p[0],+p[1]-1,+p[2]+1);
    const fin=f.getFullYear()+dd(f.getMonth()+1)+dd(f.getDate());
    const plegar=s=>String(s).replace(/[\\\\;,]/g,m=>'\\\\'+m).replace(/\\n/g,'\\\\n');
    return ['BEGIN:VEVENT','UID:panel-'+i+'-'+sello+'@revistas',
      'DTSTAMP:'+sello,'DTSTART;VALUE=DATE:'+p.join(''),
      'DTEND;VALUE=DATE:'+fin,
      'SUMMARY:'+plegar('Cierra convocatoria · '+c.revista),
      'DESCRIPTION:'+plegar(c.titulo+(c.tema?'\\nTema: '+c.tema:'')
        +(c.url?'\\n'+c.url:'')
        +'\\nVerificá el plazo en el sitio de la revista antes de enviar.'),
      c.url?'URL:'+c.url:'', 'END:VEVENT']
      .filter(Boolean).map(plegarICS).join('\\r\\n');
  });
  bajar('convocatorias-guardadas.ics','text/calendar',
    ['BEGIN:VCALENDAR','VERSION:2.0',
     'PRODID:-//Panel de revistas academicas//ES'].concat(ev)
      .concat(['END:VCALENDAR']).join('\\r\\n'));
}
function copiarLista(){
  const l=convGuardadas();
  if(!l.length) return;
  const t=l.map(c=>'· '+c.revista+' — '+c.titulo
    +(c.tema?' (tema: '+c.tema+')':'')
    +' — cierra: '+(c.fecha_cierre?fechaLeg(c.fecha_cierre):'sin fecha')
    +(c.url?'\\n  '+c.url:'')).join('\\n');
  const avisar=()=>{
    const e=document.getElementById('expoEstado');
    e.textContent='Lista copiada al portapapeles.';
    setTimeout(()=>{e.textContent='';},3000);
  };
  if(navigator.clipboard) navigator.clipboard.writeText(t).then(avisar,()=>{});
  else avisar();
}

function cambiarSeccion(b, filtro){
  document.querySelectorAll('.segs button').forEach(x=>{
    const sel = x===b;
    x.setAttribute('aria-selected', sel?'true':'false');
    x.tabIndex = sel ? 0 : -1;
  });
  seccion=b.dataset.s;
  limite=PAGINA;
  // Los filtros que no existen en la sección nueva se descartan: dejarlos
  // activos e invisibles daría resultados inexplicables.
  F.tipo.length=0; F.plazo=''; F.estado='';
  if(filtro){
    if(filtro==='urgente') F.plazo='7';
    else if(['dossier','general','nueva','confecha','sigue','reabre']
             .indexOf(filtro)>=0) F.tipo.push(filtro);
    else if(['Q1','Q2','Q3','Q4'].indexOf(filtro)>=0){
      F.cuartil.length=0; F.cuartil.push(filtro); }
    else if(filtro==='sincuartil'){ F.cuartil.length=0; F.cuartil.push('sin'); }
    else if(['scopus','scielo','doaj','scimago','wos'].indexOf(filtro)>=0){
      F.indiz.length=0; F.indiz.push(filtro); }
    else if(filtro==='n1'){ F.nivel.length=0; F.nivel.push('1'); }
    else F.estado=filtro;
    ultimoFiltro=null;
  }
  pinta();
}

// Las métricas del encabezado abren una vista nueva: se avisa en el título
// para que nadie pierda una búsqueda sin entender por qué.
function irA(sec, filtro){
  const b=document.querySelector('.segs button[data-s="'+sec+'"]');
  if(!b) return;
  F.q=''; document.getElementById('q').value='';
  LISTA.forEach(id=>F[id].length=0);
  F.orden=''; F.plazo=''; F.estado='';
  cambiarSeccion(b, filtro);
  document.getElementById('lista').scrollIntoView({behavior:'smooth',block:'start'});
}

function pintarCobertura(){
  const e=D.estadisticas||{}, est=D.estados||[];
  const total=est.reduce((a,b)=>a+b.n,0)||1;
  document.getElementById('barra').innerHTML = est.map(x=>
    '<div style="width:'+(x.n/total*100)+'%;background:'+colorCobertura(x.estado)
    +'" title="'+esc(x.estado)+': '+x.n+'"></div>').join('');
  document.getElementById('leyenda').innerHTML = est.map(x=>
    '<span><span class="dot" style="background:'+colorCobertura(x.estado)
    +'"></span>'+esc(x.estado)+' <b>'+x.n+'</b></span>').join('');
}

document.addEventListener('DOMContentLoaded',()=>{
  const pestanas=[...document.querySelectorAll('.segs button')];
  pestanas.forEach(b=>b.onclick=()=>cambiarSeccion(b));
  // Semántica de pestañas: flechas para moverse, Inicio y Fin a los extremos.
  document.querySelector('.segs').onkeydown=ev=>{
    const i=pestanas.indexOf(document.activeElement);
    if(i<0) return;
    let n=null;
    if(ev.key==='ArrowRight') n=(i+1)%pestanas.length;
    if(ev.key==='ArrowLeft') n=(i-1+pestanas.length)%pestanas.length;
    if(ev.key==='Home') n=0;
    if(ev.key==='End') n=pestanas.length-1;
    if(n===null) return;
    ev.preventDefault(); pestanas[n].focus(); cambiarSeccion(pestanas[n]);
  };
  document.querySelectorAll('.st, .stats2 button').forEach(b=>
    b.onclick=()=>irA(b.dataset.sec, b.dataset.f));
  // Las líneas del desglose filtran la tabla igual que las cajas.
  document.querySelectorAll('.dl').forEach(b=>
    b.onclick=()=>irA('rev', b.dataset.f));
  document.getElementById('q').oninput=ev=>{
    F.q=ev.target.value.trim();
    ultimoFiltro = F.q ? ['q',''] : null;
    limite=PAGINA; pinta(); };
  document.getElementById('fOrden').onchange=ev=>{
    F.orden=ev.target.value; limite=PAGINA; pinta(); };
  const vm=document.getElementById('verMetricas');
  if(vm) vm.onclick=()=>{
    const abierto=document.getElementById('metricas').classList.toggle('abierto');
    vm.setAttribute('aria-expanded', abierto?'true':'false');
  };
  document.getElementById('expCsv').onclick=exportarCSV;
  document.getElementById('expIcs').onclick=exportarICS;
  document.getElementById('expTxt').onclick=copiarLista;
  document.getElementById('expAbrir').onclick=()=>{
    const l=convGuardadas().filter(c=>c.url);
    if(!l.length) return;
    if(l.length>8 && !confirm('Se van a abrir '+l.length+' pestañas. ¿Seguimos?'))
      return;
    l.forEach(c=>window.open(c.url,'_blank','noopener'));
  };
  // Cerrar la faceta abierta al tocar fuera o con Escape.
  document.addEventListener('click',ev=>{
    if(!ev.target.closest('.fac'))
      document.querySelectorAll('.fac[open]').forEach(d=>d.open=false);
  });
  document.addEventListener('keydown',ev=>{
    if(ev.key==='Escape')
      document.querySelectorAll('.fac[open]').forEach(d=>d.open=false);
  });
  document.getElementById('tema').onclick=()=>{
    const r=document.documentElement;
    const oscuro = r.dataset.theme
      ? r.dataset.theme==='dark'
      : matchMedia('(prefers-color-scheme:dark)').matches;
    r.dataset.theme = oscuro ? 'light' : 'dark';
    try{localStorage.setItem('tema', r.dataset.theme);}catch(e){}
  };
  try{const t=localStorage.getItem('tema');
      if(t) document.documentElement.dataset.theme=t;}catch(e){}

  // El correo se arma en JS para que los recolectores de direcciones no lo
  // levanten del HTML. Para quien lee, funciona igual.
  const DIR=['aguirre.elias.gonzalo','gmail.com'].join('@');
  const a=document.getElementById('contacto');
  if(a){
    a.href='mailto:'+DIR+'?subject='+encodeURIComponent('Panel de revistas');
    a.textContent=DIR;
  }

  // Sin servicio de formularios configurado, la suscripción se resuelve
  // abriendo un correo ya escrito. Funciona sin depender de terceros.
  const f=document.getElementById('susForm');
  if(f && f.dataset.modo==='correo'){
    f.onsubmit=ev=>{
      ev.preventDefault();
      const n=document.getElementById('susNombre').value.trim();
      const c=document.getElementById('susEmail').value.trim();
      if(!n||!c) return;
      location.href='mailto:'+DIR
        +'?subject='+encodeURIComponent('Suscripcion al resumen semanal')
        +'&body='+encodeURIComponent(
          'Hola, quiero recibir el resumen semanal de convocatorias.\\n\\n'
          +'Nombre: '+n+'\\nCorreo: '+c+'\\n\\n'
          +'(No hace falta que escribas nada más: con enviar este correo alcanza.)');
      document.getElementById('susEstado').innerHTML =
        '<p class="susOk">Se abrió tu programa de correo con el mensaje ya '
        +'escrito. <b>Enviálo</b> y quedás suscriptx. Si no se abrió, escribí a '
        +DIR+'.</p>';
    };
  }

  document.querySelectorAll('[data-guard]').forEach(b=>{
    b.textContent=' Guardadas ('+guardadas.length+')'; });

  document.getElementById('conteo').textContent='Cargando datos…';
  fetch('datos.json')
    .then(r=>{ if(!r.ok) throw new Error('HTTP '+r.status); return r.json(); })
    .then(j=>{
      D=j;
      const u=D.convocatorias.filter(c=>{const d=dias(c.fecha_cierre);
        return d!==null&&d>=0&&d<=7;}).length;
      document.getElementById('stUrg').textContent=u;
      pintarCobertura();
      // La URL manda: así un enlace compartido abre la misma búsqueda.
      leerURL();
      document.getElementById('fOrden').value=F.orden;
      const b=document.querySelector('.segs button[data-s="'+seccion+'"]')
        || document.querySelector('.segs button');
      document.querySelectorAll('.segs button').forEach(x=>{
        const sel=x===b;
        x.setAttribute('aria-selected', sel?'true':'false');
        x.tabIndex = sel?0:-1;
      });
      seccion=b.dataset.s;
      pinta();
    })
    .catch(e=>{
      document.getElementById('conteo').textContent='';
      document.getElementById('lista').innerHTML =
        '<div class="aviso"><h3>No se pudieron cargar los datos</h3><p>'
        +esc(e.message)+'</p><p>Si abriste este archivo con doble clic '
        +'(<code>file://</code>), el navegador bloquea la lectura de '
        +'<code>datos.json</code>. Vela publicada, o servila con '
        +'<code>python -m http.server</code>.</p></div>';
    });
});
"""


def construir_html(revistas, convocatorias, cerradas, estados, stats):
    formulario = formulario_suscripcion()
    return f"""<!doctype html>
<html lang="es"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Panel de revistas académicas iberoamericanas</title>
<meta name="description" content="Convocatorias y llamados a dossier abiertos
 en {stats['revistas']} revistas de ciencias sociales y humanidades de
 {stats['paises']} países de Iberoamérica.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,400..800&family=Manrope:wght@400;500;600;700;800&display=swap"
      rel="stylesheet">
<style>{CSS}</style>
</head><body>

<a class="saltar" href="#lista">Saltar a los resultados</a>
<div class="bgfx"><div class="b1"></div><div class="b2"></div>
  <div class="b3"></div><div class="b4"></div></div>
<div class="wrap">

<header><div class="env">
  <div class="hcab">
    <div>
      <p class="sello"><span class="punto"></span>
        Última actualización automática: <b>{stats['generado']}</b></p>
      <h1>Panel de revistas académicas iberoamericanas</h1>
    </div>
    <button id="tema" title="Cambiar entre tema claro y oscuro"
            aria-label="Cambiar tema">◑</button>
  </div>

  <p class="sub">Convocatorias y llamados a dossier abiertos en
    <b>{stats['revistas']}</b> revistas de ciencias sociales y humanidades
    de <b>{stats['paises']}</b> países. Los plazos se calculan con la fecha
    de hoy.</p>
  <p class="firma">Desarrollado por <b>Elías Aguirre</b>. Comentarios,
    feedback y consultas a <a id="contacto" href="#">(escribir)</a>.</p>
  <div class="ojo">
    <b>¡IMPORTANTE! Chequeá e inspeccioná la información publicada.</b>
    <p>La idea es facilitar —no reemplazar— la actividad propia de
      búsqueda y revisión. Los datos se extraen automáticamente y pueden
      estar incompletos o desactualizados: verificá siempre en el sitio de
      la revista antes de preparar un envío.</p>
  </div>

  <div class="franja">
    <p>¿Querés recibir las nuevas convocatorias cada lunes?</p>
    <a href="#boletin">Suscribirme</a>
  </div>

  <button class="verMas" id="verMetricas" aria-expanded="false"
          aria-controls="metricas">Ver estadísticas y cobertura</button>
  <div class="metricas" id="metricas">
  <div class="stats">
    <button class="st urg" data-sec="conv" data-f="urgente">
      <b id="stUrg">–</b><span>cierran en 7 días</span></button>
    <button class="st" data-sec="conv" data-f="*">
      <b>{stats['convocatorias']}</b><span>convocatorias abiertas</span></button>
    <button class="st" data-sec="conv" data-f="dossier">
      <b>{stats['dossiers']}</b><span>son dossiers</span></button>
    <button class="st" data-sec="perm" data-f="*">
      <b>{stats['permanentes']}</b><span>revistas abiertas todo el año</span></button>
    <button class="st" data-sec="cerr" data-f="*">
      <b>{stats['cerradas']}</b><span>cerradas hace poco</span></button>
    <button class="st man" data-sec="rev" data-f="manual"
       title="Su servidor no responde, cambió de dirección o exige registrarse. Si tienen convocatoria abierta, no figura acá.">
      <b>{stats['revision_manual']}</b><span>revistas que requieren revisión manual</span></button>
  </div>

  <p class="rotulo">Otras bases
    <span class="acota">se superponen entre sí y con SCImago: una revista puede
      estar en varias</span></p>
  <p class="stats2">
    <button data-sec="rev" data-f="scopus"><b>{stats['scopus']}</b> en Scopus</button>
    <button data-sec="rev" data-f="scielo"><b>{stats['scielo']}</b> en SciELO</button>
    <button data-sec="rev" data-f="doaj"><b>{stats['doaj']}</b> en DOAJ</button>
    <button data-sec="rev" data-f="n1"><b>{stats['nivel1']}</b> Nivel 1 CONICET</button>
  </p>
  <p class="enlaces">
    <a href="#boletin">Recibir el resumen semanal →</a>
    <a href="{REPO}" target="_blank" rel="noopener">Código en GitHub →</a>
    <a href="#limitaciones">Qué no cubre →</a>
  </p>
  </div>
</div></header>

<nav><div class="env">
  <div class="segs" role="tablist" aria-label="Secciones del panel">
    <button role="tab" data-s="conv" aria-selected="true"
            aria-controls="lista">Abiertas</button>
    <button role="tab" data-s="perm" aria-selected="false" tabindex="-1"
            aria-controls="lista">Permanentes</button>
    <button role="tab" data-s="cerr" aria-selected="false" tabindex="-1"
            aria-controls="lista">Cerradas</button>
    <button role="tab" data-s="guard" aria-selected="false" tabindex="-1"
            aria-controls="lista" data-guard>Guardadas (0)</button>
    <button role="tab" data-s="rev" aria-selected="false" tabindex="-1"
            aria-controls="lista">Revistas</button>
  </div>
</div></nav>

<main><div class="env">

  <div class="urgente oculto" id="urgente"></div>

  <label class="vo" for="q">Buscar convocatorias, temas o revistas</label>
  <input type="search" id="q"
         placeholder="Buscar convocatorias, temas o revistas…">

  <div class="facetas" id="facetas"></div>
  <div class="activos" id="activos"></div>

  <div class="barrares">
    <p class="conteo" id="conteo" role="status" aria-live="polite">Cargando datos…</p>
    <div class="ordenar">
      <label for="fOrden">Ordenar por</label>
      <select id="fOrden">
        <option value="">Cierre más próximo</option>
        <option value="nuevas">Detectadas más recientemente</option>
        <option value="revista">Revista (A–Z)</option>
        <option value="sjr">SJR más alto</option>
      </select>
    </div>
  </div>

  <div class="expo oculto" id="expo">
    <div class="expoBotones">
      <button id="expAbrir">Abrir todas las fuentes</button>
      <button id="expCsv">Descargar CSV</button>
      <button id="expIcs">Descargar calendario (.ics)</button>
      <button id="expTxt">Copiar la lista</button>
      <span id="expoEstado" role="status" aria-live="polite"
            style="align-self:center;font-size:13px;color:var(--a2)"></span>
    </div>
    <p class="notaGuard">Lo que guardás queda en <b>este</b> navegador y sigue
      acá cuando volvés, sin crear ninguna cuenta. Como no se envía a ningún
      lado, tampoco aparece en tu teléfono ni en otra computadora, y se borra
      si limpiás los datos de navegación. Para llevarte la selección, usá
      <b>Descargar CSV</b> o <b>el calendario</b>.</p>
  </div>

  <div id="lista" role="tabpanel" tabindex="-1"></div>

  <section class="boletin" id="boletin">
    <h3>✉️ Enterate de cada convocatoria, sin buscarla</h3>
    <p>Todos los lunes te llega un correo con las convocatorias que están por
      vencer, las nuevas de la semana y el tema de cada dossier. Dejás tu
      nombre y tu correo, nada más.</p>
    {formulario}
    <div id="susEstado"></div>
    <p class="nota">Tu correo se usa únicamente para enviarte este resumen.
      Cada envío incluye un enlace para darte de baja en un clic.</p>
  </section>

  <div class="cobertura oculto" id="cobertura">
    <h3>Qué se pudo revisar y qué no</h3>
    <p style="margin:0 0 14px;color:var(--fg2);font-size:14px;max-width:76ch;">
      El rastreador entra cada semana a la página de avisos de cada revista.
      Estas seis categorías son excluyentes y suman las
      <b>{stats['revistas']}</b> del catálogo.</p>

    <div class="desglose">
      <div class="dl" data-f="conconv"><b>{stats['rev_con_conv']}</b>
        <span>tienen convocatoria abierta</span></div>
      <div class="dl" data-f="sinconv"><b>{stats['rev_sin_conv']}</b>
        <span>se leyeron y hoy no tienen ninguna &mdash; pueden publicar una
          la semana que viene</span></div>
      <div class="dl" data-f="sinpagina"><b>{stats['rev_sin_pagina']}</b>
        <span>no tienen sección de avisos: difunden sus llamados por la
          portada, redes o un PDF, y ahí el panel no llega</span></div>
      <div class="dl" data-f="manual"><b>{stats['revision_manual']}</b>
        <span>no se pudieron leer: su servidor no responde, cambió de
          dirección o exige registrarse</span></div>
      <div class="dl" data-f="sinrevisar"><b>{stats['rev_sin_revisar']}</b>
        <span>tienen dirección pero el rastreador todavía no pasó</span></div>
      <div class="dl" data-f="referencia"><b>{stats['solo_referencia']}</b>
        <span>sin dirección conocida: están con su indización, pero no se
          pueden seguir</span></div>
    </div>

    <div class="barra" id="barra"></div>
    <div class="leyenda" id="leyenda"></div>
  </div>

  <div class="aviso" id="limitaciones">
    <h3>Antes de confiar en esto para un envío</h3>
    <ol>
      <li>Solo <b>{stats['con_fecha']} de {stats['convocatorias']}</b>
        convocatorias declaran su fecha de cierre en un formato legible. Las
        demás figuran «sin fecha declarada»: el reloj no puede avisar de ellas.</li>
      <li>Las revistas que no se pudieron leer aparecen en <b>«requieren
        revisión manual»</b>, con el motivo: servidor caído, dominio que ya no
        existe, o sitio que exige registrarse. Si tienen convocatoria abierta,
        no figura acá.</li>
      <li>Puede haber falsos positivos. <b>Verificá siempre en el enlace</b>
        antes de preparar un envío.</li>
      <li>La marca <b>«Nueva»</b> compara contra el
        <b>{stats['linea_base']}</b>, que es cuando se empezó a registrar la
        fecha de detección de cada convocatoria. Todo lo anterior a esa fecha
        entró junto con el catálogo, así que no se puede saber cuándo se
        publicó realmente: por eso no figura como nuevo.</li>
      <li>El filtro <b>«Tema»</b> se deduce de las palabras del nombre de la
        revista y del título de la convocatoria. <b>No es una clasificación
        disciplinar</b>: una revista de sociología cuyo título no diga
        «sociología» no queda etiquetada, y un título puede caer en varios
        temas a la vez. Sirve para acotar una búsqueda, no para censar un
        campo.</li>
      <li>El nivel es la jerarquía de la Res. D 2249/2014 del CONICET, que
        clasifica <i>las bases de indización</i>, no las revistas una por una.
        La resolución advierte que «dentro de un mismo nivel conviven revistas
        que difieren entre sí respecto de su calidad».</li>
      <li>Para las revistas de fuera de Argentina, «sin nivel» significa que no
        se pudo verificar, <b>no</b> que no estén indizadas.</li>
      <li>De las <b>{stats['revistas']}</b> revistas del catálogo, se sigue la
        página de convocatorias de <b>{stats['con_seguimiento']}</b>. Las otras
        <b>{stats['solo_referencia']}</b> —en su mayoría incorporadas del
        ranking SCImago— están como <b>referencia</b>: podés consultar su
        cuartil y su indización, pero el panel <b>no rastrea</b> sus
        convocatorias.</li>
    </ol>
  </div>
</div></main>

<footer><div class="env">
  Instantánea generada el {stats['generado']}. Los datos provienen de
  CAICYT-CONICET, Elsevier, SciELO, DOAJ y OpenAlex, y se rigen por sus propias
  condiciones de uso. El código es MIT.<br>
  Esta página es estática: para el panel completo con actualización automática
  y boletín por correo, cloná
  <a href="{REPO}" target="_blank" rel="noopener">el repositorio</a>.
</div></footer>

</div>
<script>{JS}</script>
</body></html>"""


def construir_gracias():
    """Página a la que vuelve el visitante después de suscribirse."""
    return f"""<!doctype html>
<html lang="es"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Listo · Panel de revistas académicas</title>
<meta name="robots" content="noindex">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,400..800&family=Manrope:wght@400;500;600;700;800&display=swap"
      rel="stylesheet">
<style>{CSS}
.centro{{max-width:640px;margin:0 auto;padding:70px 22px;text-align:center}}
.tilde{{width:74px;height:74px;border-radius:50%;background:var(--grad);
  color:#fff;font-size:37px;line-height:74px;margin:0 auto 22px;
  box-shadow:var(--sombraAlta)}}
.centro h1{{font-size:clamp(25px,4vw,36px);margin-bottom:14px}}
.centro p{{color:var(--fg2);font-size:16px;margin:0 auto 16px;max-width:52ch}}
.volver{{display:inline-block;margin-top:20px;background:var(--grad);color:#fff;
  text-decoration:none;padding:13px 26px;border-radius:12px;font-weight:700;
  box-shadow:var(--sombraAlta)}}
</style>
</head><body>
<div class="bgfx"><div class="b1"></div><div class="b2"></div>
  <div class="b3"></div><div class="b4"></div></div>
<div class="wrap"><div class="centro">
  <div class="tilde">✓</div>
  <h1>Listo, ya estás suscriptx</h1>
  <p>Te va a llegar un correo de confirmación en unos minutos, y a partir del
    <b>próximo lunes</b> el resumen semanal de convocatorias.</p>
  <p style="font-size:14.5px;color:var(--fg3);">Si no lo ves, revisá la carpeta
    de spam y marcalo como correo deseado: así los siguientes te llegan a la
    bandeja de entrada.</p>
  <a class="volver" href="{SITIO}/">← Volver al panel</a>
</div></div>
</body></html>"""


def generar():
    os.makedirs(DOCS, exist_ok=True)
    revistas, convocatorias, cerradas, estados, stats = reunir_datos()
    html = construir_html(revistas, convocatorias, cerradas, estados, stats)

    ruta = os.path.join(DOCS, 'index.html')
    with open(ruta, 'w', encoding='utf-8') as f:
        f.write(html)

    with open(os.path.join(DOCS, 'gracias.html'), 'w', encoding='utf-8') as f:
        f.write(construir_gracias())

    # .nojekyll evita que GitHub Pages procese el sitio con Jekyll.
    open(os.path.join(DOCS, '.nojekyll'), 'w').close()

    ruta_json = os.path.join(DOCS, 'datos.json')
    with open(ruta_json, 'w', encoding='utf-8') as f:
        json.dump({'generado': stats['generado'], 'estadisticas': stats,
                   'estados': estados, 'revistas': revistas,
                   'convocatorias': convocatorias, 'cerradas': cerradas},
                  f, ensure_ascii=False, separators=(',', ':'))

    return ruta, stats, os.path.getsize(ruta), os.path.getsize(ruta_json)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
    ruta, stats, tam_html, tam_json = generar()
    print(f"generado: {ruta}")
    print(f"  index.html {tam_html/1024:.0f} KB · datos.json {tam_json/1024:.0f} KB")
    for k, v in stats.items():
        print(f"  {k}: {v}")
