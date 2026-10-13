# sigap-agent — Experto SIGAP Rawson 🤖

Agente conversacional experto en **SIGAP y la Municipalidad de Rawson**.
Combina un LLM (DeepSeek) con **datos reales en vivo** (sigap-mcp) y la
**base de conocimiento municipal** del proyecto SIGAP KPI (wiki + docs).

```
Usuario ──> sigap-agent (FastAPI :8200)
              ├── LLM DeepSeek (function calling)
              ├── Conocimiento municipal (RAG simple: .memory/wiki + docs de SIGAP KPI)
              └── Herramientas ──> sigap-mcp (:8100, token "agentes", solo lectura)
```

## 🚀 Ejecutar

```powershell
copy .env.example .env   # completar DEEPSEEK_API_KEY y SIGAP_MCP_TOKEN
py -3.12 -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8200
```

- **Chat web**: http://127.0.0.1:8200/
- **API**: `POST /api/chat` → `{mensaje, sesion_id?}` → `{sesion_id, respuesta}`
- PM2: `pm2 start ecosystem.config.js` (nombre `sigap-agent`)

## 🧠 Lo que sabe hacer

| Capacidad | Fuente |
|-----------|--------|
| Dónde está / cómo va un expediente (recorrido completo) | Herramienta → sigap-mcp |
| Deuda del padrón de un contribuyente (con verificación) | Herramienta → sigap-mcp |
| Recaudación, ejecución presupuestaria, KPIs ejecutivos | Herramienta → sigap-mcp |
| Analítica de expedientes (tiempos, backlog, sectores) | Herramienta → sigap-mcp |
| Cómo se calcula la deuda, tipos de boleta, planes de pago… | Conocimiento (wiki/docs) |
| Conversación con contexto (multi-turno, sesión de 1 h) | Historial en memoria |

## 🔒 Guardrails

- **Nunca inventa datos**: todo número sale de las herramientas o del conocimiento.
- **Privacidad**: no revela deuda/datos sin verificación de identidad del solicitante
  (Fase 2 agregará la verificación por DNI). Nunca datos de terceros.
- Sin opiniones políticas, sin asesoramiento legal definitivo.
- Rate limit por sesión (30 msg/min) · sesiones con TTL de 1 hora.

## 📁 Estructura

```
app/
├── main.py           → FastAPI (chat web + /api/chat)
├── agente.py         → loop LLM con function calling + sesiones + guardrails
├── conocimiento.py   → carga wiki/docs de SIGAP KPI + recuperación por palabras clave
├── herramientas.py   → 8 herramientas que consultan sigap-mcp (REST con token)
└── static/chat.html  → interfaz de chat
tests/test_agente.py  → 11 tests (LLM y herramientas mockeadas)
scripts/qa_live.py    → preguntas reales al agente contra SIGAP real
scripts/qa_chat.py    → validación del chat con Playwright
```

## 🔜 Fases siguientes

- **Fase 2**: verificación de identidad por DNI (nueva herramienta `buscar_por_dni`
  en sigap-mcp) antes de revelar deuda.
- **Fase 3**: conector WhatsApp (Meta Cloud API) + backoffice interno con más permisos.

## ⚙️ Configuración (.env)

| Variable | Descripción |
|----------|-------------|
| `DEEPSEEK_API_KEY` | API key de DeepSeek (OpenAI-compatible) |
| `DEEPSEEK_API_KEY_ALT` | Key alternativa (rotación) |
| `DEEPSEEK_MODEL` | `deepseek-chat` |
| `SIGAP_MCP_URL` | URL de sigap-mcp (default http://127.0.0.1:8100) |
| `SIGAP_MCP_TOKEN` | Token del cliente `agentes` (tokens.json de sigap-mcp) |
