"""Extracción de fechas, dossiers y temas en español, portugués e inglés.

Las fechas futuras usan el año 2099 para que las pruebas no caduquen.
"""
import pytest

from convocatorias import (ES_DOSSIER, PALABRAS_CLAVE, extraer_fecha,
                           extraer_tema, parece_vieja)


@pytest.mark.parametrize('texto, esperada', [
    ('Fecha límite: 15 de marzo de 2099', '2099-03-15'),
    ('Recepción hasta el 31/12/2099', '2099-12-31'),
    ('Cierre 2099-06-30', '2099-06-30'),
    # Portugués (213 revistas del catálogo son de Brasil)
    ('Prazo para submissão: 15 de março de 2099', '2099-03-15'),
    ('Submissões até 30 de setembro de 2099', '2099-09-30'),
    ('Data limite: 1 de dezembro de 2099', '2099-12-01'),
    # Inglés
    ('Deadline: March 15, 2099', '2099-03-15'),
    ('Submission deadline 15 March 2099', '2099-03-15'),
    ('Due by October 3rd, 2099', '2099-10-03'),
])
def test_extrae_fecha_en_tres_idiomas(texto, esperada):
    assert extraer_fecha(texto) == esperada


def test_fecha_pasada_no_se_devuelve():
    assert extraer_fecha('Prazo: 15 de março de 2001') is None
    assert extraer_fecha('Deadline: March 15, 2001') is None


def test_sin_anio_no_se_inventa():
    assert extraer_fecha('Cierra el 15 de marzo') is None


def test_prioriza_la_fecha_con_contexto_de_plazo():
    texto = ('Publicação prevista: 01 de março de 2099. '
             'Prazo para submissão: 15 de dezembro de 2099.')
    assert extraer_fecha(texto) == '2099-12-15'


def test_mes_invalido_no_rompe():
    assert extraer_fecha('Prazo: 31 de fevereiro de 2099') is None


@pytest.mark.parametrize('titulo', [
    'Chamada para submissão de artigos',
    'Convocatoria abierta',
    'Call for papers: special issue',
    'Edição especial sobre educação',
])
def test_palabras_clave(titulo):
    assert PALABRAS_CLAVE.search(titulo)


@pytest.mark.parametrize('texto', [
    'Dossiê temático: Educação e democracia',
    'Chamada para o dossiê sobre infâncias',
    'Dossier: Políticas educativas',
    'Edição especial 2099',
])
def test_detecta_dossier(texto):
    assert ES_DOSSIER.search(texto)


def test_no_es_dossier():
    assert not ES_DOSSIER.search('Aviso de mantenimiento del sitio')


def test_tema_de_dossie_entrecomillado():
    tema = extraer_tema('Chamada para o dossiê',
                        'Chamada para o dossiê "Educação e democracia no Brasil"')
    assert tema == 'Educação e democracia no Brasil'


def test_parece_vieja():
    assert parece_vieja('Convocatoria 2001')
    assert not parece_vieja('Convocatoria 2099')
    assert not parece_vieja('Convocatoria abierta')
