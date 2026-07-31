"""
Genera el sitio estático para GitHub Pages (carpeta docs/).

GitHub Pages solo sirve archivos estáticos, así que no puede ejecutar la app
Streamlit. Lo que se publica es una *instantánea* navegable de los datos: el
buscador y los filtros corren en el navegador, y la cuenta regresiva de cada
convocatoria se calcula con la fecha del visitante, así no queda desactualizada
entre una regeneración y la siguiente.

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


def formulario_suscripcion():
    """
    HTML del formulario del boletín.

    Un sitio estático no puede recibir los datos por sí mismo: hace falta un
    servicio que acepte el POST. La URL se define en config_sitio.json
    (ignorado por git) bajo la clave "formulario_endpoint"; sirve cualquiera
    que devuelva un POST por formulario: Formspree, Getform, Formsubmit,
    Basin, o un Google Form.

    Sin endpoint configurado NO se inventa uno ni se publica un correo en el
    HTML —quedaría expuesto a recolectores de spam—: se muestra el aviso de
    que la suscripción todavía no está activa.
    """
    endpoint = ''
    if os.path.exists(CONFIG_SITIO):
        try:
            with open(CONFIG_SITIO, encoding='utf-8') as f:
                endpoint = (json.load(f).get('formulario_endpoint') or '').strip()
        except (OSError, ValueError):
            endpoint = ''

    if not endpoint:
        return ('<p style="margin:0;padding:12px 15px;background:var(--bg2);'
                'border-radius:9px;font-size:14.5px;color:var(--fg2);">'
                'La suscripción todavía no está activa. Mientras tanto, el '
                f'resumen se puede generar localmente: ver <a href="{REPO}'
                '#%EF%B8%8F-resumen-semanal-por-correo">las instrucciones</a>.'
                '</p>')

    return f'''<form action="{endpoint}" method="POST">
      <input type="text" name="nombre" placeholder="Nombre completo"
             required autocomplete="name">
      <input type="email" name="email" placeholder="Correo electrónico"
             required autocomplete="email">
      <input type="hidden" name="_subject"
             value="Nueva suscripcion al panel de revistas">
      <button type="submit">Suscribirme</button>
    </form>'''


def reunir_datos():
    conn = conectar()

    revistas = [dict(f) for f in conn.execute("""
        SELECT nombre, COALESCE(pais,'Argentina') AS pais,
               COALESCE(origen,'NBRA') AS origen, institucion,
               issn_impreso, issn_online, sitio_url, ficha_url,
               nivel_conicet, en_scopus, scopus_estado, en_scielo, en_doaj,
               recepcion_permanente, evidencia_permanente
        FROM revistas ORDER BY nombre""")]

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

    n = contar()
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
  --bg:#fbfbfc; --sup:#ffffff; --bg2:#f2f4f7; --fg:#14161a; --fg2:#5c6572;
  --linea:#e2e6ec; --linea2:#cdd4de;
  --acento:#2450c5; --acento-bg:#e9effc;
  --r0:#c81e1e; --r0bg:#fdeaea; --r1:#c2410c; --r1bg:#fdf0e7;
  --r2:#916309; --r2bg:#fcf5e3; --r3:#15803d; --r3bg:#eaf6ee;
  --r4:#5c6572; --r4bg:#f0f2f5;
  --sombra:0 1px 2px rgba(16,20,28,.05);
}
@media (prefers-color-scheme:dark){:root{
  --bg:#0d0f13; --sup:#14171d; --bg2:#1a1e26; --fg:#e9ecf1; --fg2:#98a2b3;
  --linea:#242932; --linea2:#333a46;
  --acento:#8badff; --acento-bg:#182238;
  --r0:#ff8080; --r0bg:#2b1517; --r1:#ffa25c; --r1bg:#2a1a12;
  --r2:#f5cf5a; --r2bg:#282111; --r3:#6ee7a0; --r3bg:#12241a;
  --r4:#98a2b3; --r4bg:#1c2029;
  --sombra:0 1px 2px rgba(0,0,0,.3);
}}
:root[data-theme=dark]{
  --bg:#0d0f13; --sup:#14171d; --bg2:#1a1e26; --fg:#e9ecf1; --fg2:#98a2b3;
  --linea:#242932; --linea2:#333a46;
  --acento:#8badff; --acento-bg:#182238;
  --r0:#ff8080; --r0bg:#2b1517; --r1:#ffa25c; --r1bg:#2a1a12;
  --r2:#f5cf5a; --r2bg:#282111; --r3:#6ee7a0; --r3bg:#12241a;
  --r4:#98a2b3; --r4bg:#1c2029;
  --sombra:0 1px 2px rgba(0,0,0,.3);
}
:root[data-theme=light]{
  --bg:#fbfbfc; --sup:#ffffff; --bg2:#f2f4f7; --fg:#14161a; --fg2:#5c6572;
  --linea:#e2e6ec; --linea2:#cdd4de;
  --acento:#2450c5; --acento-bg:#e9effc;
  --r0:#c81e1e; --r0bg:#fdeaea; --r1:#c2410c; --r1bg:#fdf0e7;
  --r2:#916309; --r2bg:#fcf5e3; --r3:#15803d; --r3bg:#eaf6ee;
  --r4:#5c6572; --r4bg:#f0f2f5;
  --sombra:0 1px 2px rgba(16,20,28,.05);
}
html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--fg);
  font:16px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
  -webkit-text-size-adjust:100%;-webkit-font-smoothing:antialiased}
.env{max-width:1120px;margin:0 auto;padding:0 22px}

/* ── encabezado ───────────────────────────────────────────── */
header{border-bottom:1px solid var(--linea);background:var(--sup);
  padding:30px 0 24px}
.hcab{display:flex;justify-content:space-between;align-items:flex-start;gap:16px}
h1{margin:0 0 6px;font-size:clamp(22px,3.4vw,32px);line-height:1.15;
  letter-spacing:-.025em;font-weight:700}
.sub{color:var(--fg2);margin:0;max-width:64ch;font-size:15px}
.enlaces{margin:16px 0 0;display:flex;gap:16px;flex-wrap:wrap}
.enlaces a{color:var(--acento);text-decoration:none;font-size:14px;
  font-weight:550}
.enlaces a:hover{text-decoration:underline}
/* Cuatro métricas principales; el resto es secundario y no compite. */
.stats{display:grid;gap:9px;margin-top:20px;
  grid-template-columns:repeat(4,1fr)}
.st{background:var(--bg2);border-radius:10px;padding:11px 13px}
.st b{display:block;font-size:24px;line-height:1.1;letter-spacing:-.03em;
  font-variant-numeric:tabular-nums}
.st span{color:var(--fg2);font-size:12.5px}
.st.urg{background:var(--r0bg)} .st.urg b{color:var(--r0)}
.st.urg span{color:var(--r0);opacity:.85}
.stats2{margin:11px 0 0;color:var(--fg2);font-size:13px;
  display:flex;gap:7px;flex-wrap:wrap}
.stats2 b{color:var(--fg);font-variant-numeric:tabular-nums}

/* ── navegación ───────────────────────────────────────────── */
nav{position:sticky;top:0;z-index:20;background:var(--sup);
  border-bottom:1px solid var(--linea);overflow-x:auto;
  scrollbar-width:none}
nav::-webkit-scrollbar{display:none}
nav .env{display:flex;gap:2px}
nav button{background:none;border:0;border-bottom:2.5px solid transparent;
  color:var(--fg2);padding:14px 12px;font-size:14.5px;cursor:pointer;
  white-space:nowrap;font-family:inherit;font-weight:550}
nav button:hover{color:var(--fg)}
nav button[aria-selected=true]{color:var(--acento);
  border-bottom-color:var(--acento)}

/* ── controles ────────────────────────────────────────────── */
main{padding:22px 0 70px}
.controles{display:flex;gap:9px;flex-wrap:wrap;margin-bottom:14px}
input[type=search],select{background:var(--sup);color:var(--fg);
  border:1px solid var(--linea2);border-radius:9px;padding:11px 13px;
  font-size:15px;font-family:inherit;min-height:44px}
input[type=search]{flex:1;min-width:200px}
input[type=search]:focus,select:focus{outline:2px solid var(--acento);
  outline-offset:-1px;border-color:transparent}
.conteo{color:var(--fg2);font-size:13.5px;margin:0 0 6px}

/* ── aviso de urgentes ────────────────────────────────────── */
.urgente{background:var(--r0bg);border:1px solid var(--r0);
  border-radius:11px;padding:13px 17px;margin-bottom:18px;
  color:var(--r0);font-weight:600;font-size:15px}

/* ── grupos por urgencia ──────────────────────────────────── */
.grupo{margin:26px 0 12px;display:flex;align-items:baseline;gap:10px}
.grupo h2{margin:0;font-size:14px;text-transform:uppercase;
  letter-spacing:.07em;color:var(--fg2);font-weight:650}
.grupo .n{color:var(--fg2);font-size:13px;font-variant-numeric:tabular-nums}
.grupo::after{content:"";flex:1;height:1px;background:var(--linea)}

/* ── tarjeta de convocatoria ──────────────────────────────── */
.tarj{background:var(--sup);border:1px solid var(--linea);border-radius:12px;
  margin-bottom:10px;box-shadow:var(--sombra);overflow:hidden;
  display:grid;grid-template-columns:96px 1fr}
.tarj:hover{border-color:var(--linea2)}
.gutter{padding:15px 10px;text-align:center;
  border-right:1px solid var(--linea);display:flex;flex-direction:column;
  align-items:center;justify-content:center;gap:2px}
.gnum{font-size:25px;font-weight:750;line-height:1;letter-spacing:-.04em;
  font-variant-numeric:tabular-nums}
.gtxt{font-size:11px;text-transform:uppercase;letter-spacing:.05em;
  font-weight:650;opacity:.9}
.cuerpo{padding:14px 17px;min-width:0}
.rev{font-weight:650;font-size:15px}
.tit{margin-top:4px;color:var(--fg);line-height:1.45}
.tema{margin-top:10px;padding:10px 13px;background:var(--acento-bg);
  border-radius:8px;font-size:14.5px;line-height:1.45}
.tema b{color:var(--acento)}
.meta{margin-top:9px;color:var(--fg2);font-size:12.5px;
  display:flex;gap:6px;flex-wrap:wrap;align-items:center}
.tarj a{color:var(--acento);font-size:14px;text-decoration:none;
  font-weight:550;display:inline-block;margin-top:9px}
.tarj a:hover{text-decoration:underline}
.cita{font-style:italic;color:var(--fg2);font-size:14px;line-height:1.5;
  border-left:3px solid var(--r3);padding-left:12px;margin-top:10px}
.chip{display:inline-block;background:var(--bg2);border-radius:20px;
  padding:2px 10px;font-size:12px;color:var(--fg2);white-space:nowrap}
.chip.n1{background:var(--r2bg);color:var(--r2);font-weight:600}

/* ── tabla ────────────────────────────────────────────────── */
.tablaEnv{overflow-x:auto;border:1px solid var(--linea);border-radius:11px;
  background:var(--sup)}
table{border-collapse:collapse;width:100%;font-size:14px;min-width:780px}
th,td{padding:10px 12px;text-align:left;border-bottom:1px solid var(--linea);
  vertical-align:top}
th{background:var(--bg2);position:sticky;top:50px;font-weight:650;
  white-space:nowrap;font-size:13px}
tbody tr:last-child td{border-bottom:0}
tbody tr:hover{background:var(--bg2)}
td a{color:var(--acento);text-decoration:none;font-weight:550}

/* ── avisos ───────────────────────────────────────────────── */
.aviso{background:var(--sup);border:1px solid var(--linea);
  border-left:4px solid var(--r2);border-radius:11px;padding:17px 20px;
  margin:26px 0}
.aviso h3{margin:0 0 10px;font-size:15.5px}
.aviso ol{margin:0;padding-left:20px}
.aviso li{margin-bottom:8px;color:var(--fg2);line-height:1.5}
.aviso li b{color:var(--fg)}

/* ── boletín ──────────────────────────────────────────────── */
.boletin{background:var(--acento-bg);border:1px solid var(--acento);
  border-radius:12px;padding:20px 22px;margin:26px 0}
.boletin h3{margin:0 0 6px;font-size:17px}
.boletin p{margin:0 0 14px;color:var(--fg2);font-size:14.5px;max-width:62ch}
.boletin form{display:flex;gap:9px;flex-wrap:wrap}
.boletin input{flex:1;min-width:190px;background:var(--sup);
  border:1px solid var(--linea2);border-radius:9px;padding:11px 13px;
  font-size:15px;font-family:inherit;color:var(--fg);min-height:44px}
.boletin button{background:var(--acento);color:#fff;border:0;
  border-radius:9px;padding:11px 22px;font-size:15px;font-weight:600;
  cursor:pointer;font-family:inherit;min-height:44px}
.boletin button:hover{filter:brightness(1.08)}
.boletin .nota{font-size:12.5px;margin:12px 0 0}

footer{border-top:1px solid var(--linea);color:var(--fg2);font-size:13.5px;
  padding:26px 0 44px;line-height:1.6}
footer a{color:var(--acento)}
.oculto{display:none}
#tema{background:var(--bg2);border:1px solid var(--linea2);color:var(--fg);
  border-radius:9px;width:42px;height:42px;font-size:17px;cursor:pointer;
  flex:none}

@media(max-width:760px){
  .stats{grid-template-columns:repeat(2,1fr)}
  .st b{font-size:21px}
  /* Buscador arriba en toda la fila y los dos selectores compartiendo la de
     abajo: apilados en tres filas empujaban las tarjetas fuera de pantalla. */
  .controles{gap:8px}
  .controles input[type=search]{flex:1 0 100%}
  .controles select{flex:1 1 0;min-width:0}
  .tarj{grid-template-columns:74px 1fr}
  .gnum{font-size:21px}
  .cuerpo{padding:13px 14px}
  nav button{padding:13px 9px;font-size:14px}
  th{top:48px}
  table{min-width:600px}
  header{padding:22px 0 20px}
  .env{padding:0 16px}
}
"""

JS = """
// Los datos se cargan desde datos.json en vez de incrustarse en el HTML:
// al inlinear ~380 KB de JSON el parser cortaba el <script> a la mitad.
// Además así el HTML queda liviano y los datos se pueden reutilizar aparte.
let D = {revistas:[], convocatorias:[]};
const hoy = new Date(); hoy.setHours(0,0,0,0);

function dias(f){
  if(!f) return null;
  const p = String(f).slice(0,10).split('-');
  if(p.length!==3) return null;
  const d = new Date(+p[0], +p[1]-1, +p[2]); d.setHours(0,0,0,0);
  return Math.round((d-hoy)/86400000);
}
// Nivel de urgencia: 0 = crítico … 4 = sin fecha. Determina color y grupo.
function nivelUrg(d){
  if(d===null) return 4;
  if(d<=3) return 0;
  if(d<=7) return 1;
  if(d<=21) return 2;
  return 3;
}
const PAL = ['--r0','--r1','--r2','--r3','--r4'];
function color(d){ return 'var('+PAL[nivelUrg(d)]+')'; }
function colorBg(d){ return 'var('+PAL[nivelUrg(d)]+'bg)'; }

// El plazo se parte en número + unidad para que el número domine visualmente:
// es el dato por el que la gente entra a la página.
function plazoPartes(d){
  if(d===null) return ['—','sin fecha'];
  if(d<0) return ['—','vencida'];
  if(d===0) return ['hoy','cierra'];
  return [String(d), d===1 ? 'día' : 'días'];
}
function etiqueta(d){
  if(d===null) return 'sin fecha declarada';
  if(d<0) return 'vencida';
  if(d===0) return 'cierra hoy';
  return d===1 ? 'queda 1 día' : 'quedan '+d+' días';
}
const GRUPOS = [
  {t:'Cierran en 3 días o menos', u:0},
  {t:'Esta semana',               u:1},
  {t:'Este mes',                  u:2},
  {t:'Más adelante',              u:3},
  {t:'Sin fecha de cierre declarada', u:4},
];
function esc(s){
  return String(s==null?'':s).replace(/[&<>"']/g,
    c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
function chips(o){
  const c=[];
  if(o.nivel_conicet===1) c.push(['Nivel 1','n1']);
  else if(o.nivel_conicet===2) c.push(['Nivel 2','']);
  if(o.en_scopus) c.push([String(o.scopus_estado||'').toLowerCase()==='active'
      ? 'Scopus' : 'Scopus ('+o.scopus_estado+')','']);
  if(o.en_scielo) c.push(['SciELO','']);
  if(o.en_doaj) c.push(['DOAJ','']);
  if(o.pais) c.push([o.pais,'']);
  return c.map(x=>'<span class="chip '+x[1]+'">'+esc(x[0])+'</span>').join('');
}

function gutter(d){
  const p = plazoPartes(d);
  return '<div class="gutter" style="background:'+colorBg(d)+';color:'+color(d)+'">'
       + '<span class="gnum">'+esc(p[0])+'</span>'
       + '<span class="gtxt">'+esc(p[1])+'</span></div>';
}

function tarjetaConv(c){
  const d = dias(c.fecha_cierre);
  let h = '<article class="tarj">' + gutter(d) + '<div class="cuerpo">';
  h += '<div class="rev">'+esc(c.revista)+'</div>';
  h += '<div class="tit">'+(c.es_dossier?'📑 ':'')+esc(c.titulo)+'</div>';
  if(c.tema) h += '<div class="tema"><b>Dossier:</b> '+esc(c.tema)+'</div>';
  h += '<div class="meta">'
     + (c.fecha_cierre?'<span>Cierra el '+esc(c.fecha_cierre)+'</span>':'')
     + chips(c)+'</div>';
  if(c.url) h += '<a href="'+esc(c.url)
     + '" target="_blank" rel="noopener">Abrir convocatoria →</a>';
  return h+'</div></article>';
}

function tarjetaPerm(r){
  let frase = (r.evidencia_permanente||'').split('[fuente:')[0].trim();
  let fuente = (r.evidencia_permanente||'').split('[fuente:')[1];
  fuente = fuente ? fuente.replace(']','').trim() : '';
  let h = '<article class="tarj">'
    + '<div class="gutter" style="background:var(--r3bg);color:var(--r3)">'
    + '<span class="gnum">∞</span><span class="gtxt">abierta</span></div>'
    + '<div class="cuerpo">';
  h += '<div class="rev">'+esc(r.nombre)+'</div>';
  h += '<div class="meta">'+chips(r)+'</div>';
  if(frase) h += '<div class="cita">…'+esc(frase)+'…</div>';
  const ls=[];
  if(r.sitio_url) ls.push('<a href="'+esc(r.sitio_url)
    +'" target="_blank" rel="noopener">Ir a la revista →</a>');
  if(fuente && /^https?:/.test(fuente)) ls.push('<a href="'+esc(fuente)
    +'" target="_blank" rel="noopener">Ver la fuente →</a>');
  if(ls.length) h += '<div>'+ls.join(' &nbsp;&nbsp; ')+'</div>';
  return h+'</div></article>';
}

function pinta(){
  const q = (document.getElementById('q').value||'').toLowerCase().trim();
  const pais = document.getElementById('fPais').value;
  const orden = document.getElementById('fOrden').value;
  const secc = document.querySelector('nav button[aria-selected=true]').dataset.s;

  if(secc==='conv'){
    let l = D.convocatorias.filter(c=>{
      if(pais!=='*' && c.pais!==pais) return false;
      if(orden==='dossier' && !c.es_dossier) return false;
      if(orden==='fecha' && !c.fecha_cierre) return false;
      if(!q) return true;
      return (c.revista+' '+c.titulo+' '+(c.tema||'')+' '+(c.descripcion||''))
             .toLowerCase().includes(q);
    });
    l.sort((a,b)=>{
      const da=dias(a.fecha_cierre), db=dias(b.fecha_cierre);
      if(da===null&&db===null) return a.revista.localeCompare(b.revista);
      if(da===null) return 1;
      if(db===null) return -1;
      return da-db;
    });
    document.getElementById('conteo').textContent =
      l.length+' convocatoria'+(l.length===1?'':'s');

    // Aviso de urgentes: sin esto la urgencia solo se ve al scrollear.
    const urg = l.filter(c=>{const d=dias(c.fecha_cierre);
                            return d!==null && d>=0 && d<=7;}).length;
    document.getElementById('urgente').innerHTML = urg
      ? '⏰ <b>'+urg+'</b> convocatoria'+(urg===1?'':'s')
        +' cierra'+(urg===1?'':'n')+' en 7 días o menos'
      : '';
    document.getElementById('urgente').classList.toggle('oculto', !urg);

    // Agrupadas por urgencia: 174 tarjetas en lista plana no se escanean.
    let html = '';
    GRUPOS.forEach(g=>{
      const sub = l.filter(c=>nivelUrg(dias(c.fecha_cierre))===g.u);
      if(!sub.length) return;
      html += '<div class="grupo"><h2>'+esc(g.t)+'</h2>'
            + '<span class="n">'+sub.length+'</span></div>'
            + sub.map(tarjetaConv).join('');
    });
    document.getElementById('lista').innerHTML =
      html || '<p>Sin resultados para ese filtro.</p>';

  } else if(secc==='perm'){
    let l = D.revistas.filter(r=>r.recepcion_permanente===1)
      .filter(r=>{
        if(pais!=='*' && r.pais!==pais) return false;
        if(!q) return true;
        return (r.nombre+' '+(r.institucion||'')).toLowerCase().includes(q);
      });
    document.getElementById('conteo').textContent =
      l.length+' revista'+(l.length===1?'':'s')+' con recepción permanente';
    document.getElementById('urgente').classList.add('oculto');
    document.getElementById('lista').innerHTML =
      l.length ? l.map(tarjetaPerm).join('') : '<p>Sin resultados.</p>';

  } else {
    let l = D.revistas.filter(r=>{
      if(pais!=='*' && r.pais!==pais) return false;
      if(orden==='n1' && r.nivel_conicet!==1) return false;
      if(orden==='scopus' && !r.en_scopus) return false;
      if(orden==='scielo' && !r.en_scielo) return false;
      if(orden==='perm' && r.recepcion_permanente!==1) return false;
      if(!q) return true;
      return (r.nombre+' '+(r.institucion||'')+' '+(r.issn_impreso||'')+' '
              +(r.issn_online||'')+' '+r.pais).toLowerCase().includes(q);
    });
    document.getElementById('conteo').textContent =
      l.length+' revista'+(l.length===1?'':'s');
    document.getElementById('urgente').classList.add('oculto');
    const filas = l.map(r=>{
      const issn=[r.issn_impreso,r.issn_online].filter(Boolean).join(' / ');
      const sc = r.en_scopus
        ? (String(r.scopus_estado||'').toLowerCase()==='active'?'✅':'⏸️') : '';
      return '<tr><td>'+esc(r.nombre)+'</td><td>'+esc(r.pais)+'</td>'
        +'<td>'+(r.nivel_conicet||'')+'</td><td>'+sc+'</td>'
        +'<td>'+(r.en_scielo?'✅':'')+'</td><td>'+(r.en_doaj?'✅':'')+'</td>'
        +'<td>'+(r.recepcion_permanente===1?'♾️':'')+'</td>'
        +'<td>'+esc(issn||'—')+'</td><td>'+esc(r.institucion||'—')+'</td>'
        +'<td>'+(r.sitio_url?'<a href="'+esc(r.sitio_url)
            +'" target="_blank" rel="noopener">abrir</a>':'')+'</td></tr>';
    }).join('');
    document.getElementById('lista').innerHTML =
      '<div class="tablaEnv"><table><thead><tr>'
      +'<th>Revista</th><th>País</th><th>Nivel</th><th>Scopus</th>'
      +'<th>SciELO</th><th>DOAJ</th><th>Perm.</th><th>ISSN</th>'
      +'<th>Institución</th><th>Sitio</th></tr></thead><tbody>'
      +(filas||'<tr><td colspan="10">Sin resultados.</td></tr>')
      +'</tbody></table></div>';
  }
}

function seccion(b){
  document.querySelectorAll('nav button').forEach(x=>
    x.setAttribute('aria-selected', x===b ? 'true':'false'));
  const s = b.dataset.s;
  const sel = document.getElementById('fOrden');
  sel.innerHTML = s==='conv'
    ? '<option value="*">Todas</option><option value="dossier">Solo dossiers</option>'
      +'<option value="fecha">Solo con fecha</option>'
    : s==='rev'
    ? '<option value="*">Todas</option><option value="n1">Solo Nivel 1</option>'
      +'<option value="scopus">En Scopus</option><option value="scielo">En SciELO</option>'
      +'<option value="perm">Recepción permanente</option>'
    : '<option value="*">Todas</option>';
  sel.classList.toggle('oculto', s==='perm');
  document.getElementById('cobertura').classList.toggle('oculto', s!=='rev');
  pinta();
}

document.addEventListener('DOMContentLoaded',()=>{
  document.querySelectorAll('nav button').forEach(b=>
    b.onclick=()=>seccion(b));
  document.getElementById('q').oninput = pinta;
  document.getElementById('fPais').onchange = pinta;
  document.getElementById('fOrden').onchange = pinta;
  document.getElementById('tema').onclick = ()=>{
    const r=document.documentElement;
    const oscuro = r.dataset.theme
      ? r.dataset.theme==='dark'
      : matchMedia('(prefers-color-scheme:dark)').matches;
    r.dataset.theme = oscuro ? 'light' : 'dark';
  };

  document.getElementById('conteo').textContent = 'Cargando datos…';
  fetch('datos.json')
    .then(r=>{ if(!r.ok) throw new Error('HTTP '+r.status); return r.json(); })
    .then(j=>{
      D = j;
      const paises=[...new Set(D.revistas.map(r=>r.pais))].sort();
      document.getElementById('fPais').innerHTML =
        '<option value="*">Todos los países</option>'
        + paises.map(p=>'<option>'+esc(p)+'</option>').join('');
      // La métrica de urgentes se calcula acá: depende de la fecha de hoy.
      const u = D.convocatorias.filter(c=>{const d=dias(c.fecha_cierre);
                                           return d!==null && d>=0 && d<=7;}).length;
      document.getElementById('stUrg').textContent = u;
      seccion(document.querySelector('nav button'));
    })
    .catch(e=>{
      document.getElementById('conteo').textContent = '';
      document.getElementById('lista').innerHTML =
        '<div class="aviso"><h3>No se pudieron cargar los datos</h3>'
        +'<p>'+esc(e.message)+'</p><p>Si abriste este archivo con doble clic '
        +'(<code>file://</code>), el navegador bloquea la lectura de '
        +'<code>datos.json</code>. Vela publicada, o servila con '
        +'<code>python -m http.server</code>.</p></div>';
    });
});
"""


def construir_html(revistas, convocatorias, estados, stats):
    filas_estado = "".join(
        f"<tr><td>{e['estado']}</td><td>{e['n']}</td></tr>" for e in estados)
    FORMULARIO = formulario_suscripcion()

    return f"""<!doctype html>
<html lang="es"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Panel de revistas académicas iberoamericanas</title>
<meta name="description" content="Convocatorias y llamados a dossier abiertos
 en {stats['revistas']} revistas de ciencias sociales y humanidades de
 {stats['paises']} países de Iberoamérica.">
<style>{CSS}</style>
</head><body>

<header><div class="env">
  <div class="hcab">
    <div>
      <h1>Panel de revistas académicas iberoamericanas</h1>
      <p class="sub">Convocatorias y llamados a dossier abiertos en
        <b>{stats['revistas']}</b> revistas de ciencias sociales y humanidades
        de <b>{stats['paises']}</b> países.</p>
    </div>
    <button id="tema" title="Cambiar entre tema claro y oscuro"
            aria-label="Cambiar tema">◑</button>
  </div>
  <div class="stats">
    <div class="st urg"><b id="stUrg">–</b><span>cierran en 7 días</span></div>
    <div class="st"><b>{stats['convocatorias']}</b><span>convocatorias</span></div>
    <div class="st"><b>{stats['permanentes']}</b><span>abiertas todo el año</span></div>
    <div class="st"><b>{stats['revistas']}</b><span>revistas</span></div>
  </div>
  <p class="stats2">
    <span><b>{stats['dossiers']}</b> dossiers</span> ·
    <span><b>{stats['nivel1']}</b> Nivel 1</span> ·
    <span><b>{stats['scopus']}</b> en Scopus</span> ·
    <span><b>{stats['scielo']}</b> en SciELO</span> ·
    <span><b>{stats['doaj']}</b> en DOAJ</span>
  </p>
  <p class="enlaces">
    <a href="#boletin">Recibir el resumen semanal →</a>
    <a href="{REPO}">Código en GitHub →</a>
    <a href="#limitaciones">Qué no cubre →</a>
  </p>
</div></header>

<nav><div class="env">
  <button data-s="conv" aria-selected="true">⏱️ Convocatorias</button>
  <button data-s="perm">♾️ Permanentes</button>
  <button data-s="rev">🔍 Revistas</button>
</div></nav>

<main><div class="env">
  <div class="controles">
    <input type="search" id="q" placeholder="Buscar por revista, tema, ISSN o institución…">
    <select id="fPais"></select>
    <select id="fOrden"></select>
  </div>
  <p class="conteo" id="conteo"></p>
  <div class="urgente oculto" id="urgente"></div>
  <div id="lista"></div>

  <div class="aviso oculto" id="cobertura">
    <h3>Qué se pudo revisar y qué no</h3>
    <div class="tablaEnv"><table style="min-width:0">
      <thead><tr><th>Resultado del chequeo</th><th>Revistas</th></tr></thead>
      <tbody>{filas_estado}</tbody></table></div>
  </div>

  <section class="boletin" id="boletin">
    <h3>✉️ Resumen semanal por correo</h3>
    <p>Cada lunes: las convocatorias que están por vencer, las nuevas de la
      semana y el tema de cada dossier. Dejás tu nombre y tu correo, nada más.</p>
    {FORMULARIO}
    <p class="nota">Tu correo se usa únicamente para enviarte este resumen.
      Para darte de baja alcanza con responder el correo.</p>
  </section>

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
  y boletín por correo, cloná <a href="{REPO}">el repositorio</a>.
</div></footer>

<script>{JS}</script>
</body></html>"""


def generar():
    os.makedirs(DOCS, exist_ok=True)
    revistas, convocatorias, estados, stats = reunir_datos()
    html = construir_html(revistas, convocatorias, estados, stats)

    ruta = os.path.join(DOCS, 'index.html')
    with open(ruta, 'w', encoding='utf-8') as f:
        f.write(html)

    # .nojekyll evita que GitHub Pages procese el sitio con Jekyll.
    open(os.path.join(DOCS, '.nojekyll'), 'w').close()

    # Datos que consume la página, y que además quedan reutilizables aparte.
    ruta_json = os.path.join(DOCS, 'datos.json')
    with open(ruta_json, 'w', encoding='utf-8') as f:
        json.dump({'generado': stats['generado'], 'estadisticas': stats,
                   'revistas': revistas, 'convocatorias': convocatorias},
                  f, ensure_ascii=False, separators=(',', ':'))

    return ruta, stats, os.path.getsize(ruta), os.path.getsize(ruta_json)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
    ruta, stats, tam_html, tam_json = generar()
    print(f"generado: {ruta}")
    print(f"  index.html {tam_html/1024:.0f} KB · datos.json {tam_json/1024:.0f} KB")
    for k, v in stats.items():
        print(f"  {k}: {v}")
