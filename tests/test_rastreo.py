"""Reintentos y respaldo desde la portada, con una sesión simulada."""
import pytest
import requests

import convocatorias as cv


class Resp:
    def __init__(self, status=200, html='', url='https://rev.test/x'):
        self.status_code, self.text, self.url = status, html, url
        self.content = html.encode('utf-8')


class Sesion:
    """Devuelve (o lanza) lo que se le indique, en orden, por URL."""
    def __init__(self, guion):
        self.guion = {u: list(v) for u, v in guion.items()}
        self.pedidos = []

    def get(self, url, **kw):
        self.pedidos.append(url)
        item = self.guion[url].pop(0) if len(self.guion[url]) > 1 \
            else self.guion[url][0]
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture(autouse=True)
def sin_esperas(monkeypatch):
    monkeypatch.setattr(cv.time, 'sleep', lambda s: None)


def test_reintenta_un_timeout_pasajero():
    u = 'https://rev.test/announcement'
    s = Sesion({u: [requests.ReadTimeout(), Resp(200, 'ok', u)]})
    assert cv._get(s, u).status_code == 200
    assert len(s.pedidos) == 2


def test_reintenta_un_503_pasajero():
    u = 'https://rev.test/announcement'
    s = Sesion({u: [Resp(503), Resp(200, 'ok', u)]})
    assert cv._get(s, u).status_code == 200


def test_error_ssl_no_se_reintenta():
    u = 'https://rev.test/announcement'
    s = Sesion({u: [requests.exceptions.SSLError()]})
    with pytest.raises(requests.exceptions.SSLError):
        cv._get(s, u)
    assert len(s.pedidos) == 1


def test_timeout_persistente_termina_y_lanza():
    u = 'https://rev.test/announcement'
    s = Sesion({u: [requests.ConnectTimeout()]})
    with pytest.raises(requests.Timeout):
        cv._get(s, u)
    assert len(s.pedidos) == cv.REINTENTOS + 1


def test_404_con_enlace_en_portada_lee_los_avisos():
    portada = ('<html><body><a href="/avisos/announcement">Convocatorias</a>'
               '</body></html>')
    avisos = ('<html><body><div class="announcement-summary"><h3>'
              '<a href="/avisos/announcement/view/7">Chamada para dossiê '
              'temático 2099</a></h3><p>Prazo: 15 de março de 2099</p>'
              '</div></body></html>')
    s = Sesion({
        'https://rev.test/announcement': [Resp(404, '', 'https://rev.test/announcement')],
        'https://rev.test/': [Resp(200, portada, 'https://rev.test/')],
        'https://rev.test/avisos/announcement': [Resp(200, avisos, 'https://rev.test/avisos/announcement')],
        'https://rev.test/avisos/announcement/view/7': [Resp(200, avisos)],
    })
    estado, convs = cv.revisar_revista(s, {'sitio_url': 'https://rev.test/'})
    assert estado == 'ok' and len(convs) == 1
    assert convs[0]['fecha_cierre'] == '2099-03-15' and convs[0]['es_dossier']


def test_404_sin_enlace_sigue_siendo_sin_pagina():
    s = Sesion({
        'https://rev.test/announcement': [Resp(404, '', 'https://rev.test/announcement')],
        'https://rev.test/': [Resp(200, '<a href="/about">Acerca</a>', 'https://rev.test/')],
    })
    assert cv.revisar_revista(s, {'sitio_url': 'https://rev.test/'}) == \
        ('sin pagina de anuncios', [])


def test_no_sigue_enlaces_de_otro_dominio():
    portada = '<a href="https://otro.test/announcement">Convocatorias</a>'
    s = Sesion({
        'https://rev.test/announcement': [Resp(404, '', 'https://rev.test/announcement')],
        'https://rev.test/': [Resp(200, portada, 'https://rev.test/')],
    })
    assert cv.revisar_revista(s, {'sitio_url': 'https://rev.test/'})[0] == \
        'sin pagina de anuncios'


def test_catalogo_siembra_desde_publicado_si_caicyt_cae(tmp_path, monkeypatch):
    import json, database, catalogo, continuidad
    monkeypatch.setattr(database, 'DB_PATH', tmp_path / 'c.db')
    database.init_db()
    monkeypatch.setattr(continuidad, 'cargar_datos_publicados', lambda ruta=None: {
        'revistas': [{'nombre': 'Rev A', 'origen': 'NBRA', 'sitio_url': 'https://a.test/'},
                     {'nombre': 'Rev B', 'origen': 'externa'}]})
    monkeypatch.setattr(catalogo, 'listar_fichas',
                        lambda s: (_ for _ in ()).throw(RuntimeError('500')))
    r = catalogo.actualizar_catalogo()
    assert r['guardadas'] == 1 and r['desde_publicado']
    nombres = [x['nombre'] for x in database.conectar().execute('SELECT nombre FROM revistas')]
    assert nombres == ['Rev A']
