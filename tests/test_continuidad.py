"""Arrastre de convocatorias previas cuando el sitio de la revista no responde."""
from datetime import date

import continuidad

HOY = date(2026, 11, 16)


def _conv(**kw):
    base = dict(revista='Rev A', titulo='Dossier X', fecha_cierre='2026-12-20',
                fuente='OJS/announcement', ultima_revision_ok='2026-11-09 09:00:00',
                fecha_encontrada='2026-10-01 09:00:00')
    base.update(kw)
    return base


def _rev(estado, nombre='Rev A'):
    return [{'nombre': nombre, 'estado_chequeo': estado}]


def test_arrastra_si_el_sitio_no_respondio():
    actuales = []
    ag = continuidad.arrastrar([_conv()], actuales, _rev('http 403'), HOY)
    assert len(ag) == 1 and actuales[0]['arrastrada'] == 1
    assert actuales[0]['estado_chequeo'] == 'http 403'
    # conserva la última lectura correcta, para que la tarjeta la muestre
    assert actuales[0]['ultima_revision_ok'] == '2026-11-09 09:00:00'


def test_no_arrastra_si_se_leyo_bien():
    for estado in ('ok', 'sin convocatorias', 'sin pagina de anuncios'):
        assert continuidad.arrastrar([_conv()], [], _rev(estado), HOY) == []


def test_no_arrastra_vencidas():
    c = _conv(fecha_cierre='2026-11-01')
    assert continuidad.arrastrar([c], [], _rev('http 403'), HOY) == []


def test_no_arrastra_si_la_lectura_es_muy_vieja():
    c = _conv(ultima_revision_ok='2026-08-01 09:00:00')
    assert continuidad.arrastrar([c], [], _rev('http 403'), HOY) == []


def test_sin_fecha_de_referencia_no_se_arrastra():
    c = _conv(ultima_revision_ok=None, fecha_encontrada=None)
    assert continuidad.arrastrar([c], [], _rev('http 403'), HOY) == []


def test_no_duplica_ni_arrastra_manuales_ni_revistas_ausentes():
    ya = [_conv(titulo='  dossier x ')]
    assert continuidad.arrastrar([_conv()], ya, _rev('http 403'), HOY) == []
    assert continuidad.arrastrar([_conv(fuente='manual · x')], [],
                                 _rev('http 403'), HOY) == []
    assert continuidad.arrastrar([_conv()], [], _rev('http 403', 'Otra'), HOY) == []


def test_una_revista_nunca_leida_se_trata_como_no_leida():
    ag = continuidad.arrastrar([_conv()], [], _rev(None), HOY)
    assert len(ag) == 1 and ag[0]['estado_chequeo'] == 'no revisada'


def test_publicado_ausente_o_corrupto(tmp_path):
    assert continuidad.cargar_publicado(str(tmp_path / 'no_existe.json')) == []
    roto = tmp_path / 'roto.json'
    roto.write_text('{no es json', encoding='utf-8')
    assert continuidad.cargar_publicado(str(roto)) == []
