"""Núcleo del Experto SIGAP Rawson — LLM DeepSeek + herramientas + conocimiento."""
import json
import logging
import os
import threading
import time

from dotenv import load_dotenv
from openai import OpenAI

from app import conocimiento, herramientas

load_dotenv()
logger = logging.getLogger('sigap.agente')

_cliente = OpenAI(
    api_key=os.getenv('DEEPSEEK_API_KEY', ''),
    base_url=os.getenv('DEEPSEEK_BASE_URL', 'https://api.deepseek.com'),
)
_MODELO = os.getenv('DEEPSEEK_MODEL', 'deepseek-chat')

_SISTEMA_BASE = """\
Sos el asistente oficial de la Municipalidad de Rawson (San Juan, Argentina): un agente
experto en SIGAP, el sistema de gestión tributaria y administrativa del municipio, y en
los trámites municipales.

REGLAS ESTRICTAS:
1. DATOS REALES: para cualquier dato del municipio (expedientes, deuda, recaudación,
   KPIs, contribuyentes) SIEMPRE usá las herramientas disponibles. NUNCA inventes
   números, estados ni fechas. Si una herramienta falla o no hay datos, decilo
   con honestidad.
2. CONOCIMIENTO: usá el contexto de conocimiento municipal que se te adjunta para
   explicar conceptos (cómo se calcula la deuda, tipos de boleta, qué es un plan de
   pago, cómo funciona el sistema de expedientes, autoridades, contacto y servicios).
3. SITIO OFICIAL DEL MUNICIPIO (municipioderawson.gob.ar): sos experto también en lo
   publicado en la web oficial. Para preguntas sobre NOTICIAS, TRÁMITES, LICITACIONES,
   ORDENANZAS, RESOLUCIONES, EVENTOS o INFORMACIÓN PÚBLICA del municipio, usá las
   herramientas:
   - ultimas_noticias() → novedades recientes del sitio oficial.
   - buscar_sitio_municipal(consulta) → buscar un trámite/licitación/ordenanza específica
     (también busca en el portal de Gobierno Abierto: boletín oficial y normativa).
   - guia_tramites() → listar los trámites disponibles.
   - licitaciones() → últimas licitaciones públicas publicadas en Gobierno Abierto.
   Respondé con el detalle encontrado e incluí el enlace del sitio oficial cuando exista.
   Para AUTORIDADES y CONTACTO (intendente, gabinete, teléfonos, dirección) usá el
   conocimiento adjunto (Sitio Oficial — Autoridades Y Contacto).
3. DATOS PERSONALES Y VERIFICACIÓN DE IDENTIDAD (protocolo obligatorio):
   Antes de mostrar deuda o datos personales de un contribuyente, SIEMPRE:
   a) Pedí el DNI del solicitante.
   b) Llamá a buscar_por_dni(dni):
      - 0 resultados → "Ese DNI no figura en el padrón. Podés acercarte a Rentas o revisar el número."
      - 1 resultado → hacé UNA pregunta de contraste SIN revelar el dato:
        "Para confirmar tu identidad: ¿cuál es la calle del domicilio registrado?"
        (o el nombre del titular). Cuando el usuario responda, llamá a
        verificar_identidad(dni, nomenclatura, respuesta). Si verificada=true →
        mostrá la deuda (podés llamar deuda_contribuyente para el desglose).
        Si verificada=false → negá los datos y sugerí acercarte a Rentas.
      - Varios resultados → listá SOLO las nomenclaturas y barrios, pedile al usuario
        que elija SU cuenta (nomenclatura), y recién entonces hacé la pregunta de
        contraste sobre ESA cuenta y llamá a verificar_identidad con la nomenclatura
        elegida. Actuá según verificada=true/false.
   c) NUNCA muestres nombre completo, domicilio completo ni deuda ANTES de que el
      usuario responda correctamente la pregunta de contraste.
   d) Nunca muestres datos de terceros: si el DNI no corresponde al que pregunta,
      no reveles nada.
4. TONO: profesional, cálido y claro. Español de Argentina. Respuestas concisas con
   formato legible (negritas con **, listas cuando aporten). Montos en pesos argentinos.
5. LÍMITES: no opines de política. No des asesoramiento legal definitivo: en temas
   legales o de cobro judicial, derivá a la oficina correspondiente de la municipalidad.
6. SIEMPRE respondé en español.
"""

# Sesiones en memoria: id → lista de mensajes (con límite).
_sesiones = {}
_sesiones_lock = threading.Lock()
_MAX_MENSAJES = 24
_TTL_SESION = 60 * 60  # 1 hora
_RATE_MSJ_MIN = int(os.getenv('AGENT_RATE_MINUTO', '30'))
_uso = {}
_uso_lock = threading.Lock()


def _con_sistema(pregunta):
    """Construye la lista de mensajes con sistema + conocimiento relevante."""
    contexto = conocimiento.buscar_conocimiento(pregunta, top=2)
    sistema = _SISTEMA_BASE + '\n\n' + conocimiento.PERFIL_MUNICIPAL
    if contexto:
        sistema += ('\n\n## CONOCIMIENTO MUNICIPAL RELEVANTE PARA ESTA PREGUNTA\n'
                    + '\n\n'.join(contexto))
    return [{'role': 'system', 'content': sistema}]


def _limitar_uso(sesion_id):
    ahora = time.time()
    with _uso_lock:
        accesos = [t for t in _uso.get(sesion_id, []) if ahora - t < 60]
        if len(accesos) >= _RATE_MSJ_MIN:
            return False
        accesos.append(ahora)
        _uso[sesion_id] = accesos
        return True


def _obtener_sesion(sesion_id):
    with _sesiones_lock:
        ahora = time.time()
        for sid in list(_sesiones):
            if ahora - _sesiones[sid]['ts'] > _TTL_SESION:
                _sesiones.pop(sid, None)
        s = _sesiones.get(sesion_id)
        if not s:
            s = {'ts': ahora, 'mensajes': []}
            _sesiones[sesion_id] = s
        s['ts'] = ahora
        return s


def _recortar(mensajes):
    if len(mensajes) > _MAX_MENSAJES:
        return mensajes[:1] + mensajes[-(_MAX_MENSAJES - 1):]
    return mensajes


def responder(sesion_id, pregunta):
    """Procesa un mensaje del usuario y devuelve la respuesta del agente."""
    if not _limitar_uso(sesion_id or 'anon'):
        return '⚠️ Estás enviando mensajes muy rápido. Esperá un minuto y volvé a intentar.'

    sesion = _obtener_sesion(sesion_id)
    sesion['mensajes'].append({'role': 'user', 'content': pregunta})

    mensajes = _con_sistema(pregunta) + _recortar(sesion['mensajes'])
    intentos = 0

    while intentos < 5:
        intentos += 1
        try:
            resp = _cliente.chat.completions.create(
                model=_MODELO,
                messages=mensajes,
                tools=herramientas.HERRAMIENTAS,
                temperature=0.3,
            )
        except Exception as e:
            logger.error(f'Error LLM: {e}')
            return ('⚠️ Hubo un problema al consultar el modelo de lenguaje. '
                    'Intentá de nuevo en unos segundos.')

        msg = resp.choices[0].message

        # ¿El modelo quiere usar herramientas?
        if msg.tool_calls:
            mensajes.append({
                'role': 'assistant',
                'content': msg.content or '',
                'tool_calls': [{
                    'id': tc.id,
                    'type': 'function',
                    'function': {'name': tc.function.name,
                                 'arguments': tc.function.arguments},
                } for tc in msg.tool_calls],
            })
            for tc in msg.tool_calls:
                nombre = tc.function.name
                resultado = herramientas.ejecutar(nombre, tc.function.arguments)
                mensajes.append({
                    'role': 'tool',
                    'tool_call_id': tc.id,
                    'content': json.dumps(resultado, ensure_ascii=False, default=str),
                })
            continue  # volver a preguntar al modelo con los resultados

        respuesta = (msg.content or '').strip()
        sesion['mensajes'].append({'role': 'assistant', 'content': respuesta})
        sesion['mensajes'] = _recortar(sesion['mensajes'])
        return respuesta

    return ('⚠️ La consulta requirió demasiadas búsquedas internas. '
            'Reformulá la pregunta, por favor.')


def limpiar_sesion(sesion_id):
    with _sesiones_lock:
        _sesiones.pop(sesion_id, None)
