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
REPO = "https://github.com/eaguirre25/PANEL_REVISTAS_ACADEMICAS"


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
  --bg:#ffffff; --bg2:#f6f7f9; --fg:#16181d; --fg2:#5b6472; --linea:#e3e6ea;
  --acento:#2b5fd9; --acento-bg:#eaf0fe;
  --r0:#dc2626; --r1:#ea580c; --r2:#ca8a04; --r3:#16a34a; --r4:#6b7280;
}
@media (prefers-color-scheme:dark){:root{
  --bg:#0f1116; --bg2:#171a21; --fg:#e8eaee; --fg2:#9aa3b2; --linea:#272b34;
  --acento:#7aa2f7; --acento-bg:#1b2437;
  --r0:#f87171; --r1:#fb923c; --r2:#facc15; --r3:#4ade80; --r4:#9aa3b2;
}}
:root[data-theme=dark]{
  --bg:#0f1116; --bg2:#171a21; --fg:#e8eaee; --fg2:#9aa3b2; --linea:#272b34;
  --acento:#7aa2f7; --acento-bg:#1b2437;
  --r0:#f87171; --r1:#fb923c; --r2:#facc15; --r3:#4ade80; --r4:#9aa3b2;
}
:root[data-theme=light]{
  --bg:#ffffff; --bg2:#f6f7f9; --fg:#16181d; --fg2:#5b6472; --linea:#e3e6ea;
  --acento:#2b5fd9; --acento-bg:#eaf0fe;
  --r0:#dc2626; --r1:#ea580c; --r2:#ca8a04; --r3:#16a34a; --r4:#6b7280;
}
body{margin:0;background:var(--bg);color:var(--fg);
  font:15px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
  -webkit-text-size-adjust:100%}
.env{max-width:1080px;margin:0 auto;padding:0 20px}
header{border-bottom:1px solid var(--linea);background:var(--bg2);
  padding:38px 0 30px}
h1{margin:0 0 8px;font-size:clamp(21px,3.6vw,31px);line-height:1.2;
  letter-spacing:-.02em}
.sub{color:var(--fg2);margin:0 0 20px;max-width:60ch}
.enlaces a{color:var(--acento);text-decoration:none;font-size:14px;
  margin-right:18px;font-weight:500}
.enlaces a:hover{text-decoration:underline}
.stats{display:grid;gap:10px;margin-top:22px;
  grid-template-columns:repeat(auto-fit,minmax(112px,1fr))}
.st{background:var(--bg);border:1px solid var(--linea);border-radius:9px;
  padding:12px 13px}
.st b{display:block;font-size:22px;line-height:1.15;letter-spacing:-.02em}
.st span{color:var(--fg2);font-size:12px}
nav{position:sticky;top:0;z-index:20;background:var(--bg);
  border-bottom:1px solid var(--linea);overflow-x:auto}
nav .env{display:flex;gap:4px}
nav button{background:none;border:0;border-bottom:2px solid transparent;
  color:var(--fg2);padding:13px 14px;font-size:14px;cursor:pointer;
  white-space:nowrap;font-family:inherit;font-weight:500}
nav button[aria-selected=true]{color:var(--acento);
  border-bottom-color:var(--acento)}
main{padding:26px 0 70px}
.controles{display:flex;gap:9px;flex-wrap:wrap;margin-bottom:18px}
input[type=search],select{background:var(--bg2);color:var(--fg);
  border:1px solid var(--linea);border-radius:8px;padding:9px 12px;
  font-size:14px;font-family:inherit}
input[type=search]{flex:1;min-width:210px}
.conteo{color:var(--fg2);font-size:13px;margin-bottom:14px}
.tarj{border:1px solid var(--linea);border-left-width:5px;border-radius:9px;
  padding:14px 17px;margin-bottom:11px;background:var(--bg2)}
.cab{display:flex;justify-content:space-between;gap:14px;align-items:baseline;
  flex-wrap:wrap}
.rev{font-weight:650}
.plazo{font-weight:700;font-size:14px;white-space:nowrap}
.tit{margin-top:6px}
.tema{margin-top:9px;padding:9px 12px;background:var(--acento-bg);
  border-radius:6px;font-size:14px}
.meta{margin-top:8px;color:var(--fg2);font-size:12.5px}
.tarj a{color:var(--acento);font-size:13.5px;text-decoration:none}
.tarj a:hover{text-decoration:underline}
.cita{font-style:italic;color:var(--fg2);font-size:13.5px;
  border-left:3px solid var(--r3);padding-left:11px;margin-top:9px}
.chip{display:inline-block;background:var(--bg);border:1px solid var(--linea);
  border-radius:20px;padding:1px 9px;font-size:11.5px;margin-right:5px;
  color:var(--fg2)}
.tablaEnv{overflow-x:auto;border:1px solid var(--linea);border-radius:9px}
table{border-collapse:collapse;width:100%;font-size:13.5px;min-width:760px}
th,td{padding:9px 11px;text-align:left;border-bottom:1px solid var(--linea);
  vertical-align:top}
th{background:var(--bg2);position:sticky;top:47px;font-weight:600;
  white-space:nowrap}
tbody tr:hover{background:var(--bg2)}
td a{color:var(--acento);text-decoration:none}
.aviso{background:var(--bg2);border:1px solid var(--linea);
  border-left:4px solid var(--r2);border-radius:9px;padding:15px 18px;
  margin:20px 0}
.aviso h3{margin:0 0 9px;font-size:15px}
.aviso ol{margin:0;padding-left:20px}
.aviso li{margin-bottom:7px;color:var(--fg2)}
footer{border-top:1px solid var(--linea);color:var(--fg2);font-size:13px;
  padding:26px 0 40px}
.oculto{display:none}
#tema{position:fixed;right:14px;bottom:14px;background:var(--bg2);
  border:1px solid var(--linea);color:var(--fg);border-radius:50%;
  width:42px;height:42px;font-size:17px;cursor:pointer;z-index:30}
@media(max-width:620px){
  table{min-width:560px}
  th{top:45px}
  .st b{font-size:19px}
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
function color(d){
  if(d===null) return 'var(--r4)';
  if(d<=3) return 'var(--r0)';
  if(d<=7) return 'var(--r1)';
  if(d<=21) return 'var(--r2)';
  return 'var(--r3)';
}
function etiqueta(d){
  if(d===null) return 'sin fecha declarada';
  if(d<0) return 'vencida';
  if(d===0) return 'cierra hoy';
  return d===1 ? 'queda 1 día' : 'quedan '+d+' días';
}
function esc(s){
  return String(s==null?'':s).replace(/[&<>"']/g,
    c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
function chips(o){
  const c=[];
  if(o.nivel_conicet===1) c.push('🥇 Nivel 1');
  else if(o.nivel_conicet===2) c.push('🥈 Nivel 2');
  if(o.en_scopus) c.push(String(o.scopus_estado||'').toLowerCase()==='active'
      ? 'Scopus' : 'Scopus ('+esc(o.scopus_estado)+')');
  if(o.en_scielo) c.push('SciELO');
  if(o.en_doaj) c.push('DOAJ');
  if(o.pais) c.push(o.pais);
  return c.map(x=>'<span class="chip">'+esc(x)+'</span>').join('');
}

function tarjetaConv(c){
  const d = dias(c.fecha_cierre), col = color(d);
  let h = '<div class="tarj" style="border-left-color:'+col+'">';
  h += '<div class="cab"><span class="rev">'+esc(c.revista)+'</span>'
     + '<span class="plazo" style="color:'+col+'">'+etiqueta(d)+'</span></div>';
  h += '<div class="tit">'+(c.es_dossier?'📑 ':'')+esc(c.titulo)+'</div>';
  if(c.tema) h += '<div class="tema"><b>Tema del dossier:</b> '+esc(c.tema)+'</div>';
  h += '<div class="meta">'+(c.fecha_cierre?'Cierra el '+esc(c.fecha_cierre)+' · ':'')
     + chips(c)+'</div>';
  if(c.url) h += '<div style="margin-top:8px"><a href="'+esc(c.url)
     + '" target="_blank" rel="noopener">Abrir convocatoria →</a></div>';
  return h+'</div>';
}

function tarjetaPerm(r){
  let frase = (r.evidencia_permanente||'').split('[fuente:')[0].trim();
  let fuente = (r.evidencia_permanente||'').split('[fuente:')[1];
  fuente = fuente ? fuente.replace(']','').trim() : '';
  let h = '<div class="tarj" style="border-left-color:var(--r3)">';
  h += '<div class="cab"><span class="rev">'+esc(r.nombre)+'</span></div>';
  h += '<div class="meta">'+chips(r)+'</div>';
  if(frase) h += '<div class="cita">…'+esc(frase)+'…</div>';
  const ls=[];
  if(r.sitio_url) ls.push('<a href="'+esc(r.sitio_url)
    +'" target="_blank" rel="noopener">Ir a la revista →</a>');
  if(fuente && /^https?:/.test(fuente)) ls.push('<a href="'+esc(fuente)
    +'" target="_blank" rel="noopener">Ver la fuente →</a>');
  if(ls.length) h += '<div style="margin-top:9px">'+ls.join(' &nbsp; ')+'</div>';
  return h+'</div>';
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
    document.getElementById('lista').innerHTML =
      l.length ? l.map(tarjetaConv).join('') : '<p>Sin resultados.</p>';

  } else if(secc==='perm'){
    let l = D.revistas.filter(r=>r.recepcion_permanente===1)
      .filter(r=>{
        if(pais!=='*' && r.pais!==pais) return false;
        if(!q) return true;
        return (r.nombre+' '+(r.institucion||'')).toLowerCase().includes(q);
      });
    document.getElementById('conteo').textContent =
      l.length+' revista'+(l.length===1?'':'s')+' con recepción permanente';
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
  <h1>Panel de revistas académicas iberoamericanas</h1>
  <p class="sub">Convocatorias y llamados a dossier abiertos en
    <b>{stats['revistas']}</b> revistas de ciencias sociales y humanidades de
    <b>{stats['paises']}</b> países. Los plazos se calculan con la fecha de hoy.</p>
  <p class="enlaces">
    <a href="{REPO}">Código en GitHub →</a>
    <a href="{REPO}#instalacion">Cómo instalarlo →</a>
    <a href="{REPO}#%EF%B8%8F-limitaciones">Limitaciones →</a>
  </p>
  <div class="stats">
    <div class="st"><b>{stats['revistas']}</b><span>revistas</span></div>
    <div class="st"><b>{stats['convocatorias']}</b><span>convocatorias</span></div>
    <div class="st"><b>{stats['dossiers']}</b><span>dossiers</span></div>
    <div class="st"><b>{stats['permanentes']}</b><span>permanentes</span></div>
    <div class="st"><b>{stats['nivel1']}</b><span>Nivel 1</span></div>
    <div class="st"><b>{stats['scopus']}</b><span>en Scopus</span></div>
    <div class="st"><b>{stats['scielo']}</b><span>en SciELO</span></div>
    <div class="st"><b>{stats['doaj']}</b><span>en DOAJ</span></div>
  </div>
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
  <div id="lista"></div>

  <div class="aviso oculto" id="cobertura">
    <h3>Qué se pudo revisar y qué no</h3>
    <div class="tablaEnv"><table style="min-width:0">
      <thead><tr><th>Resultado del chequeo</th><th>Revistas</th></tr></thead>
      <tbody>{filas_estado}</tbody></table></div>
  </div>

  <div class="aviso">
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

<button id="tema" title="Cambiar tema">◑</button>
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
