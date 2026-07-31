"""
Resumen semanal de convocatorias: genera un informe HTML y, si hay correo
configurado, lo envía a los suscriptores.

Incluye:
  · convocatorias que vencen en los próximos DIAS_AVISO días
  · convocatorias nuevas detectadas desde el último envío
  · dossiers con su tema, cuando se pudo aislar

SOBRE EL ENVÍO POR CORREO
El informe HTML se genera SIEMPRE en informes/, sin necesidad de configurar
nada. El envío por correo es opcional y requiere que completes vos mismo
config_email.json con los datos de tu cuenta. Nadie más debe escribir ahí tu
contraseña: si usás Gmail, generá una "contraseña de aplicación" en
https://myaccount.google.com/apppasswords y usá esa, no la de tu cuenta.
El archivo está en .gitignore para que no se comparta por accidente.
"""
import os
import json
import smtplib
import logging
from datetime import date, datetime, timedelta
from email.message import EmailMessage
from html import escape

from database import (init_db, obtener_convocatorias, obtener_suscriptores,
                      marcar_envio, registrar_actualizacion, conectar)

logger = logging.getLogger(__name__)

BASE = os.path.dirname(os.path.abspath(__file__))
DIR_INFORMES = os.path.join(BASE, 'informes')
CONFIG = os.path.join(BASE, 'config_email.json')

DIAS_AVISO = 30      # "próximas a vencer"
DIAS_NUEVAS = 7      # ventana de "nuevas desde la última actualización"


def _dias(fecha_iso):
    if not fecha_iso:
        return None
    try:
        return (date.fromisoformat(str(fecha_iso)[:10]) - date.today()).days
    except ValueError:
        return None


def reunir(dias_aviso=DIAS_AVISO, dias_nuevas=DIAS_NUEVAS):
    """Devuelve (por_vencer, nuevas, permanentes_nuevas)."""
    convocatorias = obtener_convocatorias()

    por_vencer = []
    for c in convocatorias:
        d = _dias(c['fecha_cierre'])
        if d is not None and 0 <= d <= dias_aviso:
            por_vencer.append((d, c))
    por_vencer.sort(key=lambda x: x[0])

    corte = datetime.now() - timedelta(days=dias_nuevas)
    nuevas = []
    for c in convocatorias:
        try:
            hallada = datetime.fromisoformat(str(c['fecha_encontrada'])[:19])
        except (ValueError, TypeError):
            continue
        if hallada >= corte:
            nuevas.append(c)
    nuevas.sort(key=lambda c: (c['fecha_cierre'] or '9999', c['revista']))

    conn = conectar()
    permanentes = conn.execute(
        "SELECT COUNT(*) FROM revistas WHERE recepcion_permanente=1").fetchone()[0]
    conn.close()

    return por_vencer, nuevas, permanentes


def _color(d):
    if d is None:
        return "#6b7280"
    if d <= 3:
        return "#dc2626"
    if d <= 7:
        return "#ea580c"
    if d <= 21:
        return "#ca8a04"
    return "#16a34a"


def _tarjeta(c, d=None):
    color = _color(d)
    etiqueta = (f"{d} día{'s' if d != 1 else ''}" if d is not None
                else "sin fecha declarada")
    partes = [
        f'<div style="border-left:5px solid {color};background:#f6f7f9;'
        f'padding:12px 16px;margin:10px 0;border-radius:5px;">',
        f'<div style="font-weight:700;color:#111;">{escape(c["revista"])}'
        f' <span style="float:right;color:{color};">{etiqueta}</span></div>',
        f'<div style="margin-top:5px;color:#222;">{escape(c["titulo"])}</div>',
    ]
    if c.get('es_dossier') and c.get('tema'):
        partes.append(
            f'<div style="margin-top:6px;padding:8px 10px;background:#eef2ff;'
            f'border-radius:4px;font-size:13px;">'
            f'<strong>Dossier:</strong> {escape(c["tema"])}</div>')
    detalle = []
    if c.get('fecha_cierre'):
        detalle.append(f'cierra el {c["fecha_cierre"]}')
    if c.get('pais'):
        detalle.append(escape(c['pais']))
    if c.get('nivel_conicet') == 1:
        detalle.append('Nivel 1')
    elif c.get('nivel_conicet') == 2:
        detalle.append('Nivel 2')
    if detalle:
        partes.append(f'<div style="margin-top:6px;font-size:12px;color:#666;">'
                      f'{" · ".join(detalle)}</div>')
    if c.get('url'):
        partes.append(f'<div style="margin-top:6px;">'
                      f'<a href="{escape(c["url"])}" style="color:#2563eb;'
                      f'font-size:13px;">Abrir convocatoria →</a></div>')
    partes.append('</div>')
    return "".join(partes)


def construir_html(nombre_destinatario=None):
    por_vencer, nuevas, permanentes = reunir()
    hoy = date.today().isoformat()

    saludo = (f"<p>Hola {escape(nombre_destinatario)},</p>"
              if nombre_destinatario else "")
    urgentes = sum(1 for d, _ in por_vencer if d <= 7)

    h = [f'''<div style="font-family:system-ui,-apple-system,Segoe UI,sans-serif;
              max-width:720px;margin:0 auto;color:#111;">
      <h2 style="margin-bottom:4px;">Revistas iberoamericanas en ciencias
        sociales y humanidades</h2>
      <p style="color:#666;margin-top:0;">Resumen de convocatorias · {hoy}</p>
      {saludo}
      <p><strong>{len(por_vencer)}</strong> convocatorias cierran en los próximos
      {DIAS_AVISO} días''' + (f' (<strong style="color:#dc2626;">{urgentes}</strong> '
                              f'en una semana o menos)' if urgentes else '') +
        f'''. Se detectaron <strong>{len(nuevas)}</strong> nuevas en los últimos
      {DIAS_NUEVAS} días. Además hay <strong>{permanentes}</strong> revistas que
      reciben artículos todo el año.</p>''']

    h.append('<h3 style="margin-top:26px;">⏱️ Próximas a vencer</h3>')
    if por_vencer:
        for d, c in por_vencer:
            h.append(_tarjeta(c, d))
    else:
        h.append('<p style="color:#666;">Ninguna con fecha declarada en '
                 'esta ventana.</p>')

    h.append('<h3 style="margin-top:26px;">🆕 Nuevas desde la última '
             'actualización</h3>')
    if nuevas:
        for c in nuevas:
            h.append(_tarjeta(c, _dias(c['fecha_cierre'])))
    else:
        h.append('<p style="color:#666;">No se detectaron convocatorias nuevas.</p>')

    h.append(f'''<hr style="margin-top:28px;border:none;border-top:1px solid #ddd;">
      <p style="font-size:12px;color:#888;">
      Generado automáticamente por el tracker local de revistas. La detección no
      es exhaustiva: hay revistas cuyo sitio bloquea la lectura automática, y
      muchas convocatorias no declaran su fecha de cierre en un formato legible.
      Verificá siempre en el enlace antes de preparar un envío.<br>
      Para darte de baja, abrí la app y quitá tu correo en la pestaña Boletín.
      </p></div>''')
    return "\n".join(h)


def guardar_informe():
    """Escribe el informe HTML en informes/ y devuelve la ruta."""
    os.makedirs(DIR_INFORMES, exist_ok=True)
    ruta = os.path.join(DIR_INFORMES,
                        f"convocatorias-{date.today().isoformat()}.html")
    with open(ruta, 'w', encoding='utf-8') as f:
        f.write("<!doctype html><meta charset='utf-8'>"
                "<title>Convocatorias</title>" + construir_html())
    return ruta


def cargar_config():
    if not os.path.exists(CONFIG):
        return None
    try:
        with open(CONFIG, encoding='utf-8') as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        return None
    faltan = [k for k in ('servidor', 'puerto', 'usuario', 'password', 'remitente')
              if not cfg.get(k)]
    if faltan or 'COMPLETAR' in str(cfg.get('password', '')):
        return None
    return cfg


def enviar(cfg, destinatario, nombre, html):
    msg = EmailMessage()
    msg['Subject'] = (f"Convocatorias a dossier · "
                      f"{date.today().strftime('%d/%m/%Y')}")
    msg['From'] = cfg['remitente']
    msg['To'] = destinatario
    msg.set_content(
        "Este resumen está en formato HTML. Si no lo ves bien, abrí el archivo "
        f"generado en la carpeta informes/ del tracker.")
    msg.add_alternative(html, subtype='html')

    if int(cfg['puerto']) == 465:
        with smtplib.SMTP_SSL(cfg['servidor'], int(cfg['puerto']), timeout=45) as s:
            s.login(cfg['usuario'], cfg['password'])
            s.send_message(msg)
    else:
        with smtplib.SMTP(cfg['servidor'], int(cfg['puerto']), timeout=45) as s:
            s.starttls()
            s.login(cfg['usuario'], cfg['password'])
            s.send_message(msg)


def enviar_boletin():
    """Genera el informe y lo manda a los suscriptores activos."""
    init_db()
    ruta = guardar_informe()
    logger.info("Informe generado: %s", ruta)

    suscriptores = obtener_suscriptores()
    if not suscriptores:
        registrar_actualizacion("boletin", f"Informe generado ({os.path.basename(ruta)}); "
                                           "sin suscriptores cargados")
        return dict(informe=ruta, enviados=0, errores=[], correo_configurado=False)

    cfg = cargar_config()
    if not cfg:
        registrar_actualizacion(
            "boletin",
            f"Informe generado ({os.path.basename(ruta)}); correo no configurado, "
            f"{len(suscriptores)} suscriptor(es) sin enviar")
        return dict(informe=ruta, enviados=0, errores=[], correo_configurado=False)

    enviados, errores = 0, []
    for s in suscriptores:
        try:
            enviar(cfg, s['email'], s['nombre'], construir_html(s['nombre']))
            marcar_envio(s['email'])
            enviados += 1
        except Exception as e:
            errores.append(f"{s['email']}: {type(e).__name__} {e}")
            logger.warning("Falló el envío a %s: %s", s['email'], e)

    registrar_actualizacion(
        "boletin",
        f"{enviados}/{len(suscriptores)} correos enviados"
        + (f"; {len(errores)} con error" if errores else ""))
    return dict(informe=ruta, enviados=enviados, errores=errores,
                correo_configurado=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s',
                        handlers=[logging.FileHandler('actualizaciones.log',
                                                      encoding='utf-8'),
                                  logging.StreamHandler()])
    r = enviar_boletin()
    print("informe:", r['informe'])
    print("enviados:", r['enviados'])
    if not r['correo_configurado']:
        print("correo no configurado: completá config_email.json para que se envíe.")
    for e in r['errores']:
        print("  error:", e)
