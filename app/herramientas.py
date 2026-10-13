"""Herramientas del agente — consultas en vivo a sigap-mcp (REST).

Cada herramienta es una función que el LLM puede invocar (function calling).
Solo lectura, con el token del cliente "agentes".
"""
import json
import os

import httpx
from dotenv import load_dotenv

load_dotenv()

MCP_URL = os.getenv('SIGAP_MCP_URL', 'http://127.0.0.1:8100')
MCP_TOKEN = os.getenv('SIGAP_MCP_TOKEN', '')


def _get(ruta, params=None):
    resp = httpx.get(f'{MCP_URL}{ruta}', params=params or {},
                     headers={'Authorization': f'Bearer {MCP_TOKEN}'}, timeout=90)
    resp.raise_for_status()
    return resp.json()


def buscar_expediente(q: str, limit: int = 5) -> dict:
    """Busca expedientes por número/año/letra (ej. '3540', '3540-S-2026')."""
    d = _get('/api/expedientes/buscar', {'q': q, 'limit': limit})
    if not d.get('resultados'):
        return {'total': 0, 'mensaje': f'No se encontraron expedientes para "{q}".'}
    resumen = [{
        'expediente': f"{r['numero']}{'-' + r['letra'] if r['letra'] else ''}/{r['ano']}",
        'fecha_inicio': r['fecha_inicio'], 'estado': r['estado_desc'],
        'sector_actual': r['sector_actual'], 'tipo': r['tipo'],
        'motivo': r['motivo'][:120],
    } for r in d['resultados']]
    return {'total': d['total'], 'resultados': resumen}


def detalle_expediente(numero: int, ano: int = None, letra: str = None) -> dict:
    """Detalle completo de un expediente con su recorrido entre sectores."""
    d = _get('/api/expedientes/detalle', {'numero': numero, 'ano': ano, 'letra': letra})
    x = d['expediente']
    movs = d['movimientos']
    return {
        'expediente': f"{x['numero']}{'-' + x['letra'] if x['letra'] else ''}/{x['ano']}",
        'motivo': x['motivo'],
        'tipo': x['tipo_desc'], 'estado': x['estado_desc'],
        'fecha_inicio': x['fecha_inicio'], 'dias_tramite': x['dias_tramite'],
        'sector_actual': x['sector_actual_desc'],
        'responsable_actual': x['resp_actual'],
        'sector_destino': x['sector_destino_desc'],
        'recorrido': [{'fecha': m['fecha_hora'], 'sector': m['sector_desc'],
                       'desde': m['proveniente_desc']} for m in movs],
        'cantidad_movimientos': len(movs),
    }


def analitica_expedientes() -> dict:
    """Analítica de gestión de expedientes (tiempos, backlog, carga por sector)."""
    d = _get('/api/expedientes/analitica')
    return {
        'en_tramite': d['en_tramite'],
        'promedio_dias_en_tramite': d['promedio_dias_en_tramite'],
        'mediana_dias_en_tramite': d['mediana_dias_en_tramite'],
        'pct_mas_180_dias': d['pct_mas_180'],
        'resolucion_promedio_dias': d['resolucion_promedio_dias'],
        'resolucion_por_tipo': d['resolucion_por_tipo'][:6],
        'carga_por_sector': d['carga_por_sector'][:8],
        'mas_demorados': d['mas_demorados'][:5],
    }


def deuda_contribuyente(codigo: str) -> dict:
    """Deuda del padrón oficial de un contribuyente (por nomenclatura IM/CO…).
    ⚠️ Solo responder con estos datos si la identidad del solicitante fue verificada."""
    d = _get('/api/contribuyentes/deuda', {'codigo': codigo})
    return {
        'nomenclatura': d['nomenclatura'], 'nombre': d['nombre'],
        'tipo': d['tipo'], 'barrio': d['barrio'],
        'deuda': d['deuda'], 'actualizado': d['actualizado'],
    }


def buscar_contribuyente(q: str, limit: int = 5) -> dict:
    """Busca contribuyentes en el padrón por nomenclatura o nombre."""
    d = _get('/api/contribuyentes/buscar', {'q': q, 'limit': limit})
    if not d.get('resultados'):
        return {'total': 0, 'mensaje': f'No se encontraron contribuyentes para "{q}".'}
    return {'total': d['total'], 'resultados': d['resultados']}


def recaudacion() -> dict:
    """Recaudación municipal: hoy, mes, año, comparativa interanual y mensual 3 años."""
    return _get('/api/recaudacion')


def ejecucion_presupuestaria(ejercicio: int = None, top: int = 6) -> dict:
    """Ejecución presupuestaria de ingresos por partida."""
    return _get('/api/recaudacion/ejecucion', {'ejercicio': ejercicio, 'top': top})


def kpis_ejecutivos() -> dict:
    """KPIs ejecutivos consolidados (recaudación, deuda, gestión, compras, stock)."""
    return _get('/api/panel/kpis')


# ── Esquemas para function calling (OpenAI/DeepSeek) ──────────
HERRAMIENTAS = [
    {
        'type': 'function',
        'function': {
            'name': 'buscar_expediente',
            'description': 'Busca expedientes municipales por número/año/letra (ej. "3540-S-2026", "3540"). '
                           'Usar cuando preguntan por un expediente sin precisar todos los datos.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'q': {'type': 'string', 'description': 'Texto de búsqueda: número, nro/año o nro-letra-año'},
                    'limit': {'type': 'integer', 'description': 'Máximo de resultados (default 5)'},
                },
                'required': ['q'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'detalle_expediente',
            'description': 'Detalle completo de un expediente: estado, sector actual, días de tramitación '
                           'y recorrido completo entre sectores. Usar cuando preguntan "dónde está" o '
                           '"cómo va" un expediente con número conocido.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'numero': {'type': 'integer', 'description': 'Número de expediente'},
                    'ano': {'type': 'integer', 'description': 'Año (opcional, ej. 2026)'},
                    'letra': {'type': 'string', 'description': 'Letra (opcional, ej. S)'},
                },
                'required': ['numero'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'analitica_expedientes',
            'description': 'Analítica de gestión: cuántos expedientes en trámite, tiempos promedio, '
                           'backlog, resolución por tipo y carga por sector. Para preguntas de gestión '
                           'o del personal municipal.',
            'parameters': {'type': 'object', 'properties': {}},
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'deuda_contribuyente',
            'description': 'Deuda del padrón oficial de un contribuyente identificado por su código '
                           'de nomenclatura (ej. IM344002000008). SOLO usar cuando el solicitante ya '
                           'verificó su identidad (indicado en la conversación).',
            'parameters': {
                'type': 'object',
                'properties': {
                    'codigo': {'type': 'string', 'description': 'Código de nomenclatura (IM/CO/CM + dígitos)'},
                },
                'required': ['codigo'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'buscar_contribuyente',
            'description': 'Busca contribuyentes en el padrón por nombre, razón social o nomenclatura.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'q': {'type': 'string', 'description': 'Nombre o código a buscar'},
                    'limit': {'type': 'integer', 'description': 'Máximo de resultados (default 5)'},
                },
                'required': ['q'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'recaudacion',
            'description': 'Recaudación municipal: hoy, mes, año con comparativa interanual, '
                           'índice de cobranza y recaudación mensual de los últimos 3 años.',
            'parameters': {'type': 'object', 'properties': {}},
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'ejecucion_presupuestaria',
            'description': 'Ejecución presupuestaria de ingresos por partida (presupuesto vs ejecutado).',
            'parameters': {
                'type': 'object',
                'properties': {
                    'ejercicio': {'type': 'integer', 'description': 'Año (opcional)'},
                    'top': {'type': 'integer', 'description': 'Cantidad de partidas (default 6)'},
                },
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'kpis_ejecutivos',
            'description': 'KPIs ejecutivos consolidados del municipio: recaudación, deuda del padrón, '
                           'expedientes en trámite, planes de pago, compras, proveedores y stock. '
                           'Para preguntas del personal o del intendente sobre el estado general.',
            'parameters': {'type': 'object', 'properties': {}},
        },
    },
]

_FUNCIONES = {
    'buscar_expediente': buscar_expediente,
    'detalle_expediente': detalle_expediente,
    'analitica_expedientes': analitica_expedientes,
    'deuda_contribuyente': deuda_contribuyente,
    'buscar_contribuyente': buscar_contribuyente,
    'recaudacion': recaudacion,
    'ejecucion_presupuestaria': ejecucion_presupuestaria,
    'kpis_ejecutivos': kpis_ejecutivos,
}


def ejecutar(nombre, argumentos):
    """Ejecuta una herramienta por nombre con sus argumentos (dict)."""
    fn = _FUNCIONES.get(nombre)
    if not fn:
        return {'error': f'Herramienta desconocida: {nombre}'}
    try:
        args = json.loads(argumentos) if isinstance(argumentos, str) else (argumentos or {})
        return fn(**args)
    except Exception as e:
        return {'error': f'Error al consultar {nombre}: {str(e)[:200]}'}
