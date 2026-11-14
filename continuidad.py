"""
Continuidad entre corridas: no perder lo ya detectado cuando un sitio falla.

CI reconstruye la base desde cero cada semana. Si una revista no respondió
esta vez (servidor caído, bloqueo, tiempo agotado), sus convocatorias de la
semana pasada desaparecerían del panel aunque siguieran vigentes. Acá se
arrastran desde la publicación anterior (docs/datos.json) mientras:

  - la revista siga en el catálogo y hoy NO se haya podido leer,
  - la convocatoria no esté vencida,
  - la última lectura correcta de esa revista no sea más vieja que MAX_DIAS.

Se marcan con `arrastrada = 1` y conservan su `ultima_revision_ok`: la tarjeta
ya muestra «la fuente no respondió en la última revisión · última lectura
correcta: …», así que nadie ve un dato viejo como si fuera fresco.
"""
import json
import os
from datetime import date, datetime

import deteccion

RUTA_PUBLICADO = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              'docs', 'datos.json')

# Estados de una lectura que SÍ se pudo hacer (coincide con generar_sitio).
LEIDA_OK = {'ok', 'sin convocatorias', 'sin pagina de anuncios'}
MAX_DIAS = 60


def cargar_datos_publicados(ruta=None):
    """Todo el datos.json publicado; {} si no hay o no se puede leer."""
    try:
        with open(ruta or RUTA_PUBLICADO, encoding='utf-8') as f:
            datos = json.load(f)
        return datos if isinstance(datos, dict) else {}
    except (OSError, ValueError):
        return {}


def cargar_publicado(ruta=None):
    """Convocatorias de la publicación anterior; [] si no hay o no se lee."""
    return list(cargar_datos_publicados(ruta).get('convocatorias') or [])


def _fecha(valor):
    try:
        return datetime.strptime(str(valor)[:10], '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return None


def arrastrar(previas, actuales, revistas, hoy=None, max_dias=MAX_DIAS):
    """
    Agrega a `actuales` las convocatorias previas de revistas no leídas hoy.
    Devuelve la lista de las agregadas.
    """
    hoy = hoy or date.today()
    estado = {(r.get('nombre') or '').strip().lower(): r.get('estado_chequeo')
              for r in revistas}
    vistas = {deteccion.clave(c.get('revista'), c.get('titulo'))
              for c in actuales}
    agregadas = []

    for p in previas:
        nombre = (p.get('revista') or '').strip().lower()
        if nombre not in estado:
            continue                      # la revista ya no está en el catálogo
        if estado[nombre] in LEIDA_OK:
            continue                      # se leyó bien: manda lo de hoy
        if str(p.get('fuente') or '').startswith('manual'):
            continue                      # lo manual se vuelve a cargar solo
        k = deteccion.clave(p.get('revista'), p.get('titulo'))
        if k in vistas:
            continue
        cierre = _fecha(p.get('fecha_cierre'))
        if cierre and cierre < hoy:
            continue                      # vencida
        ref = _fecha(p.get('ultima_revision_ok')) or _fecha(p.get('fecha_encontrada'))
        if ref is None or (hoy - ref).days > max_dias:
            continue                      # demasiado vieja para seguir mostrándola
        nueva = dict(p)
        nueva['arrastrada'] = 1
        nueva['estado_chequeo'] = estado[nombre] or 'no revisada'
        actuales.append(nueva)
        agregadas.append(nueva)
        vistas.add(k)
    return agregadas
