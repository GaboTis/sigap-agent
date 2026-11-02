"""Base de conocimiento municipal del agente.

Carga la documentación experta del proyecto SIGAP KPI (wiki + docs) y del sitio
oficial del municipio (datos_municipio/), y recupera los fragmentos relevantes
para cada pregunta (RAG simple por palabras clave, sin dependencias externas).
"""
import unicodedata
from pathlib import Path

SIGAP_KPI = Path(r'C:\Users\User\Documents\CODE\SIGAPP KPI')
DATOS_MUNICIPIO = Path(__file__).resolve().parent.parent / 'datos_municipio'

# Archivos de conocimiento (curados) y su límite de caracteres.
_DOCS = [
    ('.memory/wiki/concepts/calculo-deuda.md', 6000),
    ('.memory/wiki/concepts/tipos-boleta.md', 5000),
    ('.memory/wiki/entities/contribuyente.md', 4000),
    ('.memory/wiki/entities/deuda.md', 5000),
    ('.memory/wiki/entities/plan-pago.md', 4000),
    ('.memory/wiki/entities/partida-presupuestaria.md', 4000),
    ('.memory/wiki/analisis-deuda.md', 8000),
    ('.memory/wiki/panel-ejecutivo.md', 8000),
    ('.memory/wiki/architecture.md', 5000),
    ('docs/MEJORAS_INGRESOS_19DIC2025.md', 6000),
    ('docs/Analisis_Base_Datos_SIGAP.md', 9000),
    ('design/PRODUCT.md', 5000),
]

# Documentos del sitio oficial del municipio (datos_municipio/).
_DOCS_MUNICIPIO = [
    ('autoridades_y_contacto.md', 9000),
]

# Perfil institucional inyectado siempre en el prompt del agente.
PERFIL_MUNICIPAL = """\
Municipalidad de Rawson, provincia de San Juan, Argentina.
SIGAPP es el sistema de gestión tributaria y administrativa del municipio (561 tablas
en SQL Server): boletas, cobros, planes de pago, certificados de ejecución, contribu
(padrón de contribuyentes), expediente/expemovi (sistema de expedientes), sectmuni
(sectores municipales), ordencpa/reciteso/proveedor (compras y pagos a proveedores),
stock, partidas presupuestarias y snapshots DWH del padrón de deuda (uno por mes).
Tipos de contribuyente: IM (inmuebles), CO (comercios), CM (cementerio), CG (comercio
general), MA (maquinaria), PT (patentes), JF (jubilados/familia), DC (derechos).
Los expedientes se identifican como NUMERO-LETRA/AÑO (ej. 3540-S-2026) y sus estados
son: EN CURSO (códigos E e I), PAGADO/CANCELADO (P), CERRADO (C) y ARCHIVO (A).
El recorrido entre sectores queda registrado en expemovi con fecha, usuario y sector
de origen/destino.
LISTADOS DE EXPEDIENTES: cuando pidan un LISTADO (ej. "expedientes de contratos en
curso", "los más antiguos", "cuántos hay de obra pública"), usar SIEMPRE la
herramienta listar_expedientes: el TEMA se filtra sobre MOTIVO del expediente
(ej. "contrat" cubre contratos, contratación, contrataciones; probar también
variantes cortas: "licit", "obra", "plan de pago"). Por defecto muestra EN CURSO
ordenados por ANTIGÜEDAD (fecha de inicio más vieja primero; las fechas sin cargar
aparecen al final como "sin fecha"). Si piden TODOS los estados → estado="todos".
Para EXPORTAR A EXCEL un listado de expedientes usar exportar_listado con una
consulta como:
  SELECT NUMERO, LETRA, ANO, FECHAINICIO, MOTIVO, TIPOEXPEDIENTE, ESTADO,
         SECTACTUAL, INICIADOR
  FROM expediente
  WHERE ANULADO=0 AND ESTADO IN ('E','I') AND MOTIVO LIKE '%CONTRAT%'
  ORDER BY FECHAINICIO ASC
(ajustar filtro MOTIVO y ESTADO al pedido; con LIMIT se acota si lo piden).

ORÁCULO DE LA BASE DE DATOS — cómo responder CUALQUIER pregunta de datos:
1) Si la pregunta menciona un TEMA (gastos, cobros, pagos, compras, deuda,
   expedientes, proveedores…), primero usar buscar_esquema(tema) para ubicar la
   tabla correcta (devuelve qué es cada tabla y sus columnas clave).
2) Confirmar columnas con esquema_tabla(tabla) si hay dudas.
3) Ejecutar con ejecutar_consulta o ejecutar_consultas (batch para varios números).
   Reglas de SQL: SIEMPRE filtrar ANULADO=0 cuando la tabla tenga esa columna;
   acotar fechas (ej. FECHA>='2026-10-01'); TOP 50 para listados; para resultados
   ORDENADOS usar el patrón: SELECT TOP 50 * FROM (SELECT TOP 100000 ... ORDER BY X) t.
4) Responder con los NÚMEROS REALES devueltos, en tabla cuando haya varios, con
   la fuente (tabla). Si la DB no tiene el dato, decirlo claramente y sugerir qué
   sí se puede consultar. Nunca inventar cifras.
Mapa rápido de tablas por dominio:
- DEUDAS: boletas (emitidas), inticomp (intereses), planpago/plpgcuot (planes),
  certejec/certejcomp (certificados de ejecución), intima, libredeuda, DWH_Deudas_Items_*
  (foto mensual del padrón — la deuda oficial por contribuyente se pide con
  deuda_contribuyente, no con SQL).
- COBROS/RECAUDACIÓN: cobros (cada cobro, TOTALGRAL), cobritem (boletas pagadas),
  recibo, cobrfpag (medios de pago: FPAGO, cheques/tarjetas), cobrosweb (web/MP),
  saldoscaja. Colector=COBRADOR, cajero=CAJERO.
- PAGOS/TESORERÍA: ordenpago (órdenes de pago), reciteso (recibos de tesorería),
  cheques, depositos, anticipos.
- CONTABILIDAD/COMPRAS: ordencpa+ocpaitem (órdenes de compra), proveedor,
  factprove/factuprov (facturas de proveedores), fpago (formas de compra, catálogo
  con rangos y normas), partidas (presupuesto: IMPORTEINICIAL/SALDOACTUAL/PREVENTPTE/
  AFECTACPTE/DEFINITPTE/MANDPAGPTE), parteegre (gastos imputados), parteingre
  (ingresos imputados), imputdef/imputprev, articulo, fpgespcomp (comprobantes de
  gastos), anticipos, asientos (contabilidad formal casi sin carga).
- EXPEDIENTES: expediente (estado E/I en curso), expemovi (recorrido),
  estaexpe/tipoexpe/sectmuni (catálogos).
- PADRÓN: contribu (RAZONSOCI, DNI, CUIT, domicilio), datospers (tel/mail),
  persona/personajuridica.
Recetas frecuentes:
- "cuánto se recaudó hoy": SELECT SUM(TOTALGRAL) FROM cobros WHERE ANULADO=0 AND FECHA>=CONVERT(date,GETDATE())
- "recaudado por medio de pago": SELECT FPAGO, SUM(TOTALGRAL) FROM cobros WHERE ANULADO=0 AND FECHA>='…' GROUP BY FPAGO (JOIN fpago por DESCRIPCION).
- "por colector": SELECT COBRADOR, COUNT(*), SUM(TOTALGRAL) FROM cobros … GROUP BY COBRADOR.
- "cuánto pagamos a proveedores": SELECT SUM(TOTAL) FROM ordenpago WHERE ANULADO=0 AND FECHA>='…' (o reciteso.IMPORTE).
- "gastos del mes": SELECT SUM(IMPORTE) FROM parteegre WHERE NROPARTE=… (parte mensual) o por CONCEPTO GROUP BY.
- "estado del presupuesto": SELECT CUENTA, DESCRIPCION, IMPORTEINICIAL, SALDOACTUAL FROM partidas WHERE ANO=2026.

VENCIMIENTOS DE BOLETAS (esquema de la tabla boletas):
- Cada boleta tiene hasta 3 vencimientos embebidos: FECHAVTO1/IMPORTE1 (base,
  sin recargo), FECHAVTO2/IMPORTE2/RECARGO2/TASA2, FECHAVTO3/IMPORTE3/RECARGO3/
  TASA3 (la columna FECHAVTO0/IMPORTE0/DESCTO0 es el pago adelantado con descuento).
- Recargo del vencimiento = IMPORTE1 × (TASA/100) × días desde FECHAVTO1.
  TASA2=TASA3=0.150 → 0,15% diario (≈4,5% mensual) de recargo escalonado,
  distinto del interés resarcitorio (tipocontriinteresas: 10% mensual antes de
  2017, 15% mensual desde 2017; códigos IP/PP/R/V).
- CUOTA MENSUAL (TIPOBOLETA='P', UNICACUOTA=0): 2023-2024 traía 3 vencimientos
  (VTO2 a los ~6-7 días, VTO3 ~7 días después). Desde 2025 el VTO3 se dejó de
  emitir: hoy tiene 2 vencimientos (base y recargo).
- CUOTA ANUAL (UNICACUOTA=1, MES=1): UN SOLO vencimiento (FECHAVTO1), sin
  recargos VTO2/VTO3. Son las tasas anuales (ej. concesiones de cementerio CM).

RÉGIMEN DE CONTRATACIONES Y COMPRAS (tabla SIGAP: fpago — cada forma de compra tiene
rango DESDE/HASTA y su norma en NORMALEGAL). Régimen vigente actualizado por
O.861-I(3A)-D1708/25 (administración general) y O.861-I(3B)-D1708/25 (obras y
servicios públicos):
- Contratación/compra DIRECTA general: desde $0,01 hasta $20.000.000 (código 293)
- Compulsa abreviada: desde $20.000.000 hasta $30.000.000 (obras: hasta $40.000.000)
- Licitación privada: hasta $40.000.000 (obras: hasta $59.000.000)
- Licitación pública: montos mayores, sin tope
- Compra directa de bienes de capital, combustibles y lubricantes: hasta $20.000.000
Existen excepciones puntuales (Ord. 683-I-23 art. 14, ley 2000-A) con montos mayores;
verificar el caso puntual en fpago. Para confirmar el dato EXACTO en el sistema,
consultar: SELECT codigo, DESCRIPCION, DESDE, HASTA, NORMALEGAL FROM fpago
WHERE DESCRIPCION LIKE '%DIRECTA%' AND (NORMALEGAL LIKE '%1708%' OR NORMALEGAL LIKE '%861%')

INTERESES POR MORA (tabla tipocontri, columnas INTERESRESAR/INTERESVALORES/
INTERESPLANPAGO, INTERESTIPO='D' = diario). Tasas mensuales vigentes por tipo:
IM, CO, CM, CG y PN: 15% · DC y JF: 10% · PT: 6,6% · MA: 0%.
La deuda de una boleta = IMPORTE NOMINAL + interés devengado desde el vencimiento
hasta hoy − descuentos (pago en término, jubilados). La deuda total incluye además
planes de pago (cuotas menos lo pagado), certificados de ejecución y notas de crédito
en contra. El portal de pagos (municipioonline.com.ar, m=rawson) muestra ese mismo
cálculo del motor SIGAP: columnas IMPORTE NOMINAL, INTERES, DTO y TOTAL por boleta.
"""

_STOPWORDS = {
    'que', 'como', 'cuando', 'donde', 'para', 'por', 'con', 'los', 'las', 'del',
    'una', 'uno', 'mi', 'mis', 'tengo', 'hay', 'mas', 'esa', 'ese', 'eso',
    'el', 'la', 'de', 'en', 'y', 'o', 'a', 'se', 'es', 'no', 'si', 'ya',
}


def _normalizar(texto):
    """Minúsculas y sin acentos, para comparar términos."""
    texto = unicodedata.normalize('NFKD', str(texto or ''))
    return ''.join(c for c in texto if not unicodedata.combining(c)).lower()


def _cargar_documentos():
    docs = []
    for rel, limite in _DOCS:
        ruta = SIGAP_KPI / rel
        if not ruta.exists():
            continue
        texto = ruta.read_text(encoding='utf-8', errors='replace')
        if len(texto) > limite:
            texto = texto[:limite] + '\n…(documento truncado)…'
        docs.append({
            'titulo': ruta.name.replace('.md', '').replace('-', ' ').title(),
            'ruta': rel,
            'texto': texto,
            'norm': _normalizar(texto),
        })
    # Sitio oficial del municipio (fuente: municipioderawson.gob.ar)
    for nombre, limite in _DOCS_MUNICIPIO:
        ruta = DATOS_MUNICIPIO / nombre
        if not ruta.exists():
            continue
        texto = ruta.read_text(encoding='utf-8', errors='replace')
        if len(texto) > limite:
            texto = texto[:limite] + '\n…'
        docs.append({
            'titulo': 'Sitio Oficial — ' + nombre.replace('.md', '').replace('_', ' ').title(),
            'ruta': f'datos_municipio/{nombre}',
            'texto': texto,
            'norm': _normalizar(texto),
        })
    return docs


_DOCS_CARGADOS = _cargar_documentos()


def buscar_conocimiento(pregunta, top=2, max_chars=3000):
    """Recupera los documentos más relevantes para la pregunta."""
    if not pregunta.strip() or not _DOCS_CARGADOS:
        return []
    terminos = [t for t in _normalizar(pregunta).split() if len(t) >= 3 and t not in _STOPWORDS]
    if not terminos:
        return []

    puntajes = []
    for doc in _DOCS_CARGADOS:
        score = 0
        titulo_norm = _normalizar(doc['titulo'])
        for t in terminos:
            if t in titulo_norm:
                score += 6  # bonus por título
            score += doc['norm'].count(t)
        if score > 0:
            puntajes.append((score, doc))
    puntajes.sort(key=lambda x: -x[0])

    resultados = []
    for score, doc in puntajes[:top]:
        texto = doc['texto']
        if len(texto) > max_chars:
            texto = texto[:max_chars] + '\n…'
        resultados.append(f"### {doc['titulo']}\n{texto}")
    return resultados
