"""Sitio oficial del municipio — municipioderawson.gob.ar (WordPress REST).

Herramientas en vivo para noticias, guía de trámites y búsqueda en el sitio.
La información estática (autoridades, contacto) vive en datos_municipio/ y se
actualiza con scripts/actualizar_sitio.py.
"""
import html
import re

import httpx

SITIO = 'https://municipioderawson.gob.ar'
GOBIERNO_ABIERTO = 'https://gobiernoabierto.municipioderawson.gob.ar'
_API = f'{SITIO}/wp-json/wp/v2'
_API_GA = f'{GOBIERNO_ABIERTO}/wp-json/wp/v2'
_TIMEOUT = 25
_UA = {'User-Agent': 'ExpertoSIGAP-Rawson/1.0 (asistente municipal)'}


def _limpiar(texto):
    """Quita HTML y normaliza espacios."""
    t = re.sub(r'<[^>]+>', ' ', html.unescape(str(texto or '')))
    return ' '.join(t.split())


def _titulo(d):
    """Título de un resultado WP: string plano (Gobierno Abierto) u objeto rendered."""
    t = d.get('title', '')
    if isinstance(t, dict):
        t = t.get('rendered', '')
    return _limpiar(t)


def _get(ruta, params=None):
    resp = httpx.get(ruta, params=params or {}, headers=_UA, timeout=_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def ultimas_noticias(n=5):
    """Últimas noticias publicadas en el sitio oficial."""
    n = max(1, min(int(n or 5), 10))
    try:
        datos = _get(f'{_API}/posts', {'per_page': n * 2, 'orderby': 'date', 'order': 'desc'})
    except (httpx.HTTPError, ValueError) as e:
        return {'error': f'No se pudo consultar el sitio municipal: {str(e)[:150]}'}
    if not isinstance(datos, list):
        return {'error': 'El sitio municipal devolvió una respuesta inesperada.'}
    noticias = []
    for d in datos:
        titulo = _titulo(d)
        # Filtrar entradas placeholder (títulos numéricos o vacíos)
        if len(titulo) < 5 or titulo.isdigit():
            continue
        noticias.append({
            'titulo': titulo,
            'fecha': (d.get('date') or '')[:10],
            'enlace': d.get('link', ''),
            'resumen': _limpiar(d.get('excerpt', {}).get('rendered'))[:300],
        })
        if len(noticias) >= n:
            break
    return {'total': len(noticias), 'noticias': noticias}


def buscar_sitio(consulta, n=6):
    """Busca en el sitio oficial (noticias, páginas, trámites) y en Gobierno Abierto
    (licitaciones, boletín oficial, normativa)."""
    consulta = (consulta or '').strip()
    if not consulta:
        return {'error': 'Indicá qué querés buscar en el sitio municipal.'}
    n = max(1, min(int(n or 6), 10))
    resultados = []

    def _colectar(datos, tipo_base, usar_link=True):
        if not isinstance(datos, list):
            return
        for d in datos:
            titulo = _titulo(d)
            if not titulo or titulo.isdigit():
                continue
            resultados.append({
                'titulo': titulo,
                'tipo': tipo_base,
                'enlace': d.get('link') or d.get('url', ''),
                'fecha': (d.get('date') or '')[:10],
            })

    # Sitio principal: búsqueda general (con tolerancia a fallos por endpoint)
    try:
        _colectar(_get(f'{_API}/search',
                       {'search': consulta, 'per_page': n, 'orderby': 'relevance'}),
                  'contenido')
    except (httpx.HTTPError, ValueError):
        pass
    try:
        _colectar(_get(f'{_API}/tramite', {'search': consulta, 'per_page': n}),
                  'trámite')
    except (httpx.HTTPError, ValueError):
        pass
    # Gobierno Abierto: licitaciones, boletín oficial, normativa
    try:
        datos_ga = _get(f'{_API_GA}/search',
                        {'search': consulta, 'per_page': n, 'orderby': 'relevance'})
        if isinstance(datos_ga, list):
            for d in datos_ga:
                titulo = _titulo(d)
                if not titulo or titulo.isdigit():
                    continue
                resultados.append({
                    'titulo': titulo,
                    'tipo': 'gobierno abierto — ' + d.get('subtype', 'documento'),
                    'enlace': d.get('link') or d.get('url', ''),
                    'fecha': (d.get('date') or '')[:10],
                })
    except (httpx.HTTPError, ValueError):
        pass

    # deduplicar por enlace
    vistos = set()
    unicos = []
    for r in resultados:
        if r['enlace'] not in vistos:
            vistos.add(r['enlace'])
            unicos.append(r)
    return {'consulta': consulta, 'total': len(unicos), 'resultados': unicos[:n]}


def licitaciones(n=5):
    """Últimas licitaciones publicadas en Gobierno Abierto."""
    n = max(1, min(int(n or 5), 10))
    try:
        datos = _get(f'{_API_GA}/search',
                     {'search': 'licitacion', 'per_page': n, 'orderby': 'date', 'order': 'desc'})
    except (httpx.HTTPError, ValueError) as e:
        return {'error': f'No se pudo consultar licitaciones: {str(e)[:150]}'}
    if not isinstance(datos, list):
        return {'error': 'El portal de Gobierno Abierto devolvió una respuesta inesperada.'}
    items = [{
        'titulo': _titulo(d),
        'enlace': d.get('link') or d.get('url', ''),
        'fecha': (d.get('date') or '')[:10],
    } for d in datos if _titulo(d)]
    return {'total': len(items), 'licitaciones': items}


def guia_tramites(n=10):
    """Lista la guía de trámites municipales (desde la página oficial de la guía)."""
    n = max(1, min(int(n or 10), 25))
    try:
        resp = httpx.get(f'{SITIO}/guia-de-tramites/', headers=_UA, timeout=_TIMEOUT)
        resp.raise_for_status()
    except httpx.HTTPError as e:
        return {'error': f'No se pudo consultar la guía de trámites: {str(e)[:150]}'}
    html_texto = resp.text
    # Enlaces a trámites: <a ... href=".../tramite/slug/">Nombre</a>
    enlaces = re.findall(
        r'href="(https://municipioderawson\.gob\.ar/tramite/[^"]+)"[^>]*>\s*'
        r'(?:<[^>]+>\s*)*([^<]{3,120}?)\s*<',
        html_texto,
    )
    tramites = []
    vistos = set()
    for enlace, nombre in enlaces:
        nombre = _limpiar(nombre)
        if not nombre or enlace in vistos or enlace.endswith('/guia-de-tramites/'):
            continue
        vistos.add(enlace)
        tramites.append({'titulo': nombre, 'enlace': enlace})
        if len(tramites) >= n:
            break
    return {'total': len(tramites), 'tramites': tramites}
