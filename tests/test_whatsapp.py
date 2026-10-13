"""Tests del conector WhatsApp (webhook Meta)."""
import hashlib
import hmac
import json
import sys
import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import whatsapp
from app.main import app


def _payload(texto, tipo='text'):
    return {
        'object': 'whatsapp_business_account',
        'entry': [{'id': '1', 'changes': [{
            'value': {
                'messaging_product': 'whatsapp',
                'metadata': {'display_phone_number': '5492641', 'phone_number_id': '99'},
                'contacts': [{'profile': {'name': 'X'}, 'wa_id': '549111'}],
                'messages': [{'from': '549111', 'id': 'w1', 'timestamp': '1',
                              'type': tipo,
                              'text': {'body': texto} if tipo == 'text' else {}}],
            },
            'field': 'messages',
        }]}]}


def test_verificar_firma_valida():
    with patch.object(whatsapp, 'WA_APP_SECRET', 'secreto'):
        body = b'{"a":1}'
        firma = 'sha256=' + hmac.new(b'secreto', body, hashlib.sha256).hexdigest()
        assert whatsapp.verificar_firma(body, firma) is True


def test_verificar_firma_invalida():
    with patch.object(whatsapp, 'WA_APP_SECRET', 'secreto'):
        assert whatsapp.verificar_firma(b'{"a":1}', 'sha256=abc') is False


def test_verificar_firma_sin_secret_configurado():
    with patch.object(whatsapp, 'WA_APP_SECRET', ''):
        assert whatsapp.verificar_firma(b'{"a":1}', '') is True


def test_manejar_mensaje_texto():
    enviados = []
    with patch.object(whatsapp, '_enviar', side_effect=lambda w, t: enviados.append((w, t))), \
            patch.object(whatsapp.agente, 'responder', return_value='respuesta de prueba'):
        r = whatsapp.manejar_webhook(_payload('hola'))
    assert r['procesados'] == 1
    assert enviados == [('549111', 'respuesta de prueba')]


def test_manejar_mensaje_no_texto():
    enviados = []
    with patch.object(whatsapp, '_enviar', side_effect=lambda w, t: enviados.append(t)):
        r = whatsapp.manejar_webhook(_payload('', tipo='image'))
    assert r['procesados'] == 1
    assert 'texto' in enviados[0]


def test_manejar_update_estado_se_ignora():
    payload = {'object': 'whatsapp_business_account',
               'entry': [{'id': '1', 'changes': [{'value': {
                   'messaging_product': 'whatsapp', 'statuses': [{'status': 'delivered'}]},
                   'field': 'messages'}]}]}
    with patch.object(whatsapp, '_enviar') as fake:
        r = whatsapp.manejar_webhook(payload)
    assert r['procesados'] == 0
    fake.assert_not_called()


def test_webhook_verificacion_get():
    client = TestClient(app)
    with patch.object(whatsapp, 'WA_VERIFY_TOKEN', 'tok123'):
        r = client.get('/webhook/whatsapp', params={
            'hub.mode': 'subscribe', 'hub.verify_token': 'tok123', 'hub.challenge': '777'})
        assert r.status_code == 200
        assert r.json() == 777


def test_webhook_verificacion_token_incorrecto():
    client = TestClient(app)
    with patch.object(whatsapp, 'WA_VERIFY_TOKEN', 'tok123'):
        r = client.get('/webhook/whatsapp', params={
            'hub.mode': 'subscribe', 'hub.verify_token': 'mal', 'hub.challenge': '777'})
        assert r.status_code == 403


def test_webhook_post_procesa():
    client = TestClient(app)
    with patch.object(whatsapp, 'WA_APP_SECRET', ''), \
            patch.object(whatsapp, '_enviar') as fake, \
            patch.object(whatsapp.agente, 'responder', return_value='hola vecino'):
        r = client.post('/webhook/whatsapp', json=_payload('consulta'))
    assert r.status_code == 200
    assert r.json()['procesados'] == 1
    fake.assert_called_once()


def test_webhook_post_firma_invalida():
    client = TestClient(app)
    with patch.object(whatsapp, 'WA_APP_SECRET', 'secreto'):
        r = client.post('/webhook/whatsapp', content=json.dumps(_payload('x')),
                        headers={'x-hub-signature-256': 'sha256=incorrecta'})
    assert r.status_code == 401
