"""
Verifica la configuración de correo y manda un mensaje de prueba.

Uso:
    python probar_correo.py                  -> se lo manda al propio remitente
    python probar_correo.py otro@correo.com  -> se lo manda a esa dirección

No pide ni muestra la contraseña: la lee de config_email.json, que completás
vos. Si algo falla, explica qué revisar en vez de mostrar el error crudo.
"""
import os
import sys
import json
import smtplib
import socket
from datetime import date
from email.message import EmailMessage

BASE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(BASE, 'config_email.json')

CAMPOS = ['servidor', 'puerto', 'usuario', 'password', 'remitente']


def revisar_config():
    """Devuelve (config, [problemas])."""
    if not os.path.exists(CONFIG):
        return None, [
            "No existe config_email.json.",
            "Copiá config_email.ejemplo.json con ese nombre y completalo."]

    try:
        with open(CONFIG, encoding='utf-8') as f:
            cfg = json.load(f)
    except ValueError as e:
        return None, [f"config_email.json no es un JSON válido: {e}",
                      "Suele ser una coma de más o una comilla sin cerrar."]

    problemas = []
    for c in CAMPOS:
        if not str(cfg.get(c, '')).strip():
            problemas.append(f"Falta completar el campo «{c}».")
    if 'COMPLETAR' in str(cfg.get('password', '')):
        problemas.append("El campo «password» todavía tiene el texto de ejemplo.")

    try:
        puerto = int(cfg.get('puerto', 0))
        if puerto not in (25, 465, 587, 2525):
            problemas.append(
                f"El puerto {puerto} es inusual. Gmail usa 465; "
                "Outlook y la mayoría, 587.")
    except (TypeError, ValueError):
        problemas.append("El campo «puerto» debe ser un número, sin comillas.")

    usuario = str(cfg.get('usuario', ''))
    if usuario and '@' not in usuario:
        problemas.append("El «usuario» suele ser la dirección completa.")

    # Aviso específico de Gmail: la clave normal no sirve por SMTP.
    if 'gmail' in str(cfg.get('servidor', '')).lower():
        clave = str(cfg.get('password', '')).replace(' ', '')
        if len(clave) != 16 and 'COMPLETAR' not in clave:
            problemas.append(
                "Con Gmail hace falta una «contraseña de aplicación», que tiene "
                f"16 caracteres; la que está cargada tiene {len(clave)}. "
                "La de tu cuenta no funciona por SMTP.")

    return cfg, problemas


def probar(destino=None):
    cfg, problemas = revisar_config()
    if problemas:
        print("Revisá esto antes de seguir:\n")
        for p in problemas:
            print("  -", p)
        return False

    destino = destino or cfg['remitente']
    print(f"Servidor : {cfg['servidor']}:{cfg['puerto']}")
    print(f"Usuario  : {cfg['usuario']}")
    print(f"Enviando a {destino}...\n")

    msg = EmailMessage()
    msg['Subject'] = "Prueba - Panel de revistas academicas"
    msg['From'] = cfg['remitente']
    msg['To'] = destino
    msg.set_content(
        "Si estás leyendo esto, el envío de correo quedó bien configurado.\n\n"
        "A partir del próximo lunes vas a recibir el resumen semanal de "
        "convocatorias a dossier.\n\n"
        f"Prueba generada el {date.today().strftime('%d/%m/%Y')}.")
    msg.add_alternative(
        "<div style='font-family:system-ui,sans-serif;max-width:520px'>"
        "<h2 style='margin-bottom:4px'>Configuración correcta ✓</h2>"
        "<p>Si estás leyendo esto, el envío de correo quedó bien configurado.</p>"
        "<p>A partir del próximo lunes vas a recibir el resumen semanal de "
        "convocatorias a dossier.</p>"
        f"<p style='color:#666;font-size:13px'>Prueba generada el "
        f"{date.today().strftime('%d/%m/%Y')}.</p></div>", subtype='html')

    puerto = int(cfg['puerto'])
    try:
        if puerto == 465:
            with smtplib.SMTP_SSL(cfg['servidor'], puerto, timeout=45) as s:
                s.login(cfg['usuario'], cfg['password'])
                s.send_message(msg)
        else:
            with smtplib.SMTP(cfg['servidor'], puerto, timeout=45) as s:
                s.starttls()
                s.login(cfg['usuario'], cfg['password'])
                s.send_message(msg)
    except smtplib.SMTPAuthenticationError as e:
        print("El servidor rechazó usuario o contraseña.\n")
        print("  - Con Gmail: tiene que ser una contraseña de aplicación de 16")
        print("    caracteres (myaccount.google.com/apppasswords), no la clave")
        print("    de tu cuenta, y con la verificación en dos pasos activada.")
        print("  - Con Outlook/Hotmail personales Microsoft desactivó este tipo")
        print("    de acceso; conviene usar Gmail o el correo institucional.")
        print(f"\n  respuesta del servidor: {e.smtp_code} {e.smtp_error}")
        return False
    except (socket.gaierror, socket.timeout, ConnectionRefusedError, OSError) as e:
        print("No se pudo conectar al servidor.\n")
        print("  - Revisá que «servidor» y «puerto» estén bien escritos.")
        print("  - Puerto 465 va con SSL; 587 con STARTTLS. Probá el otro.")
        print("  - Algunos antivirus y redes institucionales bloquean el SMTP.")
        print(f"\n  detalle: {type(e).__name__}: {e}")
        return False
    except smtplib.SMTPException as e:
        print(f"Error de SMTP: {type(e).__name__}: {e}")
        return False

    print("Enviado. Revisá la bandeja de entrada (y la carpeta de spam).")
    print("\nSi llegó, ya está: el boletín de los lunes se manda solo.")
    return True


if __name__ == "__main__":
    destino = sys.argv[1] if len(sys.argv) > 1 else None
    sys.exit(0 if probar(destino) else 1)
