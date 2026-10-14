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
son: EN CURSO, PAGADO/CANCELADO, CERRADO y ARCHIVO. El recorrido entre sectores queda
registrado en expemovi con fecha, usuario y sector de origen/destino.
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
