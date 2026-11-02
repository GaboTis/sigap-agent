"""Herramientas del agente — consultas en vivo a sigap-mcp (REST).

Cada herramienta es una función que el LLM puede invocar (function calling).
Solo lectura, con el token del cliente "agentes".
"""
import json
import os

import httpx
from dotenv import load_dotenv

from app import sitio_municipal

load_dotenv()

MCP_URL = os.getenv('SIGAP_MCP_URL', 'http://127.0.0.1:8100')
MCP_TOKEN = os.getenv('SIGAP_MCP_TOKEN', '')


def _get(ruta, params=None):
    resp = httpx.get(f'{MCP_URL}{ruta}', params=params or {},
                     headers={'Authorization': f'Bearer {MCP_TOKEN}'}, timeout=90)
    resp.raise_for_status()
    return resp.json()


def _post(ruta, body):
    resp = httpx.post(f'{MCP_URL}{ruta}', json=body,
                      headers={'Authorization': f'Bearer {MCP_TOKEN}'}, timeout=90)
    resp.raise_for_status()
    return resp.json()


# ── Consultas SQL a la base (agente "habla con la DB") ─────────

def listar_tablas(filtro: str = '') -> dict:
    """Lista tablas de la base SIGAPP con su cantidad de filas."""
    return _get('/api/consulta/esquema', {'filtro': filtro})


def columnas_tabla(tabla: str) -> dict:
    """Columnas de una tabla de SIGAPP (nombre, tipo, largo)."""
    return _get('/api/consulta/columnas', {'tabla': tabla})


def ejecutar_consulta(sql: str) -> dict:
    """Ejecuta una consulta SELECT (solo lectura) contra SIGAPP.

    Límites: máx. 200 filas, timeout 20s, sin bloqueos. Si falla, devuelve
    el error para corregir la consulta y reintentar.
    """
    return _post('/api/consulta/sql', {'sql': sql})


def ejecutar_consultas(sqls: list) -> dict:
    """Ejecuta VARIAS consultas SELECT (hasta 6) en una sola llamada batch.

    Para preguntas compuestas: armá todas las consultas que necesites y
    mandalas juntas; recibís los resultados etiquetados por índice.
    """
    return _post('/api/consulta/sql-batch', {'consultas': sqls})


def exportar_listado(titulo: str, sqls: list, nombre_archivo: str = '',
                     formato: str = 'xlsx') -> dict:
    """Genera una planilla descargable (EXCEL o PDF) con los resultados de las
    consultas SQL. Ejecuta contra SIGAP (hasta 5.000 filas por consulta), una
    hoja/sección por consulta. formato: 'xlsx' o 'pdf'. Devuelve el enlace.
    """
    from app import planillas as _planillas
    d = _post('/api/consulta/exportar', {'consultas': sqls})
    if not d.get('ok'):
        return {'error': d.get('error', 'Error al ejecutar las consultas para la planilla.')}
    resultados = [r for r in d.get('resultados', []) if r.get('ok')]
    if not resultados:
        errores = [r.get('error') for r in d.get('resultados', []) if not r.get('ok')]
        return {'error': 'Ninguna consulta devolvió datos. ' + '; '.join(errores)[:200]}
    try:
        info = _planillas.generar_exporte(titulo, resultados, nombre_archivo, formato)
    except Exception as e:
        return {'error': f'No se pudo generar la planilla: {str(e)[:200]}'}
    info['titulo'] = titulo
    info['formato'] = (formato or 'xlsx').lower()
    return info


def generar_planilla(titulo: str, sqls: list, nombre_archivo: str = '') -> dict:
    """Alias de exportar_listado con formato Excel (xlsx)."""
    return exportar_listado(titulo, sqls, nombre_archivo, 'xlsx')


# ── Sitio oficial del municipio (municipioderawson.gob.ar) ────

def ultimas_noticias(n: int = 5) -> dict:
    """Últimas noticias publicadas en el sitio oficial del municipio."""
    return sitio_municipal.ultimas_noticias(n)


def buscar_sitio_municipal(consulta: str, n: int = 6) -> dict:
    """Busca en el sitio oficial del municipio (noticias, páginas y trámites)."""
    return sitio_municipal.buscar_sitio(consulta, n)


def guia_tramites(n: int = 10) -> dict:
    """Lista la guía de trámites municipales del sitio oficial (sección trámites)."""
    return sitio_municipal.guia_tramites(n)


def detalle_tramite(consulta: str) -> dict:
    """Detalle completo de un trámite municipal: requisitos, documentación,
    pasos, costo, dónde y cuándo. Fuente: la sección de TRÁMITES del sitio
    oficial (municipioderawson.gob.ar/tramite/...). NO usa noticias."""
    return sitio_municipal.detalle_tramite(consulta)


def licitaciones(n: int = 5) -> dict:
    """Últimas licitaciones publicadas en Gobierno Abierto."""
    return sitio_municipal.licitaciones(n)


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


def buscar_esquema(q: str = '') -> dict:
    """Diccionario de datos de SIGAP: busca la tabla correcta por tema.
    Usar SIEMPRE primero ante preguntas de datos (deudas, cobros, pagos,
    contabilidad, expedientes, padrón) para ubicar la tabla adecuada."""
    d = _get('/api/esquema/buscar', {'q': q})
    if not d.get('tablas'):
        return {'total': 0, 'mensaje': f'No encontré tablas para "{q}". Probá con otro término.'}
    return {'total': d['total'], 'dominio': d.get('dominio_detectado'),
            'tablas': [{'tabla': t['tabla'], 'dominio': t['dominio'],
                        'descripcion': t['descripcion'], 'claves': t['claves']}
                       for t in d['tablas']]}


def esquema_tabla(tabla: str) -> dict:
    """Columnas reales + muestra de una tabla (para armar el SQL correcto)."""
    d = _get('/api/esquema/tabla', {'tabla': tabla})
    if d.get('error'):
        return {'error': d['error']}
    resp = {'tabla': d['tabla'], 'columnas': [c['nombre'] for c in d.get('columnas', [])]}
    if d.get('diccionario'):
        resp['descripcion'] = d['diccionario']['descripcion']
        resp['claves'] = d['diccionario']['claves']
    if d.get('muestra'):
        resp['muestra'] = d['muestra'][:2]
    return resp


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


def listar_expedientes(tema: str = '', estado: str = 'en_curso', limite: int = 30) -> dict:
    """Listado filtrable de expedientes ordenado por ANTIGÜEDAD (más viejos primero).

    - tema: texto del asunto (ej. 'contrat' para expedientes de contratos/contrataciones).
    - estado: 'en_curso' (default, incluye E e I), 'todos', 'pagado', 'cerrado', 'archivo'.
    """
    d = _get('/api/expedientes/listar', {'tema': tema, 'estado': estado, 'limite': limite})
    if not d.get('resultados'):
        return {'total': 0, 'mensaje': f'No hay expedientes que coincidan con el filtro.'}
    resumen = [{
        'expediente': r['expediente'],
        'fecha_inicio': r['fecha_inicio'] or 'sin fecha',
        'estado': r['estado_desc'],
        'tipo': r['tipo'],
        'sector_actual': r['sector_actual'],
        'motivo': r['motivo'][:110],
    } for r in d['resultados']]
    return {'total': d['total'], 'limite': d['limite'],
            'filtros': d['filtros'], 'resultados': resumen}


def deuda_contribuyente(codigo: str) -> dict:
    """Deuda del padrón oficial de un contribuyente (por nomenclatura IM/CO…).
    ⚠️ Solo responder con estos datos si la identidad del solicitante fue verificada."""
    d = _get('/api/contribuyentes/deuda', {'codigo': codigo})
    return {
        'nomenclatura': d['nomenclatura'], 'nombre': d['nombre'],
        'tipo': d['tipo'], 'barrio': d['barrio'],
        'deuda': d['deuda'], 'actualizado': d['actualizado'],
    }


def buscar_por_dni(dni: int) -> dict:
    """Busca contribuyentes por DNI para verificar identidad.

    ⚠️ Los datos devueltos (nombre, domicilio, deuda) son para CONTRASTAR la
    identidad: el agente NUNCA debe mostrarlos al usuario antes de que este
    confirme correctamente el dato de verificación.
    """
    return _get('/api/contribuyentes/por-dni', {'dni': dni})


def verificar_identidad(dni: int, nomenclatura: str, respuesta: str) -> dict:
    """Compara la respuesta de contraste del usuario contra el padrón (determinístico).

    Devuelve {'verificada': true/false}. Si verificada=true, recién ahí se puede
    mostrar la deuda de esa cuenta.
    """
    import httpx as _httpx
    resp = _httpx.post(f'{MCP_URL}/api/contribuyentes/verificar',
                       json={'dni': dni, 'nomenclatura': nomenclatura, 'respuesta': respuesta},
                       headers={'Authorization': f'Bearer {MCP_TOKEN}'}, timeout=90)
    resp.raise_for_status()
    return resp.json()


def buscar_contribuyente(q: str, limit: int = 20) -> dict:
    """Busca contribuyentes en el padrón por nomenclatura o nombre
    (todas las palabras, en cualquier orden)."""
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


def canales_recaudacion(anio: int = None) -> dict:
    """Recaudación del año por canal (cajas, colectores, MP, agentes, banco)."""
    return _get('/api/recaudacion/canales', {'anio': anio})


def anulaciones(anio: int = None, limit: int = 20, mes: int = None) -> dict:
    """Cobros anulados del año: por mes y últimos registros con motivo (filtro mes opcional)."""
    return _get('/api/recaudacion/anulaciones', {'anio': anio, 'limit': limit, 'mes': mes})


def colectores(anio: int = None) -> dict:
    """Ranking de colectores: recaudación y deuda del padrón asignada."""
    return _get('/api/recaudacion/colectores', {'anio': anio})


def medios_pago(anio: int = None) -> dict:
    """Composición mensual de la recaudación: efectivo, depósito/cheque, digital."""
    return _get('/api/recaudacion/medios', {'anio': anio})


def cobros_del_dia() -> dict:
    """Cobros de HOY discriminados: total, por tipo de boleta, partida y cobrador."""
    return _get('/api/recaudacion/cobros-del-dia')


def kpis_ejecutivos() -> dict:
    """KPIs ejecutivos consolidados (recaudación, deuda, gestión, compras, stock)."""
    return _get('/api/panel/kpis')


# ── Herramientas por modo de acceso ─────────────────────────
# 'visor' = solo consultas (sin generar planillas/exportes)
_NOMBRES_EXPORTACION = {'exportar_listado', 'generar_planilla'}


def herramientas_para(modo=None):
    """Herramientas disponibles según el modo de acceso del canal."""
    if modo == 'visor':
        return [h for h in HERRAMIENTAS
                if h.get('function', {}).get('name') not in _NOMBRES_EXPORTACION]
    return HERRAMIENTAS


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
            'name': 'buscar_esquema',
            'description': 'DICCIONARIO DE DATOS: busca las tablas de SIGAP por tema o sinónimos '
                           '(deudas, cobros, pagos, contabilidad/gastos, expedientes, padrón). '
                           'Devuelve QUÉ ES cada tabla y sus columnas clave. Usar SIEMPRE primero '
                           'ante una pregunta de datos para ubicar la tabla correcta.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'q': {'type': 'string', 'description': 'Tema a buscar (ej. "gastos", "cobros del día", "pagos a proveedores", "deuda")'},
                },
                'required': ['q'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'esquema_tabla',
            'description': 'Columnas reales y muestra de UNA tabla de SIGAP. Usar para confirmar '
                           'nombres de columnas antes de ejecutar una consulta SQL.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'tabla': {'type': 'string', 'description': 'Nombre exacto de la tabla'},
                },
                'required': ['tabla'],
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
            'name': 'listar_expedientes',
            'description': 'Listado filtrable de expedientes ordenados por ANTIGÜEDAD (más viejos '
                           'primero). Filtra por TEMA del asunto (ej. tema="contrat" para expedientes '
                           'de contratos/contrataciones) y por ESTADO (en_curso, pagado, cerrado, '
                           'archivo, todos). Usar cuando piden listados: "expedientes de X en curso", '
                           '"los más antiguos", "cuántos hay de Y".',
            'parameters': {
                'type': 'object',
                'properties': {
                    'tema': {'type': 'string', 'description': 'Texto del asunto a filtrar (ej. "contrat", "obra", "licitación"). Vacío = sin filtro.'},
                    'estado': {'type': 'string', 'description': "en_curso (default) | todos | pagado | cerrado | archivo"},
                    'limite': {'type': 'integer', 'description': 'Cantidad de resultados (1-500, default 30)'},
                },
                'required': [],
            },
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
            'name': 'buscar_por_dni',
            'description': 'Busca contribuyentes por DNI para VERIFICAR IDENTIDAD antes de mostrar '
                           'deuda o datos personales. Devuelve nombre, domicilio, barrio y deuda '
                           'de las cuentas asociadas. Los datos son para contraste interno: nunca '
                           'mostrarlos al usuario antes de que confirme el dato de verificación.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'dni': {'type': 'integer', 'description': 'Número de DNI del solicitante'},
                },
                'required': ['dni'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'verificar_identidad',
            'description': 'Verificación determinística de identidad: compara la respuesta de '
                           'contraste del usuario (calle o nombre del titular) contra el padrón. '
                           'Usar DESPUÉS de pedir el dato de contraste. Si verificada=true se puede '
                           'mostrar la deuda de la cuenta; si false, negar los datos y derivar a Rentas.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'dni': {'type': 'integer', 'description': 'DNI del solicitante'},
                    'nomenclatura': {'type': 'string', 'description': 'Nomenclatura de la cuenta elegida'},
                    'respuesta': {'type': 'string', 'description': 'Respuesta textual del usuario al dato de contraste'},
                },
                'required': ['dni', 'nomenclatura', 'respuesta'],
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
            'name': 'canales_recaudacion',
            'description': 'Recaudación del año por canal de cobro: cajas, colectores, Mercado Pago, '
                           'agentes (Pago Fácil/Rapipago), banco, foto multas y tesorería. '
                           'Usar cuando preguntan cuánto se recaudó por cada canal o medio.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'anio': {'type': 'integer', 'description': 'Año (opcional, default actual)'},
                },
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'anulaciones',
            'description': 'Cobros anulados del año: totales por mes y últimos cobros anulados '
                           'con motivo. Usar cuando preguntan por cobros anulados o devoluciones.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'anio': {'type': 'integer', 'description': 'Año (opcional)'},
                    'limit': {'type': 'integer', 'description': 'Cantidad de registros (default 20)'},
                    'mes': {'type': 'integer', 'description': 'Mes 1-12 para filtrar los últimos registros (opcional)'},
                },
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'colectores',
            'description': 'Ranking de colectores del año: recaudación por colector, cobros, '
                           'contribuyentes asignados y deuda del padrón asignada a cada uno.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'anio': {'type': 'integer', 'description': 'Año (opcional)'},
                },
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'cobros_del_dia',
            'description': 'Cobros de HOY ya discriminados: total (cobros y monto), anulados, '
                           'pagos digitales, desglose por tipo de boleta, por partida presupuestaria '
                           'y por cobrador. Usar SIEMPRE cuando pregunten cuánto se cobró hoy, '
                           'cómo se compone el cobro del día o de dónde sale ese monto. '
                           'NO intentes armar SQL para esto: usá esta herramienta.',
            'parameters': {'type': 'object', 'properties': {}},
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'medios_pago',
            'description': 'Composición mensual de la recaudación del año: efectivo/caja, '
                           'depósito/cheque y pagos digitales (Mercado Pago y foto multas).',
            'parameters': {
                'type': 'object',
                'properties': {
                    'anio': {'type': 'integer', 'description': 'Año (opcional)'},
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
    {
        'type': 'function',
        'function': {
            'name': 'listar_tablas',
            'description': 'Lista las tablas de la base SIGAPP con su cantidad aproximada de filas '
                           '(las más grandes primero). Usar para localizar la tabla correcta antes '
                           'de escribir una consulta SQL.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'filtro': {'type': 'string', 'description': 'Parte del nombre de la tabla (ej. "cobro", "boleta", "contribu")'},
                },
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'columnas_tabla',
            'description': 'Devuelve las columnas de una tabla de SIGAP (nombre, tipo y largo) '
                           'para armar una consulta SQL correcta.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'tabla': {'type': 'string', 'description': 'Nombre exacto de la tabla'},
                },
                'required': ['tabla'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'ejecutar_consulta',
            'description': 'Ejecuta una consulta SQL de SOLO LECTURA generada para responder la '
                           'pregunta del usuario, contra la base SIGAP. Solo SELECT/WITH; máximo '
                           '200 filas; timeout 20s. Si devuelve error, corregí la consulta y '
                           'reintentá. Antes de responder, verificá que los resultados realmente '
                           'respondan la pregunta.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'sql': {'type': 'string', 'description': 'Consulta SELECT a ejecutar'},
                },
                'required': ['sql'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'ejecutar_consultas',
            'description': 'Ejecuta VARIAS consultas SQL de SOLO LECTURA en una sola llamada '
                           '(hasta 6). Usar para preguntas compuestas que requieren varios '
                           'números a la vez (ej. hoy vs mismo día del año pasado, discriminado '
                           'por tipo y por cobrador). Devuelve los resultados etiquetados por '
                           'índice; si alguna falla, corregí solo esa y reintentá.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'sqls': {
                        'type': 'array',
                        'items': {'type': 'string'},
                        'description': 'Lista de consultas SELECT (máx. 6)',
                    },
                },
                'required': ['sqls'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'exportar_listado',
            'description': 'Genera una planilla descargable — EXCEL (.xlsx) o PDF — con los '
                           'resultados de una o varias consultas SQL de SOLO LECTURA (hasta '
                           '5.000 filas por consulta; una hoja/sección por consulta, con '
                           'encabezados). Usar CUANDO el usuario pida un listado, planilla, '
                           'Excel, PDF o exportar datos (ej. recorrido de comercios por zonas, '
                           'habilitaciones del año, deudas, cobros). Armá las consultas SELECT '
                           'necesarias (UNA por zona/período) y llamá UNA sola vez; después '
                           'respondé con el enlace de descarga y un resumen. NO vuelques las '
                           'filas en el chat. Si piden PDF usá formato="pdf"; si no aclaran, '
                           'xlsx.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'titulo': {'type': 'string', 'description': 'Título del listado (ej. '
                               '"Recorrido comercios colector 8888 por zonas")'},
                    'sqls': {'type': 'array', 'items': {'type': 'string'},
                             'description': 'Consultas SELECT cuyos resultados van a la '
                                            'planilla (una por zona/hoja)'},
                    'nombre_archivo': {'type': 'string',
                                       'description': 'Nombre del archivo (sin extensión, ej. '
                                                      '"recorrido_colector_8888")'},
                    'formato': {'type': 'string', 'enum': ['xlsx', 'pdf'],
                                'description': 'Formato de exportación: xlsx (Excel, default) '
                                               'o pdf'},
                },
                'required': ['titulo', 'sqls'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'ultimas_noticias',
            'description': 'Últimas noticias publicadas en el sitio oficial del municipio '
                           '(municipioderawson.gob.ar). Usar cuando preguntan por novedades, '
                           'noticias o anuncios recientes del municipio.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'n': {'type': 'integer', 'description': 'Cantidad de noticias (default 5)'},
                },
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'buscar_sitio_municipal',
            'description': 'Busca en el sitio oficial del municipio (noticias, páginas, ordenanzas, '
                           'licitaciones, trámites). Usar cuando preguntan por un trámite específico, '
                           'licitación, ordenanza, resolución, evento o información publicada en la web municipal.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'consulta': {'type': 'string', 'description': 'Términos a buscar (ej. "moratoria", "licitación")'},
                    'n': {'type': 'integer', 'description': 'Máximo de resultados (default 6)'},
                },
                'required': ['consulta'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'guia_tramites',
            'description': 'Lista la guía de trámites municipales del sitio oficial (sección '
                           'TRÁMITES de municipioderawson.gob.ar). Usar cuando preguntan qué '
                           'trámites existen o dónde hacer un trámite municipal. Para explicar '
                           'CÓMO hacer un trámite (requisitos, pasos, costo) usá detalle_tramite, '
                           'NUNCA las noticias.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'n': {'type': 'integer', 'description': 'Cantidad de trámites (default 10)'},
                },
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'detalle_tramite',
            'description': 'Detalle completo de UN trámite municipal: requisitos, documentación, '
                           'pasos a seguir, costo, dónde y cuándo se realiza. Fuente exclusiva: la '
                           'sección de TRÁMITES del sitio oficial (municipioderawson.gob.ar/tramite/). '
                           'Usar SIEMPRE que pregunten cómo hacer un trámite o qué necesitan para un '
                           'trámite. NO usar noticias ni otra fuente para explicar trámites.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'consulta': {'type': 'string',
                                 'description': 'Nombre del trámite (ej. "libre deuda", '
                                                '"habilitación comercio", "cambio de titularidad")'},
                },
                'required': ['consulta'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'licitaciones',
            'description': 'Últimas licitaciones públicas publicadas en el portal de Gobierno Abierto '
                           'del municipio. Usar cuando preguntan por licitaciones o compras públicas.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'n': {'type': 'integer', 'description': 'Cantidad de licitaciones (default 5)'},
                },
            },
        },
    },
]

_FUNCIONES = {
    'buscar_expediente': buscar_expediente,
    'detalle_expediente': detalle_expediente,
    'analitica_expedientes': analitica_expedientes,
    'listar_expedientes': listar_expedientes,
    'buscar_esquema': buscar_esquema,
    'esquema_tabla': esquema_tabla,
    'deuda_contribuyente': deuda_contribuyente,
    'buscar_por_dni': buscar_por_dni,
    'verificar_identidad': verificar_identidad,
    'buscar_contribuyente': buscar_contribuyente,
    'recaudacion': recaudacion,
    'ejecucion_presupuestaria': ejecucion_presupuestaria,
    'canales_recaudacion': canales_recaudacion,
    'anulaciones': anulaciones,
    'colectores': colectores,
    'medios_pago': medios_pago,
    'cobros_del_dia': cobros_del_dia,
    'kpis_ejecutivos': kpis_ejecutivos,
    'listar_tablas': listar_tablas,
    'columnas_tabla': columnas_tabla,
    'ejecutar_consulta': ejecutar_consulta,
    'ejecutar_consultas': ejecutar_consultas,
    'generar_planilla': generar_planilla,
    'exportar_listado': exportar_listado,
    'ultimas_noticias': ultimas_noticias,
    'buscar_sitio_municipal': buscar_sitio_municipal,
    'guia_tramites': guia_tramites,
    'detalle_tramite': detalle_tramite,
    'licitaciones': licitaciones,
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
