"""
Memoria de la primera detección de cada convocatoria.

Por qué existe: las corridas de GitHub Actions reconstruyen la base desde cero
(la base SQLite no se versiona porque contiene correos de suscriptores). Sin
memoria, `fecha_encontrada` vale siempre la fecha de la corrida, y entonces
TODAS las convocatorias salen como «Nueva» en el sitio y como «nuevas de la
semana» en el boletín.

Acá se guarda, en un JSON versionado, la primera vez que se vio cada
convocatoria. La clave es revista + título (en minúsculas), la misma identidad
que usa la base (UNIQUE(revista_id, titulo)).

Las entradas sembradas al crear el archivo llevan la fecha de la línea de
base: de ellas no se sabe cuándo aparecieron realmente, así que no pueden
figurar como nuevas (ver `_linea_base` en generar_sitio.py).
"""
import json
import os
from datetime import datetime

RUTA = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    'primera_deteccion.json')


def clave(revista, titulo):
    return f"{(revista or '').strip().lower()}||{(titulo or '').strip().lower()}"


def cargar():
    try:
        with open(RUTA, encoding='utf-8') as f:
            datos = json.load(f)
        return datos if isinstance(datos, dict) else {}
    except (OSError, ValueError):
        return {}


def guardar(memoria):
    with open(RUTA, 'w', encoding='utf-8') as f:
        json.dump(memoria, f, ensure_ascii=False, indent=0, sort_keys=True)
        f.write('\n')


def aplicar(convocatorias, persistir=False):
    """
    Reemplaza `fecha_encontrada` por la primera detección registrada.

    Las convocatorias que no estaban en la memoria conservan la fecha que
    trae la base (la de esta corrida) y se agregan a la memoria. Con
    `persistir=True` se escribe el archivo; el boletín solo lee.
    """
    memoria = cargar()
    hubo_cambios = False
    ahora = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    for c in convocatorias:
        k = clave(c.get('revista'), c.get('titulo'))
        if k in memoria:
            c['fecha_encontrada'] = memoria[k]
        else:
            memoria[k] = str(c.get('fecha_encontrada') or ahora)[:19]
            hubo_cambios = True
    if persistir and hubo_cambios:
        guardar(memoria)
    return memoria
