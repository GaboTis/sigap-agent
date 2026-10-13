"""Experto SIGAP Rawson — API y chat web.

Uso:
    uvicorn app.main:app --host 127.0.0.1 --port 8200
    Chat web: http://127.0.0.1:8200/
"""
import os
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from app import agente

load_dotenv()

app = FastAPI(title='Experto SIGAP Rawson', version='0.1.0')


class ChatIn(BaseModel):
    mensaje: str
    sesion_id: str | None = None


@app.get('/')
def chat_web():
    return FileResponse(Path(__file__).parent / 'static' / 'chat.html')


@app.get('/api/health')
def health():
    return {'status': 'ok', 'servicio': 'experto-sigap', 'modelo': os.getenv('DEEPSEEK_MODEL', 'deepseek-chat')}


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
