"""QA Fase 3 — simulación completa de WhatsApp (webhook de Meta simulado).

Simula los payloads reales de Meta (como en la doc Get Started) y captura
los mensajes que el agente enviaría de vuelta. No requiere credenciales de Meta.
"""
import json
import sys
import os
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import whatsapp

WA_ID = '5492640000000'  # número simulado


def _payload(texto):
    """Payload real de Meta (formato de la documentación Get Started)."""
    return {
        'object': 'whatsapp_business_account',
        'entry': [{
            'id': '215589313241560883',
            'changes': [{
                'value': {
                    'messaging_product': 'whatsapp',
                    'metadata': {'display_phone_number': '5492641234567',
                                 'phone_number_id': '7794189252778687'},
                    'contacts': [{'profile': {'name': 'Vecino'}, 'wa_id': WA_ID}],
                    'messages': [{
                        'from': WA_ID,
                        'id': 'wamid.HBgTEST',
                        'timestamp': '1758254144',
                        'text': {'body': texto},
                        'type': 'text',
                    }],
                },
                'field': 'messages',
            }],
        }],
    }


def main():
    enviados = []

    def fake_enviar(wa_id, texto):
        enviados.append(texto)
        print(f'\n📤 [a WhatsApp] {texto}')

    mensajes = [
        'Hola, quiero saber cuánto debo de tasas',
        'Mi DNI es 18433285',
        'Mi cuenta es la CG20184332850',
        'La calle registrada es CANO 0',
    ]

    with patch.object(whatsapp, '_enviar', side_effect=fake_enviar):
        for texto in mensajes:
            print(f'\n📩 [de WhatsApp] {texto}')
            whatsapp.manejar_webhook(_payload(texto))

    print(f'\n✅ Simulación completa: {len(mensajes)} mensajes → {len(enviados)} respuestas.')


if __name__ == '__main__':
    main()
