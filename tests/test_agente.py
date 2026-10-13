"""Tests del agente con LLM y herramientas mockeadas."""
import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import agente, conocimiento, herramientas


# ── Conocimiento ──────────────────────────────────────────────

def test_carga_documentos():
    docs = conocimiento._DOCS_CARGADOS
    assert len(docs) >= 8, 'debería cargar los documentos del wiki/docs'


def test_buscar_conocimiento_relevante():
    res = conocimiento.buscar_conocimiento('cómo se calcula la deuda de tasas')
    assert res, 'debería encontrar documentos de cálculo de deuda'
    assert any('deuda' in r.lower() for r in res)


def test_buscar_conocimiento_sin_pregunta():
    assert conocimiento.buscar_conocimiento('') == []


# ── Herramientas (mock de sigap-mcp) ──────────────────────────

def test_ejecutar_herramienta_conocida():
    with patch('app.herramientas._get', return_value={'total': 1, 'resultados': [
            {'numero': 3540, 'letra': 'S', 'ano': 2026, 'fecha_inicio': '09/04/2026',
             'estado_desc': 'Pagado/Cancelado', 'sector_actual': 'TEST', 'tipo': 'NOTAS',
             'motivo': 'TEST'}]}):
        r = herramientas.buscar_expediente('3540-S-2026')
    assert r['total'] == 1
    assert r['resultados'][0]['expediente'] == '3540-S/2026'


def test_ejecutar_herramienta_desconocida():
    r = herramientas.ejecutar('no_existe', {})
    assert 'error' in r


def test_ejecutar_herramienta_con_error():
    with patch('app.herramientas._get', side_effect=Exception('DB caída')):
        r = herramientas.ejecutar('recaudacion', {})
    assert 'error' in r
    assert 'DB caída' in r['error']


# ── Agente (LLM mockeado) ─────────────────────────────────────

class Msg:
    def __init__(self, content='', tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or []


class Choice:
    def __init__(self, msg):
        self.message = msg


class Resp:
    def __init__(self, msg):
        self.choices = [Choice(msg)]


def test_responder_sin_herramientas():
    fake = MagicMock()
    fake.chat.completions.create.return_value = Resp(Msg('Hola, ¿en qué te ayudo?'))
    with patch.object(agente, '_cliente', fake):
        r = agente.responder('test-1', 'hola')
    assert 'Hola' in r


def test_responder_con_llamada_a_herramienta():
    llamada = MagicMock()
    llamada.id = 'call_1'
    llamada.function.name = 'recaudacion'
    llamada.function.arguments = '{}'

    respuestas = [
        Resp(Msg(content='', tool_calls=[llamada])),          # 1°: pide herramienta
        Resp(Msg('Recaudación del mes: $82 millones')),        # 2°: responde
    ]
    fake = MagicMock()
    fake.chat.completions.create.side_effect = respuestas

    with patch.object(agente, '_cliente', fake), \
            patch('app.herramientas.ejecutar', return_value={'mes': {'monto': 82000000}}):
        r = agente.responder('test-2', 'cuánto se recaudó')
    assert '82 millones' in r


def test_responder_mantiene_contexto_de_sesion():
    fake = MagicMock()
    fake.chat.completions.create.return_value = Resp(Msg('ok'))
    with patch.object(agente, '_cliente', fake):
        agente.responder('ses-1', 'primera pregunta')
        llamada = fake.chat.completions.create.call_args_list[-1]
        mensajes = llamada.kwargs['messages']
        roles = [m['role'] for m in mensajes]
        assert roles[-1] == 'user'
        assert any(m['content'] == 'primera pregunta' for m in mensajes)


def test_responder_error_llm():
    fake = MagicMock()
    fake.chat.completions.create.side_effect = Exception('API key inválida')
    with patch.object(agente, '_cliente', fake):
        r = agente.responder('test-3', 'hola')
    assert 'problema' in r.lower()


def test_responder_respeta_privacidad_en_sistema():
    """El prompt del sistema debe incluir la regla de verificación de identidad."""
    with patch.object(agente, '_cliente', MagicMock(return_value=None)):
        pass
    mensajes = agente._con_sistema('dame la deuda de tal')
    sistema = mensajes[0]['content']
    assert 'verific' in sistema.lower()
    assert 'terceros' in sistema.lower()
