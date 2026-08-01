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
import json
import logging
from datetime import date, datetime

from database import conectar, contar

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

    campos = '''
      <input type="text" name="nombre" id="susNombre" required
             placeholder="Nombre completo" autocomplete="name">
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


def reunir_datos():
    conn = conectar()

    revistas = [dict(f) for f in conn.execute("""
        SELECT nombre, COALESCE(pais,'Argentina') AS pais,
               COALESCE(origen,'NBRA') AS origen, institucion,
               issn_impreso, issn_online, sitio_url, ficha_url,
               nivel_conicet, en_scopus, scopus_estado, en_scielo, en_doaj,
               recepcion_permanente, evidencia_permanente, estado_chequeo
        FROM revistas ORDER BY nombre""")]

    # Una revista "requiere revisión manual" si su sitio bloqueó la lectura
    # automática o no respondió: su convocatoria, si la tiene, no está acá.
    import re as _re
    patron_manual = _re.compile(
        r'anti-bot|login|inaccesible|redirec|^http \d|^error', _re.I)
    for r in revistas:
        r['revision_manual'] = 1 if patron_manual.search(
            r['estado_chequeo'] or '') else 0

    convocatorias = [dict(f) for f in conn.execute("""
        SELECT c.titulo, c.descripcion, c.fecha_cierre, c.url,
               COALESCE(c.es_dossier,0) AS es_dossier, c.tema,
               r.nombre AS revista, COALESCE(r.pais,'Argentina') AS pais,
               r.nivel_conicet, r.en_scopus, r.scopus_estado,
               r.en_scielo, r.en_doaj
        FROM convocatorias c JOIN revistas r ON r.id = c.revista_id
        WHERE c.activa = 1
        ORDER BY c.fecha_cierre IS NULL, c.fecha_cierre""")]

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
        'revision_manual': sum(1 for r in revistas if r['revision_manual']),
        'nivel1': sum(1 for r in revistas if r['nivel_conicet'] == 1),
        'nivel2': sum(1 for r in revistas if r['nivel_conicet'] == 2),
        'scopus': sum(1 for r in revistas if r['en_scopus']),
        'scielo': sum(1 for r in revistas if r['en_scielo']),
        'doaj': sum(1 for r in revistas if r['en_doaj']),
        'generado': datetime.now().strftime('%d/%m/%Y %H:%M'),
    }
    return revistas, convocatorias, estados, stats


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
.hcab{display:flex;justify-content:space-between;align-items:flex-start;gap:16px}
h1{font-family:'Bricolage Grotesque',system-ui,sans-serif;font-weight:800;
  font-size:clamp(27px,4.4vw,48px);line-height:1.06;letter-spacing:-.02em;
  margin:0 0 12px;background:var(--grad);-webkit-background-clip:text;
  background-clip:text;color:transparent}
.sub{margin:0 0 9px;color:var(--fg2);max-width:64ch;font-size:16px}
.sub b{color:var(--fg)}
.firma{margin:0 0 22px;color:var(--fg3);font-size:13.5px}
.firma b{color:var(--fg)}
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
.st.urg b,.st.urg span{color:#dc2626}
:root[data-theme=dark] .st.urg b,:root[data-theme=dark] .st.urg span{color:#fca5a5}
.st.man{background:rgba(180,83,9,.1);border-color:rgba(180,83,9,.32)}
.st.man b,.st.man span{color:#b45309}
:root[data-theme=dark] .st.man b,:root[data-theme=dark] .st.man span{color:#fcd34d}
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
input:focus-visible,select:focus-visible{outline:2px solid var(--a1);
  outline-offset:-1px}

main{padding:24px 0 80px}
.conteo{color:var(--fg3);font-size:13.5px;margin:0 0 12px}
.urgente{background:rgba(220,38,38,.09);border:1px solid rgba(220,38,38,.35);
  border-radius:14px;padding:14px 18px;margin-bottom:18px;color:#b91c1c;
  font-weight:650;font-size:15px}
:root[data-theme=dark] .urgente{color:#fca5a5}
.urgente.man{background:rgba(180,83,9,.1);border-color:rgba(180,83,9,.32);
  color:#92400e;font-weight:400}
:root[data-theme=dark] .urgente.man{color:#fcd34d}
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
.rcard .motivo{color:#b45309;font-size:12.5px;font-weight:650}
:root[data-theme=dark] .rcard .motivo{color:#fcd34d}
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
.oculto{display:none}

@media(max-width:760px){
  .tarj{grid-template-columns:70px 1fr}
  .gnum{font-size:21px}
  header{padding:24px 0 16px}
  .env{padding:0 16px}
  nav .env{padding:10px 16px;gap:9px}
  .segs{width:100%;justify-content:space-between}
  .segs button{flex:1;padding:9px 8px;font-size:13.5px}
  /* Buscador en una fila entera y los dos selectores compartiendo la de
     abajo: en una sola fila los tres quedaban ilegibles ("Tod...", "Tod..."). */
  input[type=search]{flex:1 0 100%;min-width:0}
  select{flex:1 1 0;min-width:0}
  .boletin{padding:20px 18px}
  .susForm input,.susForm button{flex:1 0 100%}
}
"""

JS = """
// Los datos se cargan desde datos.json en vez de incrustarse en el HTML:
// al inlinear ~400 KB de JSON el parser cortaba el <script> a la mitad.
let D = {revistas:[], convocatorias:[], estadisticas:{}};
let seccion = 'conv', revLimite = 60;
const hoy = new Date(); hoy.setHours(0,0,0,0);

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
function badges(r){
  const b=[];
  if(r.nivel_conicet===1) b.push(['Nivel 1','#fef3c7','#a16207']);
  else if(r.nivel_conicet===2) b.push(['Nivel 2','','']);
  if(r.en_scopus) b.push([String(r.scopus_estado||'').toLowerCase()==='active'
      ? 'Scopus' : 'Scopus ('+r.scopus_estado+')','#e0e7ff','#4338ca']);
  if(r.en_scielo) b.push(['SciELO','#dcfce7','#15803d']);
  if(r.en_doaj) b.push(['DOAJ','#fce7f3','#a21caf']);
  return b;
}
function chip(b){
  const st = b[1] ? ' style="background:'+b[1]+';color:'+b[2]+'"' : '';
  return '<span class="chip"'+st+'>'+esc(b[0])+'</span>';
}

function tarjetaConv(c){
  const d=dias(c.fecha_cierre), col=GUTTER[nivelUrg(d)], p=plazoPartes(d);
  let h='<article class="tarj"><div class="gutter" style="background:'+col.bg
    +';color:'+col.fg+'"><span class="gnum">'+esc(p[0])
    +'</span><span class="gtxt">'+esc(p[1])+'</span></div><div class="cuerpo">';
  h+='<div class="rev">'+esc(c.revista)+'</div>';
  h+='<div class="tit">'+(c.es_dossier?'📑 ':'')+esc(c.titulo)+'</div>';
  if(c.tema) h+='<div class="tema"><b>Dossier:</b> '+esc(c.tema)+'</div>';
  h+='<div class="meta">'
    +(c.fecha_cierre?'<span class="fecha">Cierra el '+esc(c.fecha_cierre)+'</span>':'')
    +badges(c).map(chip).join('')+'<span class="pais">'+esc(c.pais)+'</span></div>';
  if(c.url) h+='<a href="'+esc(c.url)
    +'" target="_blank" rel="noopener">Abrir convocatoria →</a>';
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

function tarjetaRev(r, manual){
  const issn=[r.issn_impreso,r.issn_online].filter(Boolean).join(' / ')||'—';
  let h='<div class="rcard"><div class="top"><div class="nombre">'
    +esc(r.nombre)+'</div><div class="pais">'+esc(r.pais)+'</div></div>';
  if(manual) h+='<div class="motivo">'+esc(r.estado_chequeo||'—')+'</div>';
  else h+='<div style="display:flex;flex-wrap:wrap;gap:6px">'
    +badges(r).map(chip).join('')+'</div>';
  h+='<div class="inst">'+esc(r.institucion||'—')+'</div>';
  if(!manual) h+='<div class="issn">ISSN '+esc(issn)+'</div>';
  if(r.sitio_url) h+='<a href="'+esc(r.sitio_url)
    +'" target="_blank" rel="noopener">Ir al sitio →</a>';
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

function pinta(){
  const q=(document.getElementById('q').value||'').toLowerCase().trim();
  const pais=document.getElementById('fPais').value;
  const orden=document.getElementById('fOrden').value;
  const cont=document.getElementById('lista');
  const aviso=document.getElementById('urgente');

  if(seccion==='conv'){
    let l=D.convocatorias.filter(c=>{
      if(pais!=='*' && c.pais!==pais) return false;
      if(orden==='dossier' && !c.es_dossier) return false;
      if(orden==='fecha' && !c.fecha_cierre) return false;
      if(orden==='urgente'){const d=dias(c.fecha_cierre);
        if(d===null||d<0||d>7) return false;}
      if(!q) return true;
      return (c.revista+' '+c.titulo+' '+(c.tema||'')+' '+(c.descripcion||''))
        .toLowerCase().includes(q);
    });
    document.getElementById('conteo').textContent =
      l.length+' convocatoria'+(l.length===1?'':'s');

    const urg=l.filter(c=>{const d=dias(c.fecha_cierre);
      return d!==null&&d>=0&&d<=7;}).length;
    aviso.className='urgente'+(urg?'':' oculto');
    aviso.innerHTML = urg ? '⏰ <b>'+urg+'</b> convocatoria'+(urg===1?'':'s')
      +' cierra'+(urg===1?'':'n')+' en 7 días o menos' : '';

    let html='';
    GRUPOS.forEach(g=>{
      const sub=l.filter(c=>nivelUrg(dias(c.fecha_cierre))===g.u);
      if(!sub.length) return;
      html+='<div class="grupo"><h2>'+esc(g.t)+'</h2><span class="n">'
        +sub.length+'</span></div>'+sub.map(tarjetaConv).join('');
    });
    cont.innerHTML = html || '<p>Sin resultados para ese filtro.</p>';

  } else if(seccion==='perm'){
    let l=D.revistas.filter(r=>r.recepcion_permanente===1).filter(r=>{
      if(pais!=='*' && r.pais!==pais) return false;
      if(!q) return true;
      return (r.nombre+' '+(r.institucion||'')).toLowerCase().includes(q);
    });
    document.getElementById('conteo').textContent =
      l.length+' revista'+(l.length===1?'':'s')+' con recepción permanente';
    aviso.className='urgente oculto';
    cont.innerHTML = l.length ? l.map(tarjetaPerm).join('')
      : '<p>Sin resultados.</p>';

  } else {
    const manual = orden==='manual';
    let l=D.revistas.filter(r=>{
      if(pais!=='*' && r.pais!==pais) return false;
      if(orden==='n1' && r.nivel_conicet!==1) return false;
      if(orden==='scopus' && !r.en_scopus) return false;
      if(orden==='scielo' && !r.en_scielo) return false;
      if(orden==='doaj' && !r.en_doaj) return false;
      if(orden==='perm' && r.recepcion_permanente!==1) return false;
      if(manual && r.revision_manual!==1) return false;
      if(!q) return true;
      return (r.nombre+' '+(r.institucion||'')+' '+(r.issn_impreso||'')+' '
        +(r.issn_online||'')+' '+r.pais).toLowerCase().includes(q);
    });
    document.getElementById('conteo').textContent =
      l.length+' revista'+(l.length===1?'':'s')
      + (l.length>revLimite ? ' · mostrando '+revLimite : '');
    aviso.className='urgente man'+(manual?'':' oculto');
    aviso.innerHTML = manual
      ? '🔍 Estas revistas <b>no se pudieron leer automáticamente</b>: su sitio '
        +'bloquea la lectura o no respondió. Si tienen convocatoria abierta, no '
        +'aparece en este panel — conviene mirarlas a mano.' : '';

    cont.innerHTML='<div class="revgrid">'
      + (l.slice(0,revLimite).map(r=>tarjetaRev(r,manual)).join('')
         || '<p>Sin resultados.</p>')
      + '</div>'
      + (l.length>revLimite
         ? '<button class="masbtn" id="mas">Ver más ('
           +(l.length-revLimite)+' restantes)</button>' : '');
    const mas=document.getElementById('mas');
    if(mas) mas.onclick=()=>{revLimite+=60;pinta();};
  }
}

function cambiarSeccion(b, filtro){
  document.querySelectorAll('.segs button').forEach(x=>
    x.setAttribute('aria-selected', x===b ? 'true':'false'));
  seccion=b.dataset.s;
  revLimite=60;
  const sel=document.getElementById('fOrden');
  sel.innerHTML = seccion==='conv'
    ? '<option value="*">Todas</option>'
      +'<option value="urgente">Cierran en 7 días</option>'
      +'<option value="dossier">Solo dossiers</option>'
      +'<option value="fecha">Solo con fecha</option>'
    : seccion==='rev'
    ? '<option value="*">Todas</option><option value="n1">Solo Nivel 1</option>'
      +'<option value="scopus">En Scopus</option>'
      +'<option value="scielo">En SciELO</option>'
      +'<option value="doaj">En DOAJ</option>'
      +'<option value="perm">Recepción permanente</option>'
      +'<option value="manual">Requieren revisión manual</option>'
    : '<option value="*">Todas</option>';
  if(filtro && sel.querySelector('option[value="'+filtro+'"]')) sel.value=filtro;
  sel.classList.toggle('oculto', seccion==='perm');
  document.getElementById('cobertura').classList.toggle('oculto', seccion!=='rev');
  pinta();
}

function irA(sec, filtro){
  const b=document.querySelector('.segs button[data-s="'+sec+'"]');
  if(!b) return;
  document.getElementById('q').value='';
  document.getElementById('fPais').value='*';
  cambiarSeccion(b, filtro);
  document.querySelector('nav').scrollIntoView({behavior:'smooth',block:'start'});
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
  document.querySelectorAll('.segs button').forEach(b=>
    b.onclick=()=>cambiarSeccion(b));
  document.querySelectorAll('.st, .stats2 button').forEach(b=>
    b.onclick=()=>irA(b.dataset.sec, b.dataset.f));
  document.getElementById('q').oninput=pinta;
  document.getElementById('fPais').onchange=pinta;
  document.getElementById('fOrden').onchange=pinta;
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

  document.getElementById('conteo').textContent='Cargando datos…';
  fetch('datos.json')
    .then(r=>{ if(!r.ok) throw new Error('HTTP '+r.status); return r.json(); })
    .then(j=>{
      D=j;
      const paises=[...new Set(D.revistas.map(r=>r.pais))].sort();
      document.getElementById('fPais').innerHTML =
        '<option value="*">Todos los países</option>'
        + paises.map(p=>'<option>'+esc(p)+'</option>').join('');
      const u=D.convocatorias.filter(c=>{const d=dias(c.fecha_cierre);
        return d!==null&&d>=0&&d<=7;}).length;
      document.getElementById('stUrg').textContent=u;
      pintarCobertura();
      cambiarSeccion(document.querySelector('.segs button'));
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


def construir_html(revistas, convocatorias, estados, stats):
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

<div class="bgfx"><div class="b1"></div><div class="b2"></div>
  <div class="b3"></div><div class="b4"></div></div>
<div class="wrap">

<header><div class="env">
  <div class="hcab">
    <div>
      <h1>Panel de revistas académicas iberoamericanas</h1>
      <p class="sub">Convocatorias y llamados a dossier abiertos en
        <b>{stats['revistas']}</b> revistas de ciencias sociales y humanidades
        de <b>{stats['paises']}</b> países. Los plazos se calculan con la fecha
        de hoy.</p>
      <p class="firma">Desarrollado por <b>Elías Aguirre</b>. Comentarios,
        feedback y consultas a <a id="contacto" href="#">(escribir)</a>.</p>
    </div>
    <button id="tema" title="Cambiar entre tema claro y oscuro"
            aria-label="Cambiar tema">◑</button>
  </div>
  <div class="stats">
    <button class="st urg" data-sec="conv" data-f="urgente">
      <b id="stUrg">–</b><span>cierran en 7 días</span></button>
    <button class="st" data-sec="conv" data-f="*">
      <b>{stats['convocatorias']}</b><span>convocatorias</span></button>
    <button class="st" data-sec="conv" data-f="dossier">
      <b>{stats['dossiers']}</b><span>dossiers</span></button>
    <button class="st" data-sec="perm" data-f="*">
      <b>{stats['permanentes']}</b><span>abiertas todo el año</span></button>
    <button class="st" data-sec="rev" data-f="*">
      <b>{stats['revistas']}</b><span>revistas</span></button>
    <button class="st man" data-sec="rev" data-f="manual">
      <b>{stats['revision_manual']}</b><span>requieren revisión manual</span></button>
  </div>
  <p class="stats2">
    <button data-sec="rev" data-f="n1"><b>{stats['nivel1']}</b> Nivel 1</button>
    <button data-sec="rev" data-f="scopus"><b>{stats['scopus']}</b> en Scopus</button>
    <button data-sec="rev" data-f="scielo"><b>{stats['scielo']}</b> en SciELO</button>
    <button data-sec="rev" data-f="doaj"><b>{stats['doaj']}</b> en DOAJ</button>
  </p>
  <p class="enlaces">
    <a href="#boletin">Recibir el resumen semanal →</a>
    <a href="{REPO}" target="_blank" rel="noopener">Código en GitHub →</a>
    <a href="#limitaciones">Qué no cubre →</a>
  </p>
</div></header>

<nav><div class="env">
  <div class="segs">
    <button data-s="conv" aria-selected="true">Convocatorias</button>
    <button data-s="perm">Permanentes</button>
    <button data-s="rev">Revistas</button>
  </div>
  <input type="search" id="q"
         placeholder="Buscar por revista, tema, ISSN o institución…">
  <select id="fPais"></select>
  <select id="fOrden"></select>
</div></nav>

<main><div class="env">

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

  <p class="conteo" id="conteo">Cargando datos…</p>
  <div class="urgente oculto" id="urgente"></div>
  <div id="lista"></div>

  <div class="cobertura oculto" id="cobertura">
    <h3>Qué se pudo revisar y qué no</h3>
    <div class="barra" id="barra"></div>
    <div class="leyenda" id="leyenda"></div>
  </div>

  <div class="aviso" id="limitaciones">
    <h3>Antes de confiar en esto para un envío</h3>
    <ol>
      <li>Solo <b>{stats['con_fecha']} de {stats['convocatorias']}</b>
        convocatorias declaran su fecha de cierre en un formato legible. Las
        demás figuran «sin fecha declarada»: el reloj no puede avisar de ellas.</li>
      <li>Las revistas cuyo sitio usa protección anti-bot <b>se saltean, no se
        evaden</b>. Si tienen convocatoria abierta, no aparece acá.</li>
      <li>Puede haber falsos positivos. <b>Verificá siempre en el enlace</b>
        antes de preparar un envío.</li>
      <li>El nivel es la jerarquía de la Res. D 2249/2014 del CONICET, que
        clasifica <i>las bases de indización</i>, no las revistas una por una.
        La resolución advierte que «dentro de un mismo nivel conviven revistas
        que difieren entre sí respecto de su calidad».</li>
      <li>Para las revistas de fuera de Argentina, «sin nivel» significa que no
        se pudo verificar, <b>no</b> que no estén indizadas.</li>
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
    revistas, convocatorias, estados, stats = reunir_datos()
    html = construir_html(revistas, convocatorias, estados, stats)

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
                   'convocatorias': convocatorias},
                  f, ensure_ascii=False, separators=(',', ':'))

    return ruta, stats, os.path.getsize(ruta), os.path.getsize(ruta_json)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
    ruta, stats, tam_html, tam_json = generar()
    print(f"generado: {ruta}")
    print(f"  index.html {tam_html/1024:.0f} KB · datos.json {tam_json/1024:.0f} KB")
    for k, v in stats.items():
        print(f"  {k}: {v}")
