"""
Configuración local del panel.

El correo de contacto NO está en el código: iría a parar a un repositorio
público y quedaría expuesto a recolectores de spam. Se toma, en este orden:

  1. la variable de entorno PANEL_REVISTAS_EMAIL
  2. el archivo config_local.json (ignorado por git)
  3. vacío

Declarar un correo no es obligatorio, pero conviene: OpenAlex y Crossref dan
límites de uso más holgados a los clientes que se identifican ("polite pool").
"""
import os
import json

BASE = os.path.dirname(os.path.abspath(__file__))
CONFIG_LOCAL = os.path.join(BASE, 'config_local.json')

PROYECTO_URL = "https://github.com/eaguirre25/PANEL_REVISTAS_ACADEMICAS"


def _leer_email():
    env = os.environ.get('PANEL_REVISTAS_EMAIL', '').strip()
    if env:
        return env
    if os.path.exists(CONFIG_LOCAL):
        try:
            with open(CONFIG_LOCAL, encoding='utf-8') as f:
                return (json.load(f).get('email_contacto') or '').strip()
        except (OSError, ValueError):
            pass
    return ''


EMAIL_CONTACTO = _leer_email()

USER_AGENT = ("PanelRevistasAcademicas/1.0 "
              f"(+{PROYECTO_URL}"
              + (f"; mailto:{EMAIL_CONTACTO}" if EMAIL_CONTACTO else "")
              + ")")

HEADERS = {'User-Agent': USER_AGENT}

# Algunos sitios de revistas rechazan agentes no habituales; para esos se usa
# un navegador genérico. No es evasión de protecciones: los sitios con desafío
# anti-bot se saltean explícitamente (ver convocatorias.py y permanentes.py).
HEADERS_NAVEGADOR = {
    'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                   'AppleWebKit/537.36 (KHTML, like Gecko) '
                   'Chrome/120.0 Safari/537.36')
}
