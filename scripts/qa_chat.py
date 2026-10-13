"""Validación del chat web del Experto SIGAP con una pregunta real."""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from playwright.async_api import async_playwright


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel='msedge', headless=True)
        page = await browser.new_page(viewport={'width': 1200, 'height': 860})
        errs = []
        page.on('pageerror', lambda e: errs.append(str(e)))

        await page.goto('http://127.0.0.1:8200/', wait_until='networkidle', timeout=60000)
        await page.wait_for_timeout(1200)

        print('1) bienvenida visible:', await page.locator('.bienvenida').is_visible())
        print('2) sugerencias:', await page.locator('.sug').count())

        # Enviar una pregunta real
        await page.fill('#txt', '¿Dónde está el expediente 3540-S-2026?')
        await page.click('#btnEnviar')
        await page.wait_for_selector('.msg.agente .burbuja', timeout=90000)
        # esperar a que desaparezca el typing
        await page.wait_for_timeout(6000)

        burbujas = await page.locator('.msg .burbuja').all_text_contents()
        print('3) mensajes en pantalla:')
        for b in burbujas:
            print('   →', b.strip()[:120].replace('\n', ' | '))

        # Segunda pregunta con contexto (misma sesión)
        await page.fill('#txt', '¿y cuántos movimientos tuvo?')
        await page.click('#btnEnviar')
        await page.wait_for_timeout(9000)
        burbujas2 = await page.locator('.msg .burbuja').all_text_contents()
        print('4) respuesta con contexto de sesión:', burbujas2[-1].strip()[:160].replace('\n', ' | '))

        print('5) errores JS:', errs if errs else 'ninguno')
        await page.screenshot(path='chat_experto.png')
        print('screenshot: chat_experto.png')
        await browser.close()


asyncio.run(main())
