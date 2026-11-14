"""Fusión de revistas duplicadas, sobre una base temporal."""
import pytest

import database
import fusionar_duplicados as fd


@pytest.fixture
def base(tmp_path, monkeypatch):
    monkeypatch.setattr(database, 'DB_PATH', tmp_path / 't.db')
    database.init_db()
    conn = database.conectar()

    def alta(nombre, pais, origen, issn=None):
        conn.execute(
            "INSERT INTO revistas(nombre, pais, origen, issn_online, sitio_url)"
            " VALUES (?,?,?,?, 'https://x.test/')", (nombre, pais, origen, issn))
    alta('Psicoperspectivas', 'Chile', 'externa', '0718-6924')
    alta('Psicoperspectivas. Individuo y Sociedad', 'Chile', 'NBRA', '0718-6924')
    alta('Revista RAAB (En línea)', 'Argentina', 'NBRA')
    alta('Revista raab', 'Argentina', 'externa')
    alta('Palabra Clave', 'Colombia', 'externa', '1111-1111')
    alta('Palabra clave', 'Argentina', 'NBRA', '2222-2222')
    conn.commit()
    conn.close()


def _pares():
    grupos, _ = fd.detectar()
    return {(c['nombre'], d['nombre']) for c, ds in grupos for d in ds}


def test_fusiona_issn_con_subtitulo(base):
    assert ('Psicoperspectivas. Individuo y Sociedad',
            'Psicoperspectivas') in _pares()


def test_fusiona_mismo_nombre_y_pais(base):
    assert ('Revista RAAB (En línea)', 'Revista raab') in _pares()


def test_no_fusiona_mismo_nombre_en_paises_distintos(base):
    assert not any('Palabra' in a for a, _ in _pares())
