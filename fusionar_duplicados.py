"""
Fusiona revistas duplicadas que quedaron con el mismo ISSN bajo distinto nombre.

Pasa cuando el mismo título entra por dos vías: el NBRA lo registra con el
sufijo institucional completo y un listado externo, sin él. El ISSN delata que
son la misma publicación.

Se conserva la fila del NBRA (tiene la ficha oficial de CAICYT) y se le pasan
los datos que solo tenía la otra: sitio web, país, ISSN faltante, recepción
permanente y sus convocatorias.
"""
import re
import logging
from database import init_db, conectar, registrar_actualizacion

logger = logging.getLogger(__name__)


def _norm(i):
    n = re.sub(r'[^0-9Xx]', '', str(i or '')).upper()
    return n if len(n) == 8 else ''


def detectar():
    """Grupos de ids que comparten ISSN. Devuelve [(conservar, [descartar…])]."""
    conn = conectar()
    filas = conn.execute(
        """SELECT id, nombre, origen, issn_impreso, issn_online, sitio_url,
                  ficha_url, pais, recepcion_permanente, evidencia_permanente
           FROM revistas ORDER BY id""").fetchall()
    conn.close()

    por_issn = {}
    for f in filas:
        for i in (f['issn_impreso'], f['issn_online']):
            n = _norm(i)
            if n:
                por_issn.setdefault(n, []).append(dict(f))

    grupos, sospechosos, vistos = [], [], set()
    for issn, rs in por_issn.items():
        ids = tuple(sorted({r['id'] for r in rs}))
        if len(ids) < 2 or ids in vistos:
            continue
        vistos.add(ids)
        # Se conserva la del NBRA; si ninguna lo es, la más antigua.
        nbra = [r for r in rs if (r['origen'] or 'NBRA') == 'NBRA']
        conservar = (nbra or sorted(rs, key=lambda r: r['id']))[0]
        descartar = [r for r in rs if r['id'] != conservar['id']]

        # Compartir ISSN no siempre significa ser la misma revista: puede ser
        # un ISSN mal asignado. Si los títulos no se parecen, no se fusiona
        # —unir dos revistas distintas destruye datos— y se reporta aparte.
        for d in descartar:
            if _parecidos(conservar['nombre'], d['nombre']):
                grupos.append((conservar, [d]))
            else:
                sospechosos.append((issn, conservar, d))
    # Segunda vía: mismo nombre normalizado y mismo país, aunque el ISSN falte
    # o difiera (la misma revista con su ISSN impreso en una fila y el online
    # en otra). Nombres iguales en países distintos NO se tocan: «Palabra
    # clave» de Colombia y la de Argentina son revistas diferentes.
    ya = {r['id'] for _, ds in grupos for r in ds} | {g['id'] for g, _ in grupos}
    por_nombre = {}
    for f in filas:
        r = dict(f)
        if r['id'] in ya:
            continue
        k = (_nombre_norm(r['nombre']), _pais_base(r['pais']))
        if k[0]:
            por_nombre.setdefault(k, []).append(r)
    for rs in por_nombre.values():
        if len(rs) < 2:
            continue
        nbra = [r for r in rs if (r['origen'] or 'NBRA') == 'NBRA']
        conservar = (nbra or sorted(rs, key=lambda r: r['id']))[0]
        issn_c = {_norm(conservar['issn_impreso']), _norm(conservar['issn_online'])} - {''}
        for d in rs:
            if d['id'] == conservar['id']:
                continue
            issn_d = {_norm(d['issn_impreso']), _norm(d['issn_online'])} - {''}
            # Si ambas filas traen ISSN y no comparten ninguno, son revistas
            # distintas con el mismo título («Fronteiras» de Anápolis y la de
            # la UFFS): no se fusionan, se reportan para revisión manual.
            if issn_c and issn_d and not (issn_c & issn_d):
                sospechosos.append(('; '.join(sorted(issn_c | issn_d)), conservar, d))
            else:
                grupos.append((conservar, [d]))
    return grupos, sospechosos


def _sin_acentos(s):
    s = (s or '').lower()
    for x, y in zip("áéíóúàãâêôõçñü", "aeiouaaaeoocnu"):
        s = s.replace(x, y)
    return s


def _nombre_norm(s):
    """Nombre sin mayúsculas, acentos ni paréntesis: «Crítica y Resistencias
    (En línea)» y «Crítica y resistencias» dan lo mismo."""
    s = re.sub(r'\([^)]*\)', ' ', _sin_acentos(s))
    return ' '.join(re.sub(r'[^a-z0-9 ]', ' ', s).split())


def _pais_base(p):
    """'Argentina/regional' -> 'argentina'."""
    return _sin_acentos((p or '').split('/')[0]).strip()


def _parecidos(a, b, umbral=0.45):
    """
    Similitud laxa de títulos, sin acentos ni palabras vacías.

    Con ISSN compartido también vale la contención: «Psicoperspectivas» está
    dentro de «Psicoperspectivas. Individuo y Sociedad», que es la misma
    revista con el subtítulo.
    """
    def tok(s):
        vacias = {'revista', 'de', 'del', 'la', 'el', 'los', 'las', 'y', 'en',
                  'linea', 'journal', 'da', 'do'}
        return {t for t in re.sub(r'[^a-z0-9 ]', ' ', _sin_acentos(s)).split()
                if t and t not in vacias}
    ta, tb = tok(a), tok(b)
    if not ta or not tb:
        return False
    if ta <= tb or tb <= ta:
        return True
    return len(ta & tb) / max(len(ta), len(tb)) >= umbral


def fusionar(aplicar=True):
    init_db()
    grupos, sospechosos = detectar()
    if not grupos and not sospechosos:
        logger.info("No hay duplicados por ISSN.")
        return dict(grupos=0, fusionadas=0, detalle=[], sospechosos=[])

    conn = conectar()
    detalle, fusionadas = [], 0

    for conservar, descartar in grupos:
        for d in descartar:
            detalle.append(f"{d['nombre']}  ->  {conservar['nombre']}")
            if not aplicar:
                continue
            # El sitio del listado externo suele ser el de la revista; el del
            # NBRA a veces apunta a SciELO. Se prefiere el que no sea SciELO.
            sitio = conservar['sitio_url'] or ''
            if d['sitio_url'] and ('scielo' in sitio.lower() or not sitio):
                sitio = d['sitio_url']
            conn.execute(
                """UPDATE revistas SET
                     sitio_url = ?,
                     pais = COALESCE(pais, ?),
                     issn_impreso = CASE WHEN COALESCE(issn_impreso,'')=''
                                         THEN ? ELSE issn_impreso END,
                     issn_online = CASE WHEN COALESCE(issn_online,'')=''
                                        THEN ? ELSE issn_online END,
                     recepcion_permanente = COALESCE(
                        NULLIF(recepcion_permanente,0), ?),
                     evidencia_permanente = COALESCE(
                        NULLIF(evidencia_permanente,''), ?)
                   WHERE id = ?""",
                (sitio, d['pais'], d['issn_impreso'], d['issn_online'],
                 d['recepcion_permanente'], d['evidencia_permanente'],
                 conservar['id']))
            # Las convocatorias de la descartada pasan a la que se conserva;
            # las que ya existan en el destino se descartan por la restricción.
            for c in conn.execute(
                    "SELECT * FROM convocatorias WHERE revista_id = ?",
                    (d['id'],)).fetchall():
                try:
                    conn.execute(
                        """INSERT INTO convocatorias
                           (revista_id, titulo, descripcion, fecha_cierre, url,
                            fuente, tipo, es_dossier, tema, activa,
                            fecha_reapertura, sigue_recibiendo,
                            fecha_encontrada)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (conservar['id'], c['titulo'], c['descripcion'],
                         c['fecha_cierre'], c['url'], c['fuente'], c['tipo'],
                         c['es_dossier'], c['tema'], c['activa'],
                         c['fecha_reapertura'], c['sigue_recibiendo'],
                         c['fecha_encontrada']))
                except Exception:
                    pass
            conn.execute("DELETE FROM convocatorias WHERE revista_id = ?", (d['id'],))
            conn.execute("DELETE FROM revistas WHERE id = ?", (d['id'],))
            fusionadas += 1

    avisos = [f"ISSN {i} compartido por «{c['nombre']}» y «{d['nombre']}»: "
              "títulos distintos, NO se fusionan; revisar cuál lo tiene mal"
              for i, c, d in sospechosos]
    for a in avisos:
        logger.warning(a)

    if aplicar:
        conn.commit()
        registrar_actualizacion(
            "fusion",
            f"{fusionadas} revistas duplicadas fusionadas por ISSN"
            + (f"; {len(avisos)} coincidencias sospechosas sin fusionar"
               if avisos else ""))
    conn.close()
    return dict(grupos=len(grupos), fusionadas=fusionadas, detalle=detalle,
                sospechosos=avisos)


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
    solo_ver = '--ver' in sys.argv
    r = fusionar(aplicar=not solo_ver)
    print(("A FUSIONAR" if solo_ver else "FUSIONADAS") + f": {r['fusionadas']}")
    for d in r['detalle']:
        print("  ", d)
    if r['sospechosos']:
        print(f"\nSOSPECHOSAS ({len(r['sospechosos'])}) - requieren revisión:")
        for s in r['sospechosos']:
            print("  ", s)
