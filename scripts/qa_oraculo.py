"""Batería de preguntas del Oráculo por dominio (agente local 8225)."""
import json
import time
import urllib.request

AGENTE = 'http://127.0.0.1:8225/api/chat'

PREGUNTAS = [
    ('cobros', '¿Cuánto se recaudó hoy en la municipalidad?'),
    ('contabilidad', '¿Cuánto gastó el municipio en compras en octubre de 2026?'),
    ('pagos', '¿Cuánto se pagó a proveedores en lo que va de 2026?'),
    ('cobros-medios', '¿Por qué medios de pago cobró la municipalidad hoy?'),
    ('deudas', '¿Cuál es la deuda total actual del padrón de contribuyentes?'),
]

for nombre, pregunta in PREGUNTAS:
    t0 = time.time()
    try:
        req = urllib.request.Request(
            AGENTE,
            data=json.dumps({'mensaje': pregunta, 'sesion_id': f'qa-oraculo-{nombre}'}).encode(),
            headers={'Content-Type': 'application/json'},
        )
        with urllib.request.urlopen(req, timeout=300) as r:
            d = json.loads(r.read().decode())
        resp = (d.get('respuesta') or '').strip()
        ok = 'No pude armar la respuesta' not in resp
        print(f'\n{"="*70}\n[{nombre}] {pregunta}\n{"="*70}')
        print(resp[:900])
        print(f'\n→ estado: {"OK" if ok else "FALLBACK"} · {round(time.time()-t0,0)}s')
    except Exception as e:
        print(f'\n[{nombre}] ERROR: {e}')
