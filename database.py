"""Base de datos SQLite del Tracker de Revistas CONICET."""
import re
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "revistas.db"


def conectar():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Crea las tablas si no existen."""
    conn = conectar()
    c = conn.cursor()

    c.execute('''
    CREATE TABLE IF NOT EXISTS revistas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT UNIQUE NOT NULL,
        ficha_url TEXT,
        sitio_url TEXT,
        issn_impreso TEXT,
        issn_online TEXT,
        area TEXT,
        institucion TEXT,
        fecha_agregada TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        fecha_actualizada TIMESTAMP
    )''')

    # UNIQUE(revista_id, titulo) evita duplicados al re-ejecutar el scraper.
    c.execute('''
    CREATE TABLE IF NOT EXISTS convocatorias (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        revista_id INTEGER NOT NULL,
        titulo TEXT NOT NULL,
        descripcion TEXT,
        fecha_cierre DATE,
        url TEXT,
        fuente TEXT,
        fecha_encontrada TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        activa INTEGER DEFAULT 1,
        UNIQUE(revista_id, titulo),
        FOREIGN KEY (revista_id) REFERENCES revistas(id)
    )''')

    c.execute('''
    CREATE TABLE IF NOT EXISTS actualizaciones (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        tipo TEXT,
        detalles TEXT
    )''')

    # Columnas agregadas post-hoc (diagnóstico e indización).
    existentes = {f[1] for f in c.execute("PRAGMA table_info(revistas)").fetchall()}
    nuevas_rev = [
        ('ultimo_chequeo', 'TIMESTAMP'), ('estado_chequeo', 'TEXT'),
        # Indización en bases (para derivar el nivel de la Res. 2249/14).
        ('en_scopus', 'INTEGER'), ('scopus_estado', 'TEXT'),
        ('en_scielo', 'INTEGER'), ('en_doaj', 'INTEGER'),
        ('openalex_core', 'INTEGER'), ('h_index', 'INTEGER'),
        ('works_count', 'INTEGER'), ('nivel_conicet', 'INTEGER'),
        ('indizacion_chequeada', 'TIMESTAMP'),
        # Recepción permanente de artículos.
        ('recepcion_permanente', 'INTEGER'), ('evidencia_permanente', 'TEXT'),
        # Revistas de fuera del NBRA (resto de América Latina).
        ('origen', "TEXT DEFAULT 'NBRA'"), ('pais', 'TEXT'),
        ('indexacion_declarada', 'TEXT'), ('resolucion', 'TEXT'),
        # Última vez que la fuente pudo leerse. Una convocatoria no desaparece
        # porque esta semana el sitio estuvo bloqueado: se muestra con la fecha
        # de su última verificación.
        ('ultima_revision_ok', 'TIMESTAMP'), ('metodo_revision', 'TEXT'),
    ]
    for col, tipo in nuevas_rev:
        if col not in existentes:
            c.execute(f"ALTER TABLE revistas ADD COLUMN {col} {tipo}")

    cols_conv = {f[1] for f in c.execute("PRAGMA table_info(convocatorias)").fetchall()}
    for col, tipo in [('tipo', "TEXT DEFAULT 'con_plazo'"),
                      ('es_dossier', 'INTEGER DEFAULT 0'), ('tema', 'TEXT')]:
        if col not in cols_conv:
            c.execute(f"ALTER TABLE convocatorias ADD COLUMN {col} {tipo}")

    # Suscriptores del resumen semanal por correo.
    c.execute('''
    CREATE TABLE IF NOT EXISTS suscriptores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        fecha_alta TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        activo INTEGER DEFAULT 1,
        ultimo_envio TIMESTAMP
    )''')

    conn.commit()
    conn.close()


# ─────────────────────────── suscriptores ───────────────────────────

def agregar_suscriptor(nombre, email):
    """Da de alta un suscriptor. Devuelve (ok, mensaje)."""
    conn = conectar()
    try:
        conn.execute("INSERT INTO suscriptores (nombre, email) VALUES (?,?)",
                     (nombre.strip(), email.strip().lower()))
        conn.commit()
        return True, "Suscripción registrada."
    except sqlite3.IntegrityError:
        conn.execute("UPDATE suscriptores SET nombre=?, activo=1 WHERE email=?",
                     (nombre.strip(), email.strip().lower()))
        conn.commit()
        return True, "Ese correo ya estaba: se reactivó y actualizó el nombre."
    finally:
        conn.close()


def baja_suscriptor(email):
    conn = conectar()
    cur = conn.execute("UPDATE suscriptores SET activo=0 WHERE email=?",
                       (email.strip().lower(),))
    n = cur.rowcount
    conn.commit()
    conn.close()
    return n


def obtener_suscriptores(solo_activos=True):
    conn = conectar()
    q = "SELECT * FROM suscriptores"
    if solo_activos:
        q += " WHERE activo=1"
    filas = conn.execute(q + " ORDER BY fecha_alta").fetchall()
    conn.close()
    return [dict(f) for f in filas]


def marcar_envio(email):
    conn = conectar()
    conn.execute("UPDATE suscriptores SET ultimo_envio=? WHERE email=?",
                 (datetime.now(), email.strip().lower()))
    conn.commit()
    conn.close()


def guardar_indizacion(revista_id, datos):
    """Guarda el resultado del chequeo de indización de una revista."""
    conn = conectar()
    conn.execute('''UPDATE revistas SET en_scopus=?, scopus_estado=?, en_scielo=?,
                    en_doaj=?, openalex_core=?, h_index=?, works_count=?,
                    nivel_conicet=?, indizacion_chequeada=? WHERE id=?''',
                 (datos.get('en_scopus'), datos.get('scopus_estado'),
                  datos.get('en_scielo'), datos.get('en_doaj'),
                  datos.get('openalex_core'), datos.get('h_index'),
                  datos.get('works_count'), datos.get('nivel_conicet'),
                  datetime.now(), revista_id))
    conn.commit()
    conn.close()


def buscar_por_issn(issns):
    """
    Devuelve el id de la revista que ya tenga alguno de esos ISSN.

    Evita duplicar una revista que ya está en el catálogo bajo otro nombre:
    el NBRA la llama "Cuadernos de la Facultad de Humanidades y Ciencias
    Sociales. Universidad Nacional de Jujuy" y un listado externo, sin el
    sufijo institucional. El ISSN es el mismo y es inequívoco.
    """
    limpios = []
    for i in issns:
        n = re.sub(r'[^0-9Xx]', '', str(i or '')).upper()
        if len(n) == 8:
            limpios.append(f"{n[:4]}-{n[4:]}")
    if not limpios:
        return None

    conn = conectar()
    marcas = ','.join('?' * len(limpios))
    fila = conn.execute(
        f"""SELECT id FROM revistas
            WHERE issn_impreso IN ({marcas}) OR issn_online IN ({marcas})
            LIMIT 1""", limpios * 2).fetchone()
    conn.close()
    return fila['id'] if fila else None


def guardar_revista_externa(nombre, pais, institucion, sitio_url, issn_impreso,
                            issn_online, indexacion_declarada, resolucion):
    """Inserta o actualiza una revista de fuera del NBRA."""
    conn = conectar()
    c = conn.cursor()
    fila = c.execute("SELECT id FROM revistas WHERE nombre = ?", (nombre,)).fetchone()
    if fila:
        c.execute('''UPDATE revistas SET pais=?, institucion=?, sitio_url=?,
                     issn_impreso=?, issn_online=?, indexacion_declarada=?,
                     resolucion=?, origen='externa', area=?, fecha_actualizada=?
                     WHERE id=?''',
                  (pais, institucion, sitio_url, issn_impreso, issn_online,
                   indexacion_declarada, resolucion, 'Ciencias Sociales y Humanidades',
                   datetime.now(), fila['id']))
        estado = 'actualizada'
        rid = fila['id']
    else:
        c.execute('''INSERT INTO revistas
                     (nombre, pais, institucion, sitio_url, issn_impreso, issn_online,
                      indexacion_declarada, resolucion, origen, area, fecha_actualizada)
                     VALUES (?,?,?,?,?,?,?,?,'externa',?,?)''',
                  (nombre, pais, institucion, sitio_url, issn_impreso, issn_online,
                   indexacion_declarada, resolucion,
                   'Ciencias Sociales y Humanidades', datetime.now()))
        estado = 'nueva'
        rid = c.lastrowid
    conn.commit()
    conn.close()
    return estado, rid


def marcar_recepcion_permanente(revista_id, permanente, evidencia):
    conn = conectar()
    conn.execute('''UPDATE revistas SET recepcion_permanente=?, evidencia_permanente=?
                    WHERE id=?''', (1 if permanente else 0, evidencia, revista_id))
    conn.commit()
    conn.close()


def marcar_chequeo(revista_id, estado, metodo='automatico'):
    """
    Registra el resultado del último intento de leer convocatorias.

    Solo se pisa `ultima_revision_ok` cuando la lectura funcionó: así una
    convocatoria hallada hace tres semanas sigue mostrándose, con la fecha en
    que se la verificó por última vez, en lugar de desaparecer porque hoy el
    sitio no respondió.
    """
    conn = conectar()
    if estado in ('ok', 'sin convocatorias'):
        conn.execute("""UPDATE revistas SET ultimo_chequeo=?, estado_chequeo=?,
                        ultima_revision_ok=?, metodo_revision=? WHERE id=?""",
                     (datetime.now(), estado, datetime.now(), metodo, revista_id))
    else:
        conn.execute("UPDATE revistas SET ultimo_chequeo=?, estado_chequeo=? "
                     "WHERE id=?", (datetime.now(), estado, revista_id))
    conn.commit()
    conn.close()


def revistas_bloqueadas():
    """
    Revistas cuya lectura automática falló, agrupadas por dominio.

    Se agrupa por dominio porque la protección suele estar a nivel de servidor:
    varias revistas comparten la plataforma de una universidad, y resolver la
    verificación una vez habilita todas las de ese dominio.
    """
    import re as _re
    from collections import OrderedDict
    conn = conectar()
    filas = conn.execute(
        """SELECT id, nombre, sitio_url, estado_chequeo, ultima_revision_ok
           FROM revistas
           WHERE sitio_url IS NOT NULL AND sitio_url != ''
             AND estado_chequeo IS NOT NULL
             AND (estado_chequeo LIKE '%anti-bot%' OR estado_chequeo LIKE '%login%'
                  OR estado_chequeo LIKE '%inaccesible%' OR estado_chequeo LIKE 'http%'
                  OR estado_chequeo LIKE '%redirec%')
           ORDER BY nombre""").fetchall()
    conn.close()

    por_dominio = OrderedDict()
    for f in filas:
        m = _re.match(r'https?://([^/]+)', f['sitio_url'] or '')
        dom = m.group(1).lower() if m else '(sin dominio)'
        por_dominio.setdefault(dom, []).append(dict(f))
    return por_dominio


def desactivar_convocatorias_vencidas():
    """Marca como inactivas las convocatorias cuya fecha de cierre ya pasó."""
    conn = conectar()
    cur = conn.execute('''UPDATE convocatorias SET activa = 0
                          WHERE activa = 1 AND fecha_cierre IS NOT NULL
                            AND date(fecha_cierre) < date('now')''')
    n = cur.rowcount
    conn.commit()
    conn.close()
    return n


def guardar_revista(nombre, ficha_url, sitio_url, issn_impreso, issn_online, area, institucion):
    """Inserta o actualiza una revista. Devuelve 'nueva' | 'actualizada'."""
    conn = conectar()
    c = conn.cursor()
    c.execute("SELECT id FROM revistas WHERE nombre = ?", (nombre,))
    existe = c.fetchone()

    if existe:
        c.execute('''UPDATE revistas SET ficha_url=?, sitio_url=?, issn_impreso=?,
                     issn_online=?, area=?, institucion=?, fecha_actualizada=?
                     WHERE nombre=?''',
                  (ficha_url, sitio_url, issn_impreso, issn_online, area,
                   institucion, datetime.now(), nombre))
        estado = 'actualizada'
    else:
        c.execute('''INSERT INTO revistas
                     (nombre, ficha_url, sitio_url, issn_impreso, issn_online,
                      area, institucion, fecha_actualizada)
                     VALUES (?,?,?,?,?,?,?,?)''',
                  (nombre, ficha_url, sitio_url, issn_impreso, issn_online,
                   area, institucion, datetime.now()))
        estado = 'nueva'

    conn.commit()
    conn.close()
    return estado


def guardar_convocatoria(revista_id, titulo, descripcion, fecha_cierre, url,
                         fuente, tipo='con_plazo', es_dossier=0, tema=None):
    """Inserta una convocatoria. Devuelve True si es nueva."""
    conn = conectar()
    c = conn.cursor()
    try:
        c.execute('''INSERT INTO convocatorias
                     (revista_id, titulo, descripcion, fecha_cierre, url, fuente,
                      tipo, es_dossier, tema)
                     VALUES (?,?,?,?,?,?,?,?,?)''',
                  (revista_id, titulo, descripcion, fecha_cierre, url, fuente,
                   tipo, es_dossier, tema))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        # Ya existía: actualizamos fecha de cierre por si cambió.
        c.execute('''UPDATE convocatorias SET fecha_cierre=?, url=?, tipo=?,
                     es_dossier=?, tema=?, descripcion=?
                     WHERE revista_id=? AND titulo=?''',
                  (fecha_cierre, url, tipo, es_dossier, tema, descripcion,
                   revista_id, titulo))
        conn.commit()
        return False
    finally:
        conn.close()


def revistas_con_sitio():
    """Revistas de Ciencias Sociales y Humanidades que tienen sitio web."""
    conn = conectar()
    filas = conn.execute('''SELECT id, nombre, sitio_url FROM revistas
                            WHERE sitio_url IS NOT NULL AND sitio_url != ''
                            ORDER BY nombre''').fetchall()
    conn.close()
    return [dict(f) for f in filas]


def obtener_revistas():
    conn = conectar()
    filas = conn.execute("SELECT * FROM revistas ORDER BY nombre").fetchall()
    conn.close()
    return [dict(f) for f in filas]


def obtener_convocatorias():
    """Convocatorias activas con el nombre de su revista."""
    conn = conectar()
    filas = conn.execute('''
        SELECT c.id, c.titulo, c.descripcion, c.fecha_cierre, c.url, c.fuente,
               c.fecha_encontrada, COALESCE(c.tipo,'con_plazo') AS tipo,
               COALESCE(c.es_dossier,0) AS es_dossier, c.tema,
               r.nombre AS revista, r.sitio_url AS revista_url, r.pais, r.origen,
               r.nivel_conicet, r.en_scopus, r.scopus_estado, r.en_scielo, r.en_doaj
        FROM convocatorias c
        JOIN revistas r ON c.revista_id = r.id
        WHERE c.activa = 1
        ORDER BY c.fecha_cierre IS NULL, c.fecha_cierre ASC
    ''').fetchall()
    conn.close()
    return [dict(f) for f in filas]


def registrar_actualizacion(tipo, detalles):
    conn = conectar()
    conn.execute("INSERT INTO actualizaciones (tipo, detalles) VALUES (?,?)",
                 (tipo, detalles))
    conn.commit()
    conn.close()


def obtener_log(limite=100):
    conn = conectar()
    filas = conn.execute("SELECT * FROM actualizaciones ORDER BY fecha DESC LIMIT ?",
                         (limite,)).fetchall()
    conn.close()
    return [dict(f) for f in filas]


def contar():
    conn = conectar()
    c = conn.cursor()
    r = {}
    r['revistas'] = c.execute("SELECT COUNT(*) FROM revistas").fetchone()[0]
    r['con_sitio'] = c.execute(
        "SELECT COUNT(*) FROM revistas WHERE sitio_url IS NOT NULL AND sitio_url != ''").fetchone()[0]
    r['convocatorias'] = c.execute(
        "SELECT COUNT(*) FROM convocatorias WHERE activa = 1").fetchone()[0]
    r['con_fecha'] = c.execute(
        "SELECT COUNT(*) FROM convocatorias WHERE activa = 1 AND fecha_cierre IS NOT NULL").fetchone()[0]
    conn.close()
    return r
