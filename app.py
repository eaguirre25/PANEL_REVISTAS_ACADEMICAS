"""Interfaz web del Tracker de Revistas CONICET."""
import re
from datetime import date, datetime

import pandas as pd
import streamlit as st

from database import (init_db, obtener_revistas, obtener_convocatorias,
                      obtener_log, contar, conectar, marcar_recepcion_permanente,
                      agregar_suscriptor, baja_suscriptor, obtener_suscriptores)

TITULO = "Revistas iberoamericanas en ciencias sociales y humanidades"

st.set_page_config(page_title=TITULO, page_icon="📚",
                   layout="wide", initial_sidebar_state="expanded")

init_db()


def dias_restantes(fecha_iso):
    if not fecha_iso:
        return None
    try:
        return (date.fromisoformat(str(fecha_iso)[:10]) - date.today()).days
    except ValueError:
        return None


def semaforo(d):
    if d is None:
        return "#6b7280", "sin fecha declarada", "⚪"
    if d <= 3:
        return "#dc2626", f"{d} día{'s' if d != 1 else ''}", "🔴"
    if d <= 7:
        return "#ea580c", f"{d} días", "🟠"
    if d <= 21:
        return "#ca8a04", f"{d} días", "🟡"
    return "#16a34a", f"{d} días", "🟢"


def chips(r):
    """Etiquetas de nivel CONICET e indización de una revista (dict)."""
    out = []
    nivel = r.get('nivel_conicet')
    if nivel == 1:
        out.append("🥇 Nivel 1")
    elif nivel == 2:
        out.append("🥈 Nivel 2")
    elif r.get('origen') == 'externa':
        out.append("nivel sin determinar")
    if r.get('en_scopus'):
        estado = (r.get('scopus_estado') or '').lower()
        out.append("Scopus" if estado == 'active'
                   else f"Scopus ({r.get('scopus_estado')})")
    if r.get('en_scielo'):
        out.append("SciELO")
    if r.get('en_doaj'):
        out.append("DOAJ")
    if r.get('pais') and r.get('origen') == 'externa':
        out.append(r['pais'])
    return out


# ─────────────────────────── barra lateral ───────────────────────────
with st.sidebar:
    st.header("⚙️ Panel")

    n = contar()
    st.metric("Revistas", n['revistas'])
    c1, c2 = st.columns(2)
    c1.metric("Convocatorias", n['convocatorias'])

    conn = conectar()
    n_perm = conn.execute(
        "SELECT COUNT(*) FROM revistas WHERE recepcion_permanente=1").fetchone()[0]
    n_niv1 = conn.execute(
        "SELECT COUNT(*) FROM revistas WHERE nivel_conicet=1").fetchone()[0]
    conn.close()
    c2.metric("Permanentes", n_perm)

    st.divider()
    st.caption("**Actualizar** (cada paso tarda varios minutos)")

    if st.button("🔄 Buscar convocatorias", use_container_width=True):
        from convocatorias import buscar_convocatorias
        b = st.progress(0.0, "Revisando...")
        res = buscar_convocatorias(progreso=lambda i, t: b.progress(i / t, f"{i}/{t}"))
        b.empty()
        st.success(f"{res['convocatorias']} convocatorias ({res['nuevas']} nuevas)")
        st.rerun()

    if st.button("♾️ Detectar permanentes", use_container_width=True):
        from permanentes import detectar_permanentes
        b = st.progress(0.0, "Revisando...")
        res = detectar_permanentes(progreso=lambda i, t: b.progress(i / t, f"{i}/{t}"))
        b.empty()
        st.success(f"{res['permanentes']} revistas con recepción permanente")
        st.rerun()

    if st.button("🏅 Actualizar indización", use_container_width=True):
        from indizacion import actualizar_indizacion
        b = st.progress(0.0, "Consultando Scopus/SciELO...")
        res = actualizar_indizacion(progreso=lambda i, t: b.progress(i / t, f"{i}/{t}"))
        b.empty()
        st.success(f"Nivel 1: {res['nivel1']} · Nivel 2: {res['nivel2']}")
        st.rerun()

    if st.button("📚 Actualizar catálogo NBRA", use_container_width=True):
        from catalogo import actualizar_catalogo
        b = st.progress(0.0, "Descargando fichas...")
        res = actualizar_catalogo(progreso=lambda i, t: b.progress(i / t, f"{i}/{t}"))
        b.empty()
        st.success(f"{res['guardadas']} revistas ({res['nuevas']} nuevas)")
        st.rerun()

    st.divider()
    log = obtener_log(1)
    if log:
        st.caption(f"Última actualización\n\n**{str(log[0]['fecha'])[:16]}**\n\n{log[0]['detalles']}")


st.title(f"📚 {TITULO.upper()}")

convocatorias = obtener_convocatorias()
revistas = obtener_revistas()
por_nombre = {r['nombre']: r for r in revistas}

tab_reloj, tab_perm, tab_conv, tab_cerr, tab_rev, tab_bol, tab_cob = st.tabs(
    ["⏱️ Reloj", "♾️ Permanentes", "📋 Convocatorias", "✕ Cerradas",
     "🔍 Buscar revistas", "✉️ Boletín", "📊 Cobertura"])


# ─────────────────────────── reloj ───────────────────────────
with tab_reloj:
    st.subheader("Convocatorias con plazo declarado")

    con_fecha = sorted(
        ((d, c) for c in convocatorias
         if (d := dias_restantes(c['fecha_cierre'])) is not None and d >= 0),
        key=lambda x: x[0])

    if not con_fecha:
        st.info("No hay convocatorias con fecha de cierre detectada.")
    else:
        urgentes = sum(1 for d, _ in con_fecha if d <= 7)
        if urgentes:
            st.warning(f"**{urgentes}** convocatoria(s) cierran en 7 días o menos.")

        for d, c in con_fecha:
            color, etiqueta, emoji = semaforo(d)
            etiquetas = chips(por_nombre.get(c['revista'], {}))
            bloque_tema = ""
            if c.get('es_dossier'):
                if c.get('tema'):
                    bloque_tema = (
                        f'<div style="margin-top:8px;padding:8px 12px;'
                        f'background:rgba(99,102,241,.13);border-radius:5px;'
                        f'font-size:.92em;"><strong>📑 Dossier:</strong> '
                        f'{c["tema"]}</div>')
                else:
                    bloque_tema = ('<div style="margin-top:8px;font-size:.85em;'
                                   'opacity:.7;">📑 Es un dossier — el tema no se '
                                   'pudo aislar; abrí el enlace.</div>')
            # Sin saltos ni sangría: el markdown de Streamlit interpreta las
            # líneas indentadas como bloque de código y muestra el HTML crudo.
            pie = (f"Cierra el {c['fecha_cierre']} · "
                   f"{' · '.join(etiquetas) or 'sin datos de indización'}")
            st.markdown(
                f'<div style="border-left:6px solid {color};'
                f'background:rgba(128,128,128,.08);padding:14px 18px;'
                f'margin:10px 0;border-radius:6px;">'
                f'<div style="display:flex;justify-content:space-between;'
                f'gap:16px;align-items:baseline;">'
                f'<strong style="font-size:1.05em;">{emoji} {c["revista"]}</strong>'
                f'<span style="color:{color};font-weight:700;'
                f'white-space:nowrap;">{etiqueta}</span></div>'
                f'<div style="margin-top:6px;">{c["titulo"]}</div>'
                f'{bloque_tema}'
                f'<div style="margin-top:6px;opacity:.75;font-size:.85em;">'
                f'{pie}</div></div>',
                unsafe_allow_html=True)
            if c['url']:
                st.markdown(f"[Abrir convocatoria →]({c['url']})")


# ─────────────────────────── permanentes ───────────────────────────
with tab_perm:
    st.subheader("Revistas que reciben artículos todo el año")
    st.caption("No tienen plazo: se puede enviar en cualquier momento. "
               "Cada una muestra la frase textual que lo declara.")

    permanentes = [r for r in revistas if r.get('recepcion_permanente') == 1]

    f1, f2 = st.columns([3, 1])
    with f1:
        q = f1.text_input("Filtrar", "", placeholder="nombre, institución o ISSN",
                          key="q_perm")
    with f2:
        solo_n1 = f2.checkbox("Solo Nivel 1", key="n1_perm")

    mostradas = []
    for r in permanentes:
        if solo_n1 and r.get('nivel_conicet') != 1:
            continue
        if q:
            blob = (f"{r['nombre']} {r['institucion'] or ''} "
                    f"{r['issn_impreso'] or ''} {r['issn_online'] or ''}").lower()
            if q.lower() not in blob:
                continue
        mostradas.append(r)

    st.caption(f"{len(mostradas)} de {len(permanentes)} revistas con recepción permanente")

    for r in mostradas:
        with st.container(border=True):
            izq, der = st.columns([4, 1])
            with izq:
                st.markdown(f"**{r['nombre']}**")
                etiquetas = chips(r)
                if etiquetas:
                    st.caption(" · ".join(etiquetas))
                evid = r.get('evidencia_permanente') or ''
                frase, _, fuente = evid.partition('[fuente:')
                if frase:
                    st.markdown(
                        f"<div style='font-size:.87em;opacity:.8;font-style:italic;"
                        f"border-left:3px solid #16a34a;padding-left:10px;'>"
                        f"…{frase.strip()}…</div>", unsafe_allow_html=True)
            with der:
                if r['sitio_url']:
                    st.markdown(f"[Ir a la revista →]({r['sitio_url']})")
                if fuente:
                    st.markdown(f"[Ver la fuente →]({fuente.rstrip(']').strip()})")

    st.divider()
    with st.expander("➕ Marcar una revista a mano "
                     "(para las que no se pudieron revisar automáticamente)"):
        st.caption("45 revistas usan protección anti-bot y no se pueden leer. "
                   "Si verificás en el sitio que recibe todo el año, marcala acá.")
        conn = conectar()
        candidatas = conn.execute(
            """SELECT id, nombre, sitio_url FROM revistas
               WHERE COALESCE(recepcion_permanente, 0) = 0 ORDER BY nombre""").fetchall()
        conn.close()

        opciones = {f"{c['nombre']}": c['id'] for c in candidatas}
        elegida = st.selectbox("Revista", ["—"] + list(opciones.keys()))
        if elegida != "—":
            rid = opciones[elegida]
            url_rev = next(c['sitio_url'] for c in candidatas if c['id'] == rid)
            if url_rev:
                st.markdown(f"[Abrir {elegida} →]({url_rev})")
            nota = st.text_input("Frase que lo confirma (pegala del sitio)", "")
            if st.button("Marcar como recepción permanente"):
                if nota.strip():
                    marcar_recepcion_permanente(
                        rid, True,
                        f"{nota.strip()}  [verificado a mano el {date.today()}]")
                    st.success(f"{elegida} marcada.")
                    st.rerun()
                else:
                    st.error("Pegá la frase del sitio que lo confirma, "
                             "para que quede registrado de dónde salió.")


# ─────────────────────────── convocatorias ───────────────────────────
with tab_conv:
    st.subheader(f"Convocatorias detectadas ({len(convocatorias)})")

    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        q = st.text_input("Filtrar por revista, título o tema", "", key="q_conv")
    with c2:
        modo = st.selectbox("Mostrar", ["Todas", "Solo con fecha", "Solo sin fecha"])
    with c3:
        solo_dossier = st.checkbox("Solo dossiers")

    n_dossier = sum(1 for c in convocatorias if c.get('es_dossier'))
    n_tema = sum(1 for c in convocatorias if c.get('tema'))
    st.caption(f"📑 {n_dossier} son dossiers o números temáticos "
               f"({n_tema} con el tema identificado)")

    filtradas = []
    for c in convocatorias:
        if solo_dossier and not c.get('es_dossier'):
            continue
        if q:
            blob = (f"{c['revista']} {c['titulo']} {c['descripcion'] or ''} "
                    f"{c.get('tema') or ''}").lower()
            if q.lower() not in blob:
                continue
        d = dias_restantes(c['fecha_cierre'])
        if modo == "Solo con fecha" and d is None:
            continue
        if modo == "Solo sin fecha" and d is not None:
            continue
        filtradas.append((d if d is not None else 10**6, d, c))

    filtradas.sort(key=lambda x: x[0])
    st.caption(f"{len(filtradas)} resultado(s)")

    for _, d, c in filtradas:
        color, etiqueta, emoji = semaforo(d)
        with st.container(border=True):
            izq, der = st.columns([5, 1])
            with izq:
                st.markdown(f"**{'📑 ' if c.get('es_dossier') else ''}{c['titulo']}**")
                etiquetas = chips(por_nombre.get(c['revista'], {}))
                st.caption(f"📚 {c['revista']}" +
                           (f" · {' · '.join(etiquetas)}" if etiquetas else ""))
                if c.get('tema'):
                    st.info(f"**Tema del dossier:** {c['tema']}")
                if c['descripcion']:
                    t = c['descripcion']
                    st.write(t[:300] + ("…" if len(t) > 300 else ""))
                if c['url']:
                    st.markdown(f"[Abrir convocatoria →]({c['url']})")
            with der:
                st.markdown(
                    f"<div style='text-align:right;color:{color};font-weight:700;'>"
                    f"{emoji}<br>{etiqueta}</div>", unsafe_allow_html=True)
                if c['fecha_cierre']:
                    st.caption(str(c['fecha_cierre']))


# ─────────────────────────── cerradas ───────────────────────────
with tab_cerr:
    from database import obtener_convocatorias_cerradas
    cerradas = obtener_convocatorias_cerradas(meses=8)

    st.subheader(f"Convocatorias cerradas en los últimos meses ({len(cerradas)})")
    st.caption("Una convocatoria cerrada sigue informando: dice si vuelve a "
               "abrirse y si la revista recibe artículos igual.")

    if not cerradas:
        st.info("Todavía no hay convocatorias cerradas registradas. Se van a "
                "ir sumando a medida que venzan los plazos.")
    else:
        sigue = sum(1 for c in cerradas
                    if c['revista_permanente'] or c['sigue_recibiendo'])
        if sigue:
            st.success(f"♾️ De estas, **{sigue}** son de revistas que **siguen "
                       "recibiendo artículos** pese al cierre del dossier.")

        f1, f2 = st.columns([3, 1])
        q_cer = f1.text_input("Filtrar", "", key="q_cer",
                              placeholder="revista, título o tema")
        solo_abiertas = f2.checkbox("Solo las que siguen recibiendo")

        for c in cerradas:
            if solo_abiertas and not (c['revista_permanente']
                                      or c['sigue_recibiendo']):
                continue
            if q_cer:
                blob = f"{c['revista']} {c['titulo']} {c.get('tema') or ''}".lower()
                if q_cer.lower() not in blob:
                    continue

            with st.container(border=True):
                izq, der = st.columns([5, 1])
                with izq:
                    st.markdown(f"**{'📑 ' if c['es_dossier'] else ''}{c['titulo']}**")
                    st.caption(f"📚 {c['revista']} · {c['pais']}")
                    if c.get('tema'):
                        st.caption(f"Tema: {c['tema']}")

                    if c['fecha_reapertura']:
                        st.success(f"🔁 Reabre el **{c['fecha_reapertura']}**")
                    if c['revista_permanente']:
                        st.info("♾️ La revista **recibe artículos todo el año**: "
                                "podés enviar aunque este dossier haya cerrado.")
                    elif c['sigue_recibiendo']:
                        st.info("El aviso indica que **se siguen recibiendo "
                                "trabajos** por fuera del dossier.")
                    elif not c['fecha_reapertura']:
                        st.caption("No declara reapertura ni recepción abierta.")

                    if c['url']:
                        st.markdown(f"[Ver la convocatoria →]({c['url']})")
                with der:
                    d = dias_restantes(c['fecha_cierre'])
                    st.markdown("<div style='text-align:right;color:#6b7280;"
                                "font-weight:700;'>✕<br>cerrada</div>",
                                unsafe_allow_html=True)
                    st.caption(str(c['fecha_cierre']))
                    if d is not None:
                        st.caption(f"hace {abs(d)} días")


# ─────────────────────────── buscar revistas ───────────────────────────
with tab_rev:
    n_nbra = sum(1 for r in revistas if (r.get('origen') or 'NBRA') == 'NBRA')
    n_ext = len(revistas) - n_nbra
    st.subheader(f"{len(revistas)} revistas — {n_nbra} del NBRA argentino "
                 f"+ {n_ext} del resto de América Latina")

    c1, c2, c3 = st.columns([3, 1, 1])
    with c1:
        busq = st.text_input("Buscar por nombre, ISSN o institución", "", key="q_rev")
    with c2:
        f_origen = st.selectbox("Catálogo", ["Todos", "NBRA (Argentina)",
                                             "Resto de América Latina"])
    with c3:
        f_base = st.selectbox("Indizada en", ["Cualquiera", "Scopus", "SciELO", "DOAJ"])

    d1, d2, d3 = st.columns([1, 1, 2])
    f_nivel = d1.selectbox("Nivel CONICET", ["Todos", "Nivel 1", "Nivel 2",
                                             "Sin determinar"])
    paises = sorted({r['pais'] for r in revistas if r.get('pais')})
    f_pais = d2.selectbox("País", ["Todos"] + paises)
    solo_conv = d3.checkbox("Solo con convocatoria abierta")
    solo_perm = d3.checkbox("Solo con recepción permanente")

    revistas_con_conv = {c['revista'] for c in convocatorias}

    filas = []
    for r in revistas:
        origen = r.get('origen') or 'NBRA'
        if f_origen == "NBRA (Argentina)" and origen != 'NBRA':
            continue
        if f_origen == "Resto de América Latina" and origen != 'externa':
            continue
        if f_pais != "Todos" and r.get('pais') != f_pais:
            continue
        if solo_conv and r['nombre'] not in revistas_con_conv:
            continue
        if solo_perm and r.get('recepcion_permanente') != 1:
            continue
        if f_nivel == "Nivel 1" and r.get('nivel_conicet') != 1:
            continue
        if f_nivel == "Nivel 2" and r.get('nivel_conicet') != 2:
            continue
        if f_nivel == "Sin determinar" and r.get('nivel_conicet') is not None:
            continue
        if f_base == "Scopus" and not r.get('en_scopus'):
            continue
        if f_base == "SciELO" and not r.get('en_scielo'):
            continue
        if f_base == "DOAJ" and not r.get('en_doaj'):
            continue
        if busq:
            blob = (f"{r['nombre']} {r['issn_impreso'] or ''} "
                    f"{r['issn_online'] or ''} {r['institucion'] or ''} "
                    f"{r.get('pais') or ''}").lower()
            if busq.lower() not in blob:
                continue

        issn = " / ".join(x for x in [r['issn_impreso'], r['issn_online']] if x)
        scopus = ""
        if r.get('en_scopus'):
            scopus = "✅" if (r.get('scopus_estado') or '').lower() == 'active' else "⏸️"
        filas.append({
            "Revista": r['nombre'],
            "País": r.get('pais') or "Argentina",
            # None (no "") para que la columna quede numérica y Arrow no falle.
            "Nivel": r.get('nivel_conicet'),
            "Scopus": scopus,
            "SciELO": "✅" if r.get('en_scielo') else "",
            "DOAJ": "✅" if r.get('en_doaj') else "",
            "Permanente": "♾️" if r.get('recepcion_permanente') == 1 else "",
            "Convocatoria": "📋" if r['nombre'] in revistas_con_conv else "",
            "ISSN": issn or "—",
            "Institución": r['institucion'] or "—",
            "Indexación declarada": r.get('indexacion_declarada') or "",
            "Sitio": r['sitio_url'] or "",
            "Ficha": r['ficha_url'] or "",
        })

    st.caption(f"{len(filas)} resultado(s)  ·  ⏸️ = título discontinuado por Scopus  ·  "
               "«Indexación declarada» es lo que afirma el listado de origen, "
               "sin verificar")
    st.dataframe(
        pd.DataFrame(filas), use_container_width=True, hide_index=True,
        column_config={
            "Sitio": st.column_config.LinkColumn("Sitio", display_text="abrir"),
            "Ficha": st.column_config.LinkColumn("Ficha", display_text="CAICYT"),
            "Revista": st.column_config.TextColumn(width="large"),
            "Nivel": st.column_config.NumberColumn(width="small"),
        })

    st.info("**Qué significa el nivel.** Es la jerarquía de la Res. D 2249/2014 del "
            "CONICET, que clasifica *las bases de indización* —no las revistas una "
            "por una. Nivel 1: Web of Science, Scopus, ERIH, SciELO.org, CIRC-A. "
            "Nivel 2: Sage, Springer, Taylor & Francis, Wiley, JSTOR, REDALyC y el "
            "Núcleo Básico. Las revistas argentinas del NBRA son **Nivel 2 como "
            "piso** y suben a Nivel 1 con Scopus o SciELO. Las **extranjeras no "
            "tienen ese piso**: si no están en Scopus ni SciELO su nivel queda "
            "*sin determinar*, porque haría falta verificar REDALyC o Latindex "
            "Catálogo, que no publican listados abiertos comparables. "
            "La resolución advierte que *«dentro de un mismo nivel conviven "
            "revistas que difieren entre sí respecto de su calidad»*.")


# ─────────────────────────── boletín ───────────────────────────
with tab_bol:
    st.subheader("Resumen semanal por correo")
    st.caption("Cada lunes, después de actualizar, se arma un resumen con las "
               "convocatorias que están por vencer y las nuevas que aparecieron.")

    import os
    from boletin import cargar_config, guardar_informe, DIR_INFORMES, DIAS_AVISO

    izq, der = st.columns([1, 1])

    with izq:
        st.markdown("**Suscribirse**")
        with st.form("alta_suscriptor"):
            nombre_s = st.text_input("Nombre completo")
            email_s = st.text_input("Correo electrónico")
            enviado = st.form_submit_button("Suscribirme")
        if enviado:
            if not nombre_s.strip():
                st.error("Escribí tu nombre completo.")
            elif not re.fullmatch(r"[^@\s]+@[^@\s]+\.[A-Za-z]{2,}", email_s.strip()):
                st.error("Ese correo no parece válido.")
            else:
                ok, msg = agregar_suscriptor(nombre_s, email_s)
                if ok:
                    from boletin import enviar_bienvenida
                    enviado, detalle = enviar_bienvenida(nombre_s, email_s)
                    st.success(msg + ("  " + detalle if enviado else ""))
                    if not enviado:
                        st.info(detalle)
                else:
                    st.error(msg)
                st.rerun()

        suscriptores = obtener_suscriptores()
        if suscriptores:
            st.markdown(f"**Suscriptores ({len(suscriptores)})**")
            for s in suscriptores:
                col_a, col_b = st.columns([4, 1])
                ultimo = (str(s['ultimo_envio'])[:16] if s['ultimo_envio']
                          else "sin envíos aún")
                col_a.write(f"{s['nombre']} · `{s['email']}`  \n"
                            f"<span style='font-size:.8em;opacity:.7;'>"
                            f"último envío: {ultimo}</span>",
                            unsafe_allow_html=True)
                if col_b.button("Baja", key=f"baja_{s['id']}"):
                    baja_suscriptor(s['email'])
                    st.rerun()

    with der:
        st.markdown("**Estado del envío**")
        cfg = cargar_config()
        if cfg:
            st.success(f"Correo configurado ({cfg['servidor']}). "
                       "El boletín se enviará automáticamente.")
        else:
            st.warning(
                "**El correo todavía no está configurado.** El resumen se "
                "genera igual como archivo HTML, pero no se envía.\n\n"
                "Para activarlo, copiá `config_email.ejemplo.json` como "
                "`config_email.json` y completalo **vos mismo** con los datos "
                "de tu cuenta.\n\n"
                "Si usás Gmail, no pongas la contraseña de tu cuenta: generá "
                "una *contraseña de aplicación* en "
                "myaccount.google.com/apppasswords y usá esa.")

        st.divider()
        if st.button("👁️ Generar el resumen ahora (sin enviar)",
                     use_container_width=True):
            ruta = guardar_informe()
            st.success(f"Generado: `{os.path.basename(ruta)}`")
            with open(ruta, encoding='utf-8') as f:
                st.components.v1.html(f.read(), height=620, scrolling=True)

        if os.path.isdir(DIR_INFORMES):
            previos = sorted(os.listdir(DIR_INFORMES), reverse=True)[:8]
            if previos:
                st.caption("Informes generados: " + ", ".join(previos))

    st.divider()
    st.markdown(f"""
**Qué incluye el resumen**

- Convocatorias que cierran en los próximos **{DIAS_AVISO} días**, ordenadas por urgencia
- Convocatorias **nuevas** detectadas en la última semana
- Para los dossiers, **el tema** cuando se pudo aislar del aviso
- Cuántas revistas reciben artículos todo el año

**Cuándo se envía.** La tarea de Windows corre los lunes a las 10:00: primero
actualiza los datos y después arma y manda el resumen. Si el correo no está
configurado, el archivo igual queda en la carpeta `informes/`.
""")


# ─────────────────────────── cobertura ───────────────────────────
with tab_cob:
    st.subheader("Qué se pudo revisar y qué no")

    n = contar()
    conn = conectar()
    n_perm = conn.execute("SELECT COUNT(*) FROM revistas WHERE recepcion_permanente=1").fetchone()[0]
    n_scopus = conn.execute("SELECT COUNT(*) FROM revistas WHERE en_scopus=1").fetchone()[0]
    n_scielo = conn.execute("SELECT COUNT(*) FROM revistas WHERE en_scielo=1").fetchone()[0]
    n_doaj = conn.execute("SELECT COUNT(*) FROM revistas WHERE en_doaj=1").fetchone()[0]

    m = st.columns(6)
    m[0].metric("Revistas", n['revistas'])
    m[1].metric("Nivel 1", n_niv1)
    m[2].metric("Permanentes", n_perm)
    m[3].metric("Scopus", n_scopus)
    m[4].metric("SciELO", n_scielo)
    m[5].metric("DOAJ", n_doaj)

    st.markdown("**Resultado del último chequeo de convocatorias**")
    estados = conn.execute(
        """SELECT COALESCE(estado_chequeo,'no revisada') AS estado, COUNT(*) AS n
           FROM revistas GROUP BY estado ORDER BY n DESC""").fetchall()
    st.dataframe(pd.DataFrame([{"Estado": e['estado'], "Revistas": e['n']}
                               for e in estados]),
                 use_container_width=True, hide_index=True)

    # ── navegador asistido ──
    from navegador_asistido import estado_cola
    cola = estado_cola()
    if cola:
        total_cola = sum(n for _, n, _ in cola)
        st.markdown("**🖥️ Leer las pendientes con el navegador asistido**")
        st.caption(
            f"{total_cola} revistas en {len(cola)} dominios no se pudieron leer. "
            "Abre Chrome en un perfil aparte, con sesión que se reutiliza entre "
            "corridas. Si aparece una verificación, resolvela en la ventana; "
            "queda guardada para las próximas.")

        st.dataframe(
            pd.DataFrame([{"Dominio": d, "Revistas": n,
                           "Con lectura previa": ok} for d, n, ok in cola]),
            use_container_width=True, hide_index=True)

        c1, c2 = st.columns([2, 1])
        doms = c1.multiselect("Limitar a estos dominios (vacío = todos)",
                              [d for d, _, _ in cola])
        if c2.button("Abrir navegador y leer", use_container_width=True):
            from navegador_asistido import revisar
            barra = st.progress(0.0, "Abriendo Chrome...")
            res = revisar(dominios=doms or None,
                          progreso=lambda i, t, n: barra.progress(
                              i / t, f"{i}/{t} · {n[:40]}"))
            barra.empty()
            st.success(f"{res['revisadas']} revistas leídas · "
                       f"{res['convocatorias']} convocatorias "
                       f"({res['nuevas']} nuevas) · "
                       f"{res['permanentes']} recepciones permanentes")
            for p in res['pendientes']:
                st.warning(p)
            st.rerun()
        st.divider()

    st.markdown("**Revistas que requieren revisión manual**")
    st.caption("Su servidor no responde, cambió de dirección o exige "
               "registrarse. Si tienen convocatoria abierta, no aparece acá.")
    filas = conn.execute(
        """SELECT nombre, estado_chequeo, sitio_url, nivel_conicet FROM revistas
           WHERE estado_chequeo IS NOT NULL
             AND (estado_chequeo LIKE '%anti-bot%' OR estado_chequeo LIKE '%login%'
                  OR estado_chequeo LIKE '%inaccesible%' OR estado_chequeo LIKE 'http%'
                  OR estado_chequeo LIKE '%redirec%')
           ORDER BY nombre""").fetchall()
    conn.close()
    st.dataframe(
        pd.DataFrame([{"Revista": f['nombre'], "Nivel": f['nivel_conicet'],
                       "Motivo": f['estado_chequeo'], "Sitio": f['sitio_url']}
                      for f in filas]),
        use_container_width=True, hide_index=True,
        column_config={"Sitio": st.column_config.LinkColumn("Sitio",
                                                            display_text="abrir")})

    st.divider()
    st.markdown("**Historial de actualizaciones**")
    log = obtener_log(40)
    if log:
        st.dataframe(
            pd.DataFrame([{"Fecha": str(l['fecha'])[:19], "Tipo": l['tipo'],
                           "Detalle": l['detalles']} for l in log]),
            use_container_width=True, hide_index=True)
