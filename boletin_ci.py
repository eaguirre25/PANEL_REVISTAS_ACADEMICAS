"""Envío del boletín semanal desde GitHub Actions.

Usa credenciales y destinatarios desde variables de entorno para no publicar
ningún dato sensible. Está pensado para ejecutarse los martes desde CI.
"""
import json
import os
from pathlib import Path

from database import init_db, agregar_suscriptor
from boletin import enviar_boletin

BASE = Path(__file__).parent


def _destinatarios():
    """Lee destinatarios desde BOLETIN_SUSCRIPTORES.

    Acepta JSON (lista de strings o de objetos con nombre/email) o una lista
    separada por comas, punto y coma o saltos de línea. Como respaldo usa
    NOTIFY_EMAIL y, por último, GMAIL_USER para que una mala configuración no
    termine en un envío silenciosamente vacío.
    """
    raw = (os.getenv("BOLETIN_SUSCRIPTORES") or "").strip()
    items = []

    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                for x in data:
                    if isinstance(x, str):
                        items.append(("", x.strip()))
                    elif isinstance(x, dict) and x.get("email"):
                        items.append(((x.get("nombre") or "").strip(), x["email"].strip()))
        except json.JSONDecodeError:
            normalizado = raw.replace(";", ",").replace("\n", ",")
            items.extend(("", x.strip()) for x in normalizado.split(",") if x.strip())

    if not items:
        fallback = (os.getenv("NOTIFY_EMAIL") or os.getenv("GMAIL_USER") or "").strip()
        if fallback:
            items.append(("", fallback))

    vistos = set()
    limpios = []
    for nombre, email in items:
        e = email.lower()
        if "@" in e and e not in vistos:
            vistos.add(e)
            limpios.append((nombre or e.split("@", 1)[0], e))
    return limpios


def _configurar_correo():
    usuario = (os.getenv("GMAIL_USER") or "").strip()
    password = (os.getenv("GMAIL_APP_PASSWORD") or "").strip()
    if not usuario or not password:
        raise RuntimeError("Faltan los Secrets GMAIL_USER y/o GMAIL_APP_PASSWORD")

    cfg = {
        "servidor": "smtp.gmail.com",
        "puerto": 465,
        "usuario": usuario,
        "password": password,
        "remitente": usuario,
    }
    (BASE / "config_email.json").write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def main():
    _configurar_correo()
    init_db()

    destinatarios = _destinatarios()
    if not destinatarios:
        raise RuntimeError(
            "No hay destinatarios. Configurá BOLETIN_SUSCRIPTORES, NOTIFY_EMAIL "
            "o GMAIL_USER en Secrets."
        )

    for nombre, email in destinatarios:
        agregar_suscriptor(nombre, email)

    resultado = enviar_boletin()
    print(f"Boletín semanal: {resultado['enviados']} enviado(s)")
    for error in resultado["errores"]:
        print("ERROR:", error)

    if resultado["enviados"] < 1 or resultado["errores"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
