"""Conector WhatsApp Cloud API (Meta Graph API).

Flujo:
    Vecino escribe → Meta envía webhook POST /webhook/whatsapp →
    extraemos mensajes → sesión por número (wa_id) → agente responde →
    enviamos la respuesta vía Graph API (v23.0/<phone_number_id>/messages).

Seguridad:
- Verificación del webhook: GET con hub.verify_token (WHATSAAPP_VERIFY_TOKEN).
- Firma HMAC: X-Hub-Signature-256 con WHATSAPP_APP_SECRET (si está configurada).
- Respuestas no plantilla: solo dentro de la ventana de servicio de 24 h
  (Meta no deja responder plantillas desde acá — el agente siempre responde
  conversacional, lo cual es válido dentro de la ventana).
"""
import hashlib
import hmac
import json
import logging
import os

import httpx
from dotenv import load_dotenv

from app import agente

load_dotenv()
logger = logging.getLogger('sigap.whatsapp')

GRAPH_URL = 'https://graph.facebook.com/v23.0'
WA_TOKEN = os.getenv('WHATSAPP_TOKEN', '')
WA_PHONE_ID = os.getenv('WHATSAPP_PHONE_NUMBER_ID', '')
WA_VERIFY_TOKEN = os.getenv('WHATSAPP_VERIFY_TOKEN', '')
WA_APP_SECRET = os.getenv('WHATSAPP_APP_SECRET', '')

# ── Sesión por número de WhatsApp ─────────────────────────────
def _sesion_de(wa_id):
    return f'wa-{wa_id}'


def verificar_firma(payload_bytes, firma):
    """Valida X-Hub-Signature-256 (si hay APP_SECRET configurado)."""
    if not WA_APP_SECRET:
        return True  # sin secret configurado → no se valida firma (modo prueba)
    if not firma:
        return False
    esperado = hmac.new(WA_APP_SECRET.encode(), payload_bytes, hashlib.sha256).hexdigest()
    recibido = firma.replace('sha256=', '')
    return hmac.compare_digest(esperado, recibido)


def _enviar(wa_id, texto):
    """Envía un mensaje de texto vía Graph API."""
    if not WA_TOKEN or not WA_PHONE_ID:
        logger.warning('WHATSAPP_TOKEN/PHONE_NUMBER_ID sin configurar — mensaje no enviado.')
        return {'error': 'configuración incompleta'}
    resp = httpx.post(
        f'{GRAPH_URL}/{WA_PHONE_ID}/messages',
        headers={'Authorization': f'Bearer {WA_TOKEN}', 'Content-Type': 'application/json'},
        json={'messaging_product': 'whatsapp', 'recipient_type': 'individual',
              'to': wa_id, 'type': 'text',
              'text': {'body': texto[:4000], 'preview_url': False}},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def _procesar_mensaje(wa_id, tipo, cuerpo):
    """Un mensaje entrante → respuesta del agente → envío por WhatsApp."""
    if tipo != 'text':
        _enviar(wa_id, 'Por ahora solo puedo leer mensajes de texto. Escribime tu consulta 🙌')
        return
    texto = (cuerpo or '').strip()
    if not texto:
        return
    logger.info(f'Mensaje de {wa_id}: {texto[:100]}')
    respuesta = agente.responder(_sesion_de(wa_id), texto)
    _enviar(wa_id, respuesta)


def manejar_webhook(payload):
    """Procesa el payload de Meta (object: whatsapp_business_account)."""
    if payload.get('object') != 'whatsapp_business_account':
        return {'recibido': False, 'motivo': 'object no reconocido'}

    procesados = 0
    for entry in payload.get('entry', []):
        for change in entry.get('changes', []):
            value = change.get('value', {})
            if change.get('field') != 'messages':
                continue
            if 'messages' not in value:
                continue  # estado (read/delivered) — ignorar
            wa_id = (value.get('contacts') or [{}])[0].get('wa_id', '')
            for msg in value.get('messages', []):
                if msg.get('from'):
                    wa_id = msg['from']
                tipo = msg.get('type', '')
                cuerpo = (msg.get('text') or {}).get('body', '')
                try:
                    _procesar_mensaje(wa_id, tipo, cuerpo)
                    procesados += 1
                except Exception as e:
                    logger.error(f'Error procesando mensaje de {wa_id}: {e}')
                    try:
                        _enviar(wa_id, '⚠️ Tuvimos un problema procesando tu mensaje. '
                                       'Intentá de nuevo en unos segundos.')
                    except Exception:
                        pass
    return {'recibido': True, 'procesados': procesados}
