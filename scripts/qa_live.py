"""QA en vivo del agente — preguntas reales a DeepSeek + sigap-mcp."""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import agente

PREGUNTAS = [
    ('¿Dónde está el expediente 3540-S-2026?', 'expediente'),
    ('¿Cuánto recaudó el municipio este mes y cómo viene vs el año pasado?', 'recaudacion'),
    ('¿Cómo se calcula la deuda de tasas en SIGAP?', 'conocimiento'),
    ('¿Qué deuda tiene el contribuyente IM345805620000?', 'deuda'),
    ('¿Cuántos expedientes hay en trámite y cuáles son los sectores más cargados?', 'analitica'),
]


def main():
    sesion = 'qa-live'
    for pregunta, tipo in PREGUNTAS:
        print(f'\n{"=" * 72}')
        print(f'[{"*" if tipo != "conocimiento" else "?"}] PREGUNTA: {pregunta}')
        t0 = time.time()
        try:
            r = agente.responder(sesion, pregunta)
            print(f'RESPUESTA ({time.time() - t0:.1f}s):\n{r}')
        except Exception as e:
            print(f'ERROR: {e}')


if __name__ == '__main__':
    main()
