"""
Completa los ISSN de las revistas externas que quedaron sin resolver.

Usa OpenAlex, que resuelve nombre -> ISSN mejor que DOAJ pero tiene cuota
diaria gratuita: se agota con las ~324 consultas del catálogo argentino y
devuelve HTTP 429 el resto del día (resetea a medianoche UTC). Por eso este
paso corre por separado, y se detiene solo si la cuota vuelve a agotarse.

Con el ISSN obtenido re-verifica Scopus y SciELO y recalcula el nivel.
"""
import truststore
truststore.inject_into_ssl()

import re
import time
import logging
import requests

from database import (init_db, conectar, guardar_indizacion,
                      registrar_actualizacion)
from indizacion import cargar_scopus, normalizar_issn
from externas import cargar_scielo_red, PAISES, _tokens

logger = logging.getLogger(__name__)

from configuracion import HEADERS  # el correo de contacto no va en el código

OPENALEX = "https://api.openalex.org/sources"


def sin_issn():
    """Revistas externas sin ningún ISSN registrado."""
    conn = conectar()
    filas = conn.execute(
        """SELECT id, nombre, pais, sitio_url, indexacion_declarada FROM revistas
           WHERE origen='externa'
             AND COALESCE(issn_impreso,'')='' AND COALESCE(issn_online,'')=''
           ORDER BY nombre""").fetchall()
    conn.close()
    return [dict(f) for f in filas]


def consultar(sesion, nombre, pais):
    """Busca en OpenAlex. Devuelve (datos|None, agotada_la_cuota)."""
    params = {'search': nombre, 'per-page': 5}
    cc = PAISES.get(pais)
    if cc:
        params['filter'] = f'country_code:{cc}'

    for intento_params in (params, {'search': nombre, 'per-page': 5}):
        try:
            r = sesion.get(OPENALEX, params=intento_params, timeout=30)
        except requests.RequestException:
            return None, False
        if r.status_code == 429:
            return None, True
        if r.status_code != 200:
            continue
        try:
            resultados = r.json().get('results', [])
        except ValueError:
            continue

        objetivo = _tokens(nombre)
        mejor, punt = None, 0.0
        for it in resultados:
            otros = _tokens(it.get('display_name') or '')
            if not otros or not objetivo:
                continue
            s = len(objetivo & otros) / max(len(objetivo), len(otros))
            if s > punt:
                mejor, punt = it, s
        # Umbral alto: un ISSN equivocado afirma una indización que no existe.
        if mejor and punt >= 0.7:
            issns = mejor.get('issn') or []
            st = mejor.get('summary_stats') or {}
            return dict(
                nombre_openalex=mejor.get('display_name'), similitud=punt,
                issn_impreso=mejor.get('issn_l') or (issns[0] if issns else ''),
                issn_online=next((i for i in issns if i != mejor.get('issn_l')), ''),
                sitio_url=mejor.get('homepage_url') or '',
                en_doaj=1 if mejor.get('is_in_doaj') else 0,
                openalex_core=1 if mejor.get('is_core') else 0,
                h_index=st.get('h_index'), works_count=mejor.get('works_count')), False
        if cc is None:
            break
    return None, False


def completar(progreso=None):
    init_db()
    pendientes = sin_issn()
    if not pendientes:
        logger.info("No hay revistas sin ISSN.")
        return dict(pendientes=0, resueltas=0, cuota_agotada=False)

    logger.info("Revistas sin ISSN: %d", len(pendientes))
    scopus = cargar_scopus()
    scielo = cargar_scielo_red()

    sesion = requests.Session()
    sesion.headers.update(HEADERS)

    resumen = dict(pendientes=len(pendientes), resueltas=0, nivel1=0,
                   scopus=0, scielo=0, doaj=0, cuota_agotada=False, detalle=[])

    for i, rv in enumerate(pendientes, 1):
        datos, agotada = consultar(sesion, rv['nombre'], rv['pais'])
        if agotada:
            logger.warning("Cuota de OpenAlex agotada en la revista %d de %d. "
                           "Volvé a correr después de medianoche UTC.", i, len(pendientes))
            resumen['cuota_agotada'] = True
            break
        time.sleep(0.12)  # cortesía con la API pública
        if not datos:
            continue

        ns = [n for n in (normalizar_issn(datos['issn_impreso']),
                          normalizar_issn(datos['issn_online'])) if n]
        if not ns:
            continue

        estado_scopus = next((scopus[n] for n in ns if n in scopus), None)
        en_scopus = 1 if estado_scopus else 0
        en_scielo = 1 if any(n in scielo for n in ns) else 0
        sitio = rv['sitio_url'] or datos['sitio_url']
        if not en_scielo and 'scielo' in (sitio or '').lower():
            en_scielo = 1
        nivel = 1 if (en_scopus or en_scielo) else None

        conn = conectar()
        conn.execute(
            """UPDATE revistas SET issn_impreso=?, issn_online=?, sitio_url=?,
               resolucion=? WHERE id=?""",
            (datos['issn_impreso'], datos['issn_online'], sitio,
             f"OpenAlex: {datos['nombre_openalex']} (similitud {datos['similitud']:.2f})",
             rv['id']))
        conn.commit()
        conn.close()

        guardar_indizacion(rv['id'], dict(
            en_scopus=en_scopus, scopus_estado=estado_scopus, en_scielo=en_scielo,
            en_doaj=datos['en_doaj'], openalex_core=datos['openalex_core'],
            h_index=datos['h_index'], works_count=datos['works_count'],
            nivel_conicet=nivel))

        resumen['resueltas'] += 1
        resumen['scopus'] += en_scopus
        resumen['scielo'] += en_scielo
        resumen['doaj'] += datos['en_doaj']
        if nivel == 1:
            resumen['nivel1'] += 1
        resumen['detalle'].append(
            f"{rv['nombre']} -> ISSN {datos['issn_impreso'] or datos['issn_online']}"
            + (f" · Scopus({estado_scopus})" if en_scopus else "")
            + (" · SciELO" if en_scielo else ""))

        if progreso and i % 5 == 0:
            progreso(i, len(pendientes))

    registrar_actualizacion(
        "resolver_issn",
        f"{resumen['resueltas']}/{resumen['pendientes']} ISSN resueltos; "
        f"{resumen['nivel1']} pasaron a Nivel 1"
        + (" (cuota de OpenAlex agotada, quedan pendientes)"
           if resumen['cuota_agotada'] else ""))
    return resumen


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s',
                        handlers=[logging.FileHandler('actualizaciones.log',
                                                      encoding='utf-8'),
                                  logging.StreamHandler()])
    r = completar(progreso=lambda i, t: print(f"  {i}/{t}", flush=True))
    print("\nRESUMEN")
    for k in ('pendientes', 'resueltas', 'nivel1', 'scopus', 'scielo', 'doaj',
              'cuota_agotada'):
        print(f"  {k}: {r[k]}")
    for d in r.get('detalle', [])[:40]:
        print("   ·", d)
