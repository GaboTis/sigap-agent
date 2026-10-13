"""Tests del módulo sitio_municipal (WordPress REST del municipio)."""
from unittest.mock import patch

import httpx

from app import sitio_municipal


class _Resp:
    def __init__(self, datos):
        self._d = datos

    def json(self):
        return self._d

    def raise_for_status(self):
        pass


_POST = {'id': 1, 'date': '2026-09-25T15:54:49',
         'link': 'https://municipioderawson.gob.ar/2026/09/25/nota/',
         'title': {'rendered': '<p>Nueva <b>obra</b></p>'},
         'excerpt': {'rendered': '<p>Resumen de la nota</p>'}}


def test_ultimas_noticias():
    with patch.object(sitio_municipal, '_get', return_value=[_POST]):
        r = sitio_municipal.ultimas_noticias(3)
    assert r['total'] == 1
    assert r['noticias'][0]['titulo'] == 'Nueva obra'
    assert r['noticias'][0]['fecha'] == '2026-09-25'
    assert 'Resumen de la nota' in r['noticias'][0]['resumen']


def test_ultimas_noticias_error():
    with patch.object(sitio_municipal, '_get', side_effect=httpx.ConnectError('caído')):
        r = sitio_municipal.ultimas_noticias()
    assert 'error' in r


def test_buscar_sitio_deduplica():
    tramite = {'title': {'rendered': 'Moratoria'}, 'link': 'https://x/t/1', 'date': '2026-01-01'}
    ga = {'title': {'rendered': 'Licitacion Publica N15'}, 'link': 'https://ga/x/2',
          'subtype': 'docs', 'date': '2026-02-02'}
    with patch.object(sitio_municipal, '_get', side_effect=[[], [tramite], [ga]]):
        r = sitio_municipal.buscar_sitio('licitacion', 5)
    assert r['total'] == 2
    tipos = {x['titulo']: x['tipo'] for x in r['resultados']}
    assert 'trámite' in tipos['Moratoria']
    assert 'gobierno abierto' in tipos['Licitacion Publica N15']


def test_buscar_sitio_sin_consulta():
    r = sitio_municipal.buscar_sitio('   ')
    assert 'error' in r


def test_licitaciones():
    datos = [{'title': {'rendered': 'Licitacion Publica N15/2026'},
              'link': 'https://ga/l15', 'date': '2026-09-01'}]
    with patch.object(sitio_municipal, '_get', return_value=datos):
        r = sitio_municipal.licitaciones(3)
    assert r['total'] == 1
    assert 'N15/2026' in r['licitaciones'][0]['titulo']


def test_guia_tramites():
    class _Resp:
        text = ('<a href="https://municipioderawson.gob.ar/tramite/habilitaciones-comercio-e-industria/">'
                '<img src="x.png"> Habilitaciones Comerciales </a>'
                '<a href="https://municipioderawson.gob.ar/tramite/libre-deuda/">Libre Deuda</a>')

        def raise_for_status(self):
            pass

    with patch.object(sitio_municipal.httpx, 'get', return_value=_Resp()):
        r = sitio_municipal.guia_tramites(5)
    assert r['total'] == 2
    assert r['tramites'][0]['titulo'] == 'Habilitaciones Comerciales'
    assert 'tramite/libre-deuda' in r['tramites'][1]['enlace']


def test_limpiar_html():
    assert sitio_municipal._limpiar('<b>Hola</b>   mundo &amp; más') == 'Hola mundo & más'
