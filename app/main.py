"""Experto SIGAPP Rawson — API y chat web.

Uso:
    uvicorn app.main:app --host 127.0.0.1 --port 8200
    Chat web: http://127.0.0.1:8200/
"""
import json
import os
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app import agente, planillas, whatsapp

load_dotenv()

app = FastAPI(title='Experto SIGAPP Rawson', version='0.2.0')

# Descarga de planillas generadas por el agente
app.mount('/exportes', StaticFiles(directory=str(planillas.ruta_exportes())),
          name='exportes')


class ChatIn(BaseModel):
    mensaje: str
    sesion_id: str | None = None


@app.get('/')
def chat_web():
    return FileResponse(Path(__file__).parent / 'static' / 'chat.html')


@app.get('/api/health')
def health():
    return {'status': 'ok', 'servicio': 'experto-sigap', 'modelo': os.getenv('DEEPSEEK_MODEL', 'deepseek-chat')}


# ── Webhook de WhatsApp Cloud API (Meta) ──────────────────────
@app.get('/webhook/whatsapp')
def webhook_verificar(request: Request):
    """Verificación inicial de Meta: hub.mode + hub.verify_token + hub.challenge."""
    modo = request.query_params.get('hub.mode')
    token = request.query_params.get('hub.verify_token')
    challenge = request.query_params.get('hub.challenge')
    if modo == 'subscribe' and whatsapp.WA_VERIFY_TOKEN and token == whatsapp.WA_VERIFY_TOKEN:
        return int(challenge or 0)
    return JSONResponse(status_code=403, content={'error': 'verify_token inválido'})


@app.post('/webhook/whatsapp')
async def webhook_mensajes(request: Request):
    """Recepción de mensajes (con validación de firma HMAC)."""
    body = await request.body()
    firma = request.headers.get('x-hub-signature-256', '')
    if not whatsapp.verificar_firma(body, firma):
        return JSONResponse(status_code=401, content={'error': 'firma inválida'})
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return JSONResponse(status_code=400, content={'error': 'JSON inválido'})
    resultado = whatsapp.manejar_webhook(payload)
    return resultado


@app.post('/api/chat')
def chat(body: ChatIn, request: Request):
    mensaje = (body.mensaje or '').strip()
    if not mensaje:
        return JSONResponse(status_code=400, content={'error': 'Mensaje vacío'})
    if len(mensaje) > 2000:
        return JSONResponse(status_code=400, content={'error': 'Mensaje demasiado largo'})

    sesion_id = (body.sesion_id or '').strip() or uuid.uuid4().hex[:12]
    respuesta = agente.responder(sesion_id, mensaje)
    return {'sesion_id': sesion_id, 'respuesta': respuesta}


@app.post('/api/chat/nueva')
def nueva_sesion():
    return {'sesion_id': uuid.uuid4().hex[:12]}
