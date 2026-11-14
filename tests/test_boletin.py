"""El boletín en CI lee lo publicado y no marca todo como «nuevo»."""
import json
from datetime import date, datetime, timedelta

import boletin
import continuidad
import deteccion


def test_boletin_lee_lo_publicado(tmp_path, monkeypatch):
    hoy = date.today()
    ahora = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    vieja = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d %H:%M:%S')
    publicado = {
        'estadisticas': {'permanentes': 98},
        'convocatorias': [
            {'revista': 'A', 'titulo': 'Por vencer', 'fecha_cierre':
             (hoy + timedelta(days=3)).isoformat(), 'fecha_encontrada': vieja},
            {'revista': 'B', 'titulo': 'Nueva de hoy', 'fecha_cierre': None,
             'fecha_encontrada': ahora},
            {'revista': 'C', 'titulo': 'Vencida', 'fecha_cierre':
             (hoy - timedelta(days=2)).isoformat(), 'fecha_encontrada': vieja},
        ],
    }
    ruta = tmp_path / 'datos.json'
    ruta.write_text(json.dumps(publicado), encoding='utf-8')
    monkeypatch.setattr(continuidad, 'RUTA_PUBLICADO', str(ruta))
    monkeypatch.setattr(deteccion, 'RUTA', str(tmp_path / 'mem.json'))
    monkeypatch.setenv('BOLETIN_FUENTE', 'publicado')

    por_vencer, nuevas, permanentes = boletin.reunir()

    assert [c['titulo'] for _, c in por_vencer] == ['Por vencer']
    assert [c['titulo'] for c in nuevas] == ['Nueva de hoy']   # no todas
    assert permanentes == 98
