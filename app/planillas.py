"""Generación de planillas Excel para el agente (openpyxl).

El agente arma listados a pedido del usuario: ejecuta las consultas (vía
sigap-mcp /api/consulta/exportar, tope amplio) y escribe un .xlsx en
exportes/ con una hoja por consulta, encabezados destacados y filtros.
"""
import logging
import re
import time
from pathlib import Path

logger = logging.getLogger('sigap.planillas')

_EXPORTES = Path(__file__).resolve().parent.parent / 'exportes'
_BASE_URL = 'http://127.0.0.1:8200'

# Caracteres de control que openpyxl NO acepta en celdas (los datos viejos de
# SIGAP los traen embebidos en MOTIVO/TEMA, ej. \x05).
_CONTROL = re.compile(r'[\x00-\x08\x0b-\x0c\x0e-\x1f]')


def _limpiar(val):
    """Convierte cualquier valor a texto limpio apto para Excel."""
    if val is None:
        return ''
    s = str(val)
    return _CONTROL.sub(' ', s)


def ruta_exportes():
    _EXPORTES.mkdir(parents=True, exist_ok=True)
    return _EXPORTES


def _nombre_seguro(nombre):
    base = (nombre or 'listado').strip() or 'listado'
    base = re.sub(r'[^A-Za-z0-9_-]+', '_', base).strip('_')[:60] or 'listado'
    if not base.lower().endswith('.xlsx'):
        base += '.xlsx'
    return base


def generar_planilla(titulo, resultados, nombre_archivo):
    """Escribe un .xlsx con los resultados de las consultas.

    resultados: lista de {columnas, filas, indice} (solo las ok).
    Devuelve {archivo, url, hojas, filas}.
    """
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    if not resultados:
        raise ValueError('No hay resultados para exportar.')

    nombre = _nombre_seguro(nombre_archivo)
    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    total_filas = 0
    for res in resultados:
        columnas = [str(c or '') for c in res.get('columnas', [])]
        filas = res.get('filas', [])
        if not columnas:
            continue
        hoja = wb.create_sheet(f'Listado {res.get("indice", len(wb.worksheets) + 1)}'[:31])
        # Título
        hoja.append([titulo or 'Listado'])
        hoja.merge_cells(start_row=1, start_column=1,
                         end_row=1, end_column=max(1, len(columnas)))
        hoja['A1'].font = Font(bold=True, size=12, color='0F172A')
        hoja['A1'].alignment = Alignment(vertical='center')
        hoja.row_dimensions[1].height = 20
        # Encabezados
        hoja.append(columnas)
        for col in range(1, len(columnas) + 1):
            celda = hoja.cell(row=2, column=col)
            celda.font = Font(bold=True, color='FFFFFF')
            celda.fill = PatternFill('solid', fgColor='1E3A8A')
            celda.alignment = Alignment(vertical='center')
        # Filas (sanitizadas: los datos viejos de SIGAP traen caracteres de control)
        for fila in filas:
            hoja.append([_limpiar(v) for v in fila])
        total_filas += len(filas)
        # Ancho de columnas automático (acotado)
        for col in range(1, len(columnas) + 1):
            ancho = min(40, max(10, len(columnas[col - 1]) + 2))
            for fila in filas[:80]:
                v = fila[col - 1] if col - 1 < len(fila) else None
                if v is not None:
                    ancho = max(ancho, min(40, len(str(v)) + 2))
            hoja.column_dimensions[get_column_letter(col)].width = ancho
        hoja.freeze_panes = 'A3'
        hoja.auto_filter.ref = f'A2:{get_column_letter(len(columnas))}{len(filas) + 2}'

    ruta = ruta_exportes() / nombre
    wb.save(ruta)
    return {
        'archivo': nombre,
        'url': f'{_BASE_URL}/exportes/{nombre}',
        'hojas': len(wb.sheetnames),
        'filas': total_filas,
    }


def generar_pdf(titulo, resultados, nombre_archivo):
    """Escribe un .pdf con los resultados (una sección por consulta).

    Tabla horizontal (landscape) si hay varias columnas; celda con salto de
    línea si el texto no entra. Devuelve {archivo, url, paginas, filas}.
    """
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (Paragraph, SimpleDocTemplate, Spacer, Table,
                                    TableStyle)

    if not resultados:
        raise ValueError('No hay resultados para exportar.')

    nombre = _nombre_seguro(nombre_archivo)
    if nombre.lower().endswith('.xlsx'):
        nombre = nombre[:-5] + '.pdf'
    ruta = ruta_exportes() / nombre

    estilos = getSampleStyleSheet()
    total_cols = max((len(r.get('columnas', [])) for r in resultados), default=1)
    horizontal = total_cols >= 6
    doc = SimpleDocTemplate(
        str(ruta), pagesize=landscape(A4) if horizontal else A4,
        leftMargin=12 * mm, rightMargin=12 * mm, topMargin=12 * mm, bottomMargin=12 * mm,
        title=titulo or 'Listado')

    historia = []
    historia.append(Paragraph(titulo or 'Listado', estilos['Title']))
    historia.append(Spacer(1, 4 * mm))

    total_filas = 0
    for res in resultados:
        columnas = [str(c or '') for c in res.get('columnas', [])]
        filas = res.get('filas', [])
        if not columnas:
            continue
        estilo_tit = estilos['Heading3']
        historia.append(Paragraph(f'Zona {res.get("indice", len(historia))} '
                                  f'— {len(filas)} comercios', estilo_tit))
        historia.append(Spacer(1, 2 * mm))
        datos = [columnas] + [[Paragraph(_limpiar(v), estilos['BodyText']) for v in fila]
                              for fila in filas]
        ancho_col = doc.width / len(columnas)
        tabla = Table(datos, colWidths=[ancho_col] * len(columnas), repeatRows=1)
        tabla.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E3A8A')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTSIZE', (0, 0), (-1, 0), 7.5),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 1), (-1, -1), 7),
            ('GRID', (0, 0), (-1, -1), 0.3, colors.HexColor('#CBD5E1')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 3),
            ('RIGHTPADDING', (0, 0), (-1, -1), 3),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8FAFC')]),
        ]))
        historia.append(tabla)
        historia.append(Spacer(1, 6 * mm))
        total_filas += len(filas)

    doc.build(historia)
    return {
        'archivo': nombre,
        'url': f'{_BASE_URL}/exportes/{nombre}',
        'paginas': doc.page,
        'filas': total_filas,
    }


def generar_exporte(titulo, resultados, nombre_archivo, formato='xlsx'):
    """Genera la planilla en el formato pedido: 'xlsx' (Excel) o 'pdf'."""
    if (formato or 'xlsx').lower() == 'pdf':
        return generar_pdf(titulo, resultados, nombre_archivo)
    return generar_planilla(titulo, resultados, nombre_archivo)
