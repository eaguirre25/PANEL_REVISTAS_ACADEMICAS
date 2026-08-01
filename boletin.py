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


def _nombre_pila(nombre):
    """Primer nombre, para un saludo que no suene a formulario."""
    return (nombre or '').strip().split(' ')[0] if nombre else ''


def enlace_baja(email, remitente):
    """
    mailto de baja, con asunto y cuerpo ya escritos.

    Un sitio estático no puede procesar una baja por su cuenta, así que se
    resuelve por correo: llega un mensaje con asunto BAJA y la dirección, y
    se quita desde la pestaña Boletín de la app.
    """
    from urllib.parse import quote
    asunto = quote(f"BAJA - {email}")
    cuerpo = quote("Quiero dejar de recibir el resumen semanal de "
                   "convocatorias.\n\nNo hace falta que escribas nada más: "
                   "con enviar este correo alcanza.")
    return f"mailto:{remitente}?subject={asunto}&body={cuerpo}"


def _envoltorio(saludo, cuerpo, email, remitente, pie_extra=""):
    """Estructura común de los correos: saludo breve, contenido, y baja."""
    baja = enlace_baja(email, remitente)
    return f'''<div style="font-family:system-ui,-apple-system,'Segoe UI',
      Roboto,sans-serif;max-width:660px;margin:0 auto;color:#16181d;
      line-height:1.55;">
  <div style="border-bottom:2px solid #2450c5;padding-bottom:12px;
       margin-bottom:22px;">
    <div style="font-size:13px;color:#5c6572;letter-spacing:.04em;
         text-transform:uppercase;">Panel de revistas académicas</div>
    <div style="font-size:13px;color:#5c6572;">Ciencias sociales y
      humanidades · Iberoamérica</div>
  </div>

  {saludo}

  {cuerpo}

  <hr style="margin-top:34px;border:none;border-top:1px solid #e2e6ec;">
  <p style="font-size:12.5px;color:#8a93a1;margin:14px 0 0;">
    {pie_extra}
    Recibís este correo porque te suscribiste al resumen de convocatorias.
    Podés <a href="{baja}" style="color:#5c6572;">darte de baja acá</a>
    &mdash; se abre un correo ya escrito, solo tenés que enviarlo.
  </p>
  <p style="font-size:12.5px;color:#8a93a1;margin:8px 0 0;">
    Desarrollado por Elías Aguirre ·
    <a href="https://eaguirre25.github.io/PANEL_REVISTAS_ACADEMICAS/"
       style="color:#2450c5;">ver el panel completo</a>
  </p>
</div>'''


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


def construir_bienvenida(nombre, email, remitente):
    """Correo de confirmación, al darse de alta."""
    por_vencer, _, permanentes = reunir()
    pila = _nombre_pila(nombre)
    urgentes = sum(1 for d, _ in por_vencer if d <= 7)

    saludo = (f'<p style="font-size:17px;margin:0 0 6px;">'
              f'Hola{" " + escape(pila) if pila else ""},</p>'
              '<p style="margin:0 0 22px;color:#3d4552;">'
              'Quedaste suscriptx al resumen semanal de convocatorias. '
              'Desde ahora te llega <b>todos los lunes</b>.</p>')

    cuerpo = f'''
  <div style="background:#f2f4f7;border-radius:10px;padding:16px 19px;
       margin-bottom:20px;">
    <p style="margin:0 0 10px;font-weight:600;">Qué vas a recibir</p>
    <ul style="margin:0;padding-left:19px;color:#3d4552;">
      <li style="margin-bottom:5px;">Las convocatorias que cierran en los
        próximos {DIAS_AVISO} días, ordenadas por urgencia.</li>
      <li style="margin-bottom:5px;">Las nuevas que aparecieron esa semana.</li>
      <li style="margin-bottom:5px;">El tema de cada dossier, cuando el aviso
        permite identificarlo.</li>
      <li>Las revistas que reciben artículos todo el año.</li>
    </ul>
  </div>

  <p style="margin:0 0 8px;">Ahora mismo hay
    <b>{len(por_vencer)}</b> convocatorias con el plazo abierto'''\
    + (f', de las cuales <b style="color:#dc2626;">{urgentes}</b> cierran '
       'esta semana' if urgentes else '') + f''', y <b>{permanentes}</b>
    revistas que reciben artículos todo el año.</p>

  <p style="margin:18px 0 0;">
    <a href="https://eaguirre25.github.io/PANEL_REVISTAS_ACADEMICAS/"
       style="display:inline-block;background:#2450c5;color:#fff;
       text-decoration:none;padding:11px 20px;border-radius:8px;
       font-weight:600;">Ver el panel completo</a>
  </p>

  <p style="margin:22px 0 0;color:#5c6572;font-size:14px;">
    Un aviso honesto: la detección no es exhaustiva. Hay revistas cuyo sitio
    bloquea la lectura automática y muchas convocatorias no publican su fecha
    de cierre en un formato legible. Verificá siempre en el enlace antes de
    preparar un envío.</p>'''

    return _envoltorio(saludo, cuerpo, email, remitente)


def construir_html(nombre_destinatario=None, email='', remitente=''):
    """Correo del resumen semanal."""
    por_vencer, nuevas, permanentes = reunir()
    pila = _nombre_pila(nombre_destinatario)
    urgentes = sum(1 for d, _ in por_vencer if d <= 7)
    hoy = date.today().strftime('%d/%m/%Y')

    saludo = (f'<p style="font-size:17px;margin:0 0 6px;">'
              f'Hola{" " + escape(pila) if pila else ""},</p>'
              f'<p style="margin:0 0 20px;color:#3d4552;">'
              f'Esto es lo que se movió esta semana ({hoy}).</p>')

    resumen = f'''<p style="margin:0 0 6px;">
      <b>{len(por_vencer)}</b> convocatorias cierran en los próximos
      {DIAS_AVISO} días'''\
      + (f' &mdash; <b style="color:#dc2626;">{urgentes}</b> en una semana '
         'o menos' if urgentes else '') + f'''.
      Aparecieron <b>{len(nuevas)}</b> nuevas en los últimos {DIAS_NUEVAS} días.
      Además hay <b>{permanentes}</b> revistas que reciben todo el año.</p>'''

    c = [resumen]

    c.append('<h3 style="margin:30px 0 4px;font-size:15px;'
             'text-transform:uppercase;letter-spacing:.05em;color:#5c6572;">'
             'Próximas a vencer</h3>')
    if por_vencer:
        for d, conv in por_vencer:
            c.append(_tarjeta(conv, d))
    else:
        c.append('<p style="color:#5c6572;">Ninguna con fecha declarada en '
                 'esta ventana.</p>')

    c.append('<h3 style="margin:30px 0 4px;font-size:15px;'
             'text-transform:uppercase;letter-spacing:.05em;color:#5c6572;">'
             'Nuevas esta semana</h3>')
    if nuevas:
        for conv in nuevas:
            c.append(_tarjeta(conv, _dias(conv['fecha_cierre'])))
    else:
        c.append('<p style="color:#5c6572;">No se detectaron convocatorias '
                 'nuevas.</p>')

    pie = ('La detección no es exhaustiva: hay revistas cuyo sitio bloquea la '
           'lectura automática y muchas convocatorias no declaran su fecha de '
           'cierre en un formato legible. Verificá siempre en el enlace antes '
           'de preparar un envío.<br><br>')

    return _envoltorio(saludo, "\n".join(c), email, remitente, pie_extra=pie)


def guardar_informe():
    """Escribe el informe HTML en informes/ y devuelve la ruta."""
    os.makedirs(DIR_INFORMES, exist_ok=True)
    ruta = os.path.join(DIR_INFORMES,
                        f"convocatorias-{date.today().isoformat()}.html")
    cfg = cargar_config() or {}
    with open(ruta, 'w', encoding='utf-8') as f:
        f.write("<!doctype html><meta charset='utf-8'>"
                "<title>Convocatorias</title>"
                + construir_html(remitente=cfg.get('remitente', '')))
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


def enviar(cfg, destinatario, asunto, html, texto_plano):
    msg = EmailMessage()
    msg['Subject'] = asunto
    msg['From'] = f"Panel de revistas académicas <{cfg['remitente']}>"
    msg['To'] = destinatario

    # Cabecera estándar: los clientes de correo muestran su propio botón de
    # baja a partir de esto, además del enlace visible en el cuerpo.
    from urllib.parse import quote
    msg['List-Unsubscribe'] = (
        f"<mailto:{cfg['remitente']}?subject={quote('BAJA - ' + destinatario)}>")

    msg.set_content(texto_plano)
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


def enviar_bienvenida(nombre, email):
    """Manda la confirmación de alta. Devuelve (enviado, mensaje)."""
    cfg = cargar_config()
    if not cfg:
        return False, "El correo no está configurado; no se envió confirmación."
    try:
        enviar(cfg, email,
               "Ya estás suscriptx · Panel de revistas académicas",
               construir_bienvenida(nombre, email, cfg['remitente']),
               f"Hola {_nombre_pila(nombre)},\n\n"
               "Quedaste suscriptx al resumen semanal de convocatorias a "
               "dossier. Te llega todos los lunes.\n\n"
               "Panel completo: "
               "https://eaguirre25.github.io/PANEL_REVISTAS_ACADEMICAS/\n\n"
               f"Para darte de baja, respondé este correo con el asunto "
               f"BAJA - {email}")
        marcar_envio(email)
        return True, "Se envió el correo de bienvenida."
    except Exception as e:
        logger.warning("Falló la bienvenida a %s: %s", email, e)
        return False, f"No se pudo enviar la confirmación: {type(e).__name__}"


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
            enviar(cfg, s['email'],
                   f"Convocatorias a dossier · {date.today().strftime('%d/%m/%Y')}",
                   construir_html(s['nombre'], s['email'], cfg['remitente']),
                   f"Hola {_nombre_pila(s['nombre'])},\n\n"
                   "Este resumen se ve mejor en HTML. Panel completo:\n"
                   "https://eaguirre25.github.io/PANEL_REVISTAS_ACADEMICAS/\n\n"
                   f"Para darte de baja, respondé con el asunto "
                   f"BAJA - {s['email']}")
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
