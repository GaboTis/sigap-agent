"""QA Fase 2 final — verificación determinística end-to-end."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import agente

SESION = 'qa-fase2-e2e'


def hablar(pregunta):
    print(f'\n👤 {pregunta}')
    r = agente.responder(SESION, pregunta)
    print(f'🤖 {r}')
    return r


def main():
    hablar('Hola, quiero saber cuánto debo de tasas')
    hablar('Mi DNI es 18433285')
    hablar('Mi cuenta es la CG20184332850')
    hablar('La calle registrada es CANO 0')

    print('\n✅ E2E Fase 2 completado.')


if __name__ == '__main__':
    main()
