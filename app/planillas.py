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
        # Filas
        for fila in filas:
            hoja.append(list(fila))
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
