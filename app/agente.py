"""Núcleo del Experto SIGAPP Rawson — LLM DeepSeek + herramientas + conocimiento."""
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
# Verificación de identidad: activa por defecto; IDENTIDAD_ACTIVA=0 → modo prueba
# (muestra datos solo con DNI o nombre, sin pregunta de contraste).
_IDENTIDAD_ACTIVA = os.getenv('IDENTIDAD_ACTIVA', '1') != '0'

_PROTOCOLO_IDENTIDAD_ACTIVO = """\
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
"""

_PROTOCOLO_IDENTIDAD_PRUEBA = """\
3. DATOS PERSONALES — MODO PRUEBA (verificación de identidad DESACTIVADA):
   Podés mostrar deuda y datos personales de un contribuyente consultando SOLO
   con DNI (buscar_por_dni) o con nombre/apellido (buscar_contribuyente), SIN
   pregunta de contraste. Si hay varias cuentas, mostralas todas con su
   nomenclatura, nombre y deuda (podés usar deuda_contribuyente para el detalle).
   Aclarale al usuario que la verificación de identidad está desactivada
   temporalmente por pruebas.
"""

_SISTEMA_BASE = """\
Sos el asistente oficial de la Municipalidad de Rawson (San Juan, Argentina): un agente
experto en SIGAPP, el sistema de gestión tributaria y administrativa del municipio, y en
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
   publicado en la web oficial. SEPARÁ SIEMPRE las fuentes según el tema:
   a) NOTICIAS Y NOVEDADES (comunicados, anuncios, eventos recientes):
      - ultimas_noticias() → novedades recientes del sitio oficial.
   b) TRÁMITES (información de un trámite y CÓMO HACERLO: requisitos, documentación,
      pasos, costo, dónde y cuándo). Fuente EXCLUSIVA: la sección de trámites del sitio
      (municipioderawson.gob.ar/tramite/...). NUNCA uses las noticias ni otra fuente
      para explicar trámites:
      - guia_tramites() → listar los trámites disponibles.
      - detalle_tramite(consulta) → requisitos y paso a paso de un trámite puntual.
        Usala SIEMPRE que pregunten cómo hacer un trámite o qué necesitan para uno.
   c) OTROS CONTENIDOS DEL SITIO Y GOBIERNO ABIERTO (ordenanzas, resoluciones,
      licitaciones, boletín oficial, normativa):
      - buscar_sitio_municipal(consulta) → búsqueda general (también en Gobierno Abierto).
      - licitaciones() → últimas licitaciones públicas publicadas en Gobierno Abierto.
   Respondé con el detalle encontrado e incluí el enlace del sitio oficial cuando exista.
   Para AUTORIDADES y CONTACTO (intendente, gabinete, teléfonos, dirección) usá el
   conocimiento adjunto (Sitio Oficial — Autoridades Y Contacto).
3. DATOS PERSONALES: {protocolo_identidad}
4. HABLAR CON LA BASE DE DATOS (consultas SQL generadas por vos):
   Podés responder CUALQUIER pregunta sobre los datos de SIGAPP generando tu propia
   consulta SQL. Protocolo obligatorio:
   a) PRIMERO fijate si ya existe una herramienta que resuelva el pedido sin SQL:
      - cobros del día (total o discriminado) → cobros_del_dia() (NO usar SQL)
      - recaudación hoy/mes/año → recaudacion()
      - canales, colectores, anulaciones, medios → sus herramientas
   b) EXPLORAR: si no hay herramienta, usá listar_tablas(filtro) para localizar
      las tablas y columnas_tabla(tabla) para ver sus columnas.
   c) GENERAR: escribí las consultas SELECT simples y correctas, con alias claros.
      Consejos de datos reales: las fechas van como CAST('AAAAMMDD' AS datetime);
      las columnas COBRADO de boletas y FPAGO de cobros suelen valer 0 (no filtrar por
      ellas); la deuda del padrón oficial está en las tablas DWH_Deudas_Items_AAAAMM
      (filtrar FechaActualizacion máxima por nomencla); NOMENCLA se guarda con
      espacios de relleno (usar LIKE o RTRIM); expedientes se guardan por NUMERO y ANO;
      el DNI REAL de un contribuyente está en contribu.DNI (el campo DNIOCUIT guarda
      un número viejo del padrón); CUIT para empresas en contribu.CUIT.
      SI LA PREGUNTA ES COMPUESTA (varios números/desgloses), usá ejecutar_consultas(sqls)
      con TODAS las consultas juntas en UNA llamada (máx. 6) en lugar de varias llamadas
      de ejecutar_consulta. Escribí las consultas directamente con estos esquemas
      conocidos (sin explorar tablas): cobros(NROCOBRO, FECHA, TOTALGRAL, ANULADO,
      COBRADOR, NOMENCLA, TIPOCOBRO) · cobritem(NROCOBRO, BOLETA, TIPO, TOTAL) ·
      cobrpartid(nrocobro, partida, total) · boletas(NUMERO, ANO, MES, NOMENCLA, ANULA,
      IMPORTE1, FECHAVTO1) · contribu(NOMENCLA, RAZONSOCI, DNIOCUIT, COLECTOR).
      No uses ORDER BY en las consultas batch (se ordena solo por defecto).
   d) EJECUTAR: llamá a ejecutar_consulta(sql) o ejecutar_consultas(sqls). Solo
      SELECT/WITH, máximo 200 filas por consulta, timeout 20 segundos.
   e) VERIFICAR SIEMPRE el resultado antes de responder (obligatorio):
      - ¿Las columnas y filas devueltas responden exactamente lo que preguntaron?
      - ¿Los números son razonables (órdenes de magnitud, no vacíos inesperados)?
      - Si algo no cierra, corregí el SQL y reintentá (máximo 2 reintentos).
      - Si la consulta devolvió error, leé el mensaje, corregí y reintentá.
   f) RESPONDER con el resultado verificando, en lenguaje natural y claro. Si el dato
      no existe o la consulta sigue fallando, decilo con honestidad.
   g) NUNCA muestres datos personales de terceros por esta vía sin pasar el protocolo
      de verificación de identidad del punto 3.
5. LISTADOS Y PLANILLAS (Excel/PDF): cuando el usuario pida un listado, planilla,
   Excel, PDF o exportar datos (ej. 'habilitaciones de comercio 2025 y 2026'):
   a) Armá las consultas SELECT necesarias: UNA por zona/período/bloque (las
      planillas soportan hasta 5.000 filas por consulta; NO uses TOP 200).
   b) Llamá a exportar_listado(titulo, sqls, nombre_archivo, formato) UNA sola vez.
      formato='xlsx' por defecto; formato='pdf' si lo piden en PDF.
   c) Respondé con el enlace de descarga y un resumen (qué contiene, cuántas
      filas). NO vuelques las filas en el chat.
   RECORRIDOS / ZONAS (ej. 'comercios del colector X agrupados por zonas'):
   - La ZONA de un comercio es su BARRIO: JOIN barrios br ON c.BARRIO = br.CODIGO
     → br.NOMBRE (los nombres están en la tabla barrios, no en contribu).
     Si no hay barrio con nombre, agrupá por CALLEFISCAL.
   - Nombre del colector: JOIN colector col ON c.COLECTOR = col.CODIGO
     → col.NOMBRE (contribu.COLECTOR es el CODIGO del colector).
   - Orden de visita dentro de cada zona: ORDER BY CALLEFISCAL, NUMEROFISCAL.
   - Hacé UNA consulta por zona (ej. TOP 6 zonas con más comercios) y exportá
     con exportar_listado → cada zona queda en su propia hoja/sección.
   - Columnas útiles de contribu: NOMENCLA, RAZONSOCI, CALLEFISCAL, NUMEROFISCAL,
     DNI, CUIT, COLECTOR, BARRIO, FECHAALTA, TELEFONO si existe (ver columnas_tabla).
   Datos útiles para otros listados:
   - Habilitaciones de comercio = ALTAS de cuentas de comercio: contribu con
     TIPOCONTRIBUYENTE='CO' y FECHAALTA en el período pedido.
   - Deudas: DWH_Deudas_Items_YYYYMM (fila más reciente por nomencla; TotalGral ya
     incluye interés salvo certificados: sumar InteresCertEjec).
   - Cobros: cobros ANULADO=0 y COBRADOR<>96 (el 96 es alumbrado interno, no recaudación).
6. TONO: profesional, cálido y claro. Español de Argentina. Respuestas concisas con
   formato legible (negritas con **, listas cuando aporten). Montos en pesos argentinos.
7. LÍMITES: no opines de política. No des asesoramiento legal definitivo: en temas
   legales o de cobro judicial, derivá a la oficina correspondiente de la municipalidad.
8. SIEMPRE respondé en español.
"""

# Ensamblar el protocolo de identidad según el modo (activo / prueba)
_SISTEMA_BASE = _SISTEMA_BASE.format(
    protocolo_identidad=_PROTOCOLO_IDENTIDAD_ACTIVO if _IDENTIDAD_ACTIVA
    else _PROTOCOLO_IDENTIDAD_PRUEBA)

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

    while intentos < 8:
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
                try:
                    resultado = herramientas.ejecutar(nombre, tc.function.arguments)
                    logger.info(f'tool {nombre} args={tc.function.arguments[:200]} → '
                                f'{str(resultado)[:200]}')
                except Exception as e:
                    logger.error(f'tool {nombre} FALLO: {e}')
                    resultado = {'error': f'Error al ejecutar {nombre}: {str(e)[:200]}'}
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

    return ('⚠️ No pude armar la respuesta con los datos disponibles. '
            'Reformulá la pregunta con el dato puntual que necesitás '
            '(ej: monto de hoy, un código, un período) y lo resuelvo.')


def limpiar_sesion(sesion_id):
    with _sesiones_lock:
        _sesiones.pop(sesion_id, None)
