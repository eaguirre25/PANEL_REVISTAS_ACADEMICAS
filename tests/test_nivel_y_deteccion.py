"""Nivel CONICET según origen y memoria de la primera detección."""
import deteccion
from indizacion import nivel_conicet


def test_nbra_tiene_piso_nivel_2():
    assert nivel_conicet(0, 0, 'NBRA') == 2


def test_externa_sin_indices_queda_sin_nivel():
    assert nivel_conicet(0, 0, 'externa') is None


def test_scopus_o_scielo_dan_nivel_1_sin_importar_origen():
    for origen in ('NBRA', 'externa'):
        assert nivel_conicet(1, 0, origen) == 1
        assert nivel_conicet(0, 1, origen) == 1


def test_deteccion_conserva_primera_fecha(tmp_path, monkeypatch):
    monkeypatch.setattr(deteccion, 'RUTA', str(tmp_path / 'mem.json'))
    deteccion.guardar({deteccion.clave('Rev A', 'Convocatoria 1'):
                       '2026-08-03 20:57:10'})
    convs = [
        {'revista': 'REV A', 'titulo': ' convocatoria 1 ',
         'fecha_encontrada': '2026-11-16 09:00:00'},
        {'revista': 'Rev B', 'titulo': 'Nueva',
         'fecha_encontrada': '2026-11-16 09:00:00'},
    ]
    deteccion.aplicar(convs, persistir=True)
    assert convs[0]['fecha_encontrada'] == '2026-08-03 20:57:10'
    assert convs[1]['fecha_encontrada'] == '2026-11-16 09:00:00'
    # lo nuevo quedó guardado para la próxima corrida
    assert deteccion.cargar()[deteccion.clave('Rev B', 'Nueva')] == \
        '2026-11-16 09:00:00'


def test_deteccion_solo_lectura_no_escribe(tmp_path, monkeypatch):
    ruta = tmp_path / 'mem.json'
    monkeypatch.setattr(deteccion, 'RUTA', str(ruta))
    deteccion.aplicar([{'revista': 'X', 'titulo': 'Y',
                        'fecha_encontrada': '2026-11-16 09:00:00'}])
    assert not ruta.exists()
