# -*- coding: utf-8 -*-
"""
Datos verificados a mano, para lo que el rastreador no puede leer solo.

Sirve para dos casos:
  · revistas cuyo sitio bloquea la lectura automática (Anubis, Cloudflare),
    que se saltean a propósito y nunca van a aparecer por scraping;
  · convocatorias publicadas en PDF, en redes o fuera de la página de avisos.

Cada entrada lleva su `fuente`: de dónde salió el dato y quién lo verificó.
Sin eso no se carga — el valor de este panel está en que todo sea rastreable
hasta su origen.

Las convocatorias vencidas se archivan solas en la próxima actualización;
no hace falta borrarlas de acá.
"""

# (nombre_revista, frase_textual_que_lo_declara, fuente)
PERMANENTES = [
    ("Políticas Educativas (PolEd)",
     "Los artículos podrán presentarse de forma continua en el Sistema "
     "Electrónico de la Revista, sin embargo, se publicarán dos números "
     "correspondientes a dos semestres por año",
     "https://seer.ufrgs.br/index.php/Poled/announcement/view/1808"),

    ("Cuadernos de la Facultad de Humanidades y Ciencias Sociales",
     "La revista Cuadernos de la Facultad de Humanidades y Ciencias Sociales, "
     "Universidad Nacional de Jujuy, recibe artículos científicos para su "
     "posible publicación entre los meses de Febrero a Noviembre",
     "https://revistas.fhycs.unju.edu.ar/revistacuadernos/index.php/cuadernos/announcement"),

    # El sitio de ORT usa protección anti-bot y no se puede leer; el dato lo
    # aportó Elías Aguirre, que la sigue.
    ("Cuadernos de Investigación Educativa",
     "Convocatoria continua: la revista recibe artículos todo el año",
     "informado por Elías Aguirre (el sitio bloquea la lectura automática)"),
]

# Convocatorias que no aparecen por scraping.
#   revista      debe coincidir con el nombre en el catálogo
#   fecha_cierre 'YYYY-MM-DD' o None si no está declarada
CONVOCATORIAS = [
    dict(revista="Políticas Educativas (PolEd)",
         titulo="DOSSIER TEMÁTICO - Tiempos y espacios escolares en disputa. "
                "Debates contemporáneos en el campo pedagógico",
         tema="Tiempos y espacios escolares en disputa. Debates contemporáneos "
              "en el campo pedagógico",
         descripcion="Comisión organizadora: María Silvia Serra (UNR) y "
                     "Natalia Fattore (UNR). Envío de artículos del 30/03/2026 "
                     "al 30/06/2026, ampliado hasta el 30/07/2026. "
                     "Publicación: diciembre de 2026.",
         fecha_cierre="2026-07-30",
         url="https://seer.ufrgs.br/index.php/Poled/announcement/view/2124",
         fuente="página de avisos de PolEd"),

    dict(revista="Políticas Educativas (PolEd)",
         titulo="DOSSIER TEMÁTICO - Privatización de la educación en América "
                "Latina: sujetos y contenido de las propuestas",
         tema="Privatización de la educación en América Latina: sujetos y "
              "contenido de las propuestas",
         descripcion="Propuesto por el Grupo de Investigación Relaciones entre "
                     "lo Público y lo Privado en la Educación. Analiza "
                     "políticas, programas y propuestas que materializan "
                     "formas de privatización de la educación pública.",
         fecha_cierre="2026-04-06",
         url="https://seer.ufrgs.br/index.php/Poled/announcement/view/2067",
         fuente="página de avisos de PolEd"),
]

# ─────────────────────────────────────────────────────────────────────────
# Relevamiento de agosto de 2026, informado por Elías Aguirre.
#
# Las fechas vienen de la fuente, no de una lectura automática. Las que la
# fuente marca como «cierre consignado» son nominales: corresponden a
# convocatorias declaradas permanentes o continuas, donde la fecha es un tope
# administrativo y no un plazo real. Esas revistas se marcan además como de
# recepción permanente, que es el dato que de verdad importa.
# ─────────────────────────────────────────────────────────────────────────

_FUENTE = "relevamiento informado por Elías Aguirre (agosto 2026)"

CONVOCATORIAS += [
    dict(revista="Revista de economía política de Buenos Aires",
         titulo="Convocatoria abierta", fecha_cierre="2026-08-01",
         url="", fuente=_FUENTE),
    dict(revista="Revista Significantes",
         titulo="Convocatoria abierta", fecha_cierre="2026-08-01",
         url="", fuente=_FUENTE),
    dict(revista="Revista de extensión universitaria +E",
         titulo="E+E: Estudios de Extensión en Humanidades — convocatoria",
         fecha_cierre="2026-08-10", url="", fuente=_FUENTE),
    dict(revista="RICAP. Revista Integradora de la Comunidad Académica en Psicología",
         titulo="Dossier: Salud mental y sociedad",
         tema="Salud mental y sociedad",
         fecha_cierre="2026-08-15", url="", fuente=_FUENTE),
    dict(revista="RICAP. Revista Integradora de la Comunidad Académica en Psicología",
         titulo="Dossier: Educación innovadora y de impacto social",
         tema="Educación innovadora y de impacto social",
         fecha_cierre="2026-08-15", url="", fuente=_FUENTE),
    dict(revista="Argonautas. Revista de Educación y Ciencias Sociales",
         titulo="Convocatoria abierta", fecha_cierre="2026-08-17",
         descripcion="Convocatoria difundida a través de LatinREV.",
         url="", fuente=_FUENTE),
    dict(revista="Historia y Región",
         titulo="Convocatoria abierta", fecha_cierre="2026-08-23",
         url="", fuente=_FUENTE),
    dict(revista="Dearq",
         titulo="Dossier: Materia tectónica / Tectonic Matter",
         tema="Materia tectónica / Tectonic Matter",
         fecha_cierre="2026-08-30", url="", fuente=_FUENTE),
    dict(revista="Disertaciones",
         titulo="Dossier: Posthumanidades y nuevos materialismos",
         tema="Posthumanidades y nuevos materialismos",
         fecha_cierre="2026-08-30", url="", fuente=_FUENTE),
    dict(revista="Dixit",
         titulo="Dossier: Comunicación y gobernanza del ecosistema digital "
                "en América Latina",
         tema="Comunicación y gobernanza del ecosistema digital en América Latina",
         fecha_cierre="2026-08-31", url="", fuente=_FUENTE),
    dict(revista="Encuentros Uruguayos",
         titulo="Convocatoria Vol. 19, N.º 2", fecha_cierre="2026-08-31",
         url="", fuente=_FUENTE),
    dict(revista="Íconos. Revista de Ciencias Sociales",
         titulo="Dossier: Economías ilegales y crimen organizado en América Latina",
         tema="Economías ilegales y crimen organizado en América Latina",
         fecha_cierre="2026-09-07", url="", fuente=_FUENTE),
    dict(revista="Acervo",
         titulo="Dossier: En las fronteras de lo archivable y la memoria "
                "como derecho",
         tema="En las fronteras de lo archivable y la memoria como derecho",
         fecha_cierre="2026-09-30", url="", fuente=_FUENTE),
    dict(revista="Desafíos: Economía y Empresa",
         titulo="Convocatoria edición N.º 10", fecha_cierre="2026-10-15",
         url="", fuente=_FUENTE),
    dict(revista="El Peldaño",
         titulo="El Peldaño: Cuaderno de Teatrología — número 27",
         fecha_cierre="2026-10-19", url="", fuente=_FUENTE),
    dict(revista="Polifonías",
         titulo="Recepción de artículos libres", fecha_cierre="2026-11-01",
         descripcion="Recepción de artículos libres, por fuera de los dossiers "
                     "temáticos.",
         url="", fuente=_FUENTE),
    dict(revista="Anuario IEHS",
         titulo="Convocatoria a propuestas de dosier",
         fecha_cierre="2026-12-01", url="", fuente=_FUENTE),
    dict(revista="Revista Perspectivas (UNIMINUTO)",
         titulo="Convocatoria abierta", fecha_cierre="2026-12-13",
         url="", fuente=_FUENTE),
    dict(revista="Antigua Matanza",
         titulo="Convocatoria permanente de artículos",
         fecha_cierre="2026-12-20",
         descripcion="Convocatoria permanente. La fecha es un tope "
                     "administrativo, no un plazo real.",
         url="", fuente=_FUENTE),
    dict(revista="Cotopaxi Tech",
         titulo="Convocatoria continua para artículos originales",
         fecha_cierre="2026-12-24",
         descripcion="Convocatoria continua. La fecha es un tope "
                     "administrativo, no un plazo real.",
         url="", fuente=_FUENTE),
    dict(revista="Cuadernos del Sur. Letras",
         titulo="Convocatoria abierta y permanente", fecha_cierre="2026-12-30",
         descripcion="Convocatoria abierta y permanente. La fecha es un tope "
                     "administrativo, no un plazo real.",
         url="", fuente=_FUENTE),
    dict(revista="Liberabit. Revista Peruana de Psicología",
         titulo="Convocatoria 2026", fecha_cierre="2026-12-31",
         url="", fuente=_FUENTE),
    dict(revista="Jangwa Pana",
         titulo="Convocatoria permanente de artículos",
         fecha_cierre="2026-12-31",
         descripcion="Convocatoria permanente. La fecha es un tope "
                     "administrativo, no un plazo real.",
         url="", fuente=_FUENTE),
    dict(revista="Cadernos de Filosofia Alemã: Crítica e Modernidade",
         titulo="Convocatoria abierta", fecha_cierre="2026-12-31",
         url="", fuente=_FUENTE),
    dict(revista="Estudios económicos",
         titulo="Llamado de artículos", fecha_cierre="2026-12-31",
         url="", fuente=_FUENTE),
    dict(revista="[re]Design",
         titulo="Artículos científicos o ensayos visuales",
         fecha_cierre="2027-12-31",
         descripcion="Recepción abierta. La fecha es un tope administrativo, "
                     "no un plazo real.",
         url="", fuente=_FUENTE),
    dict(revista="Claves. Revista de Historia",
         titulo="Artículos de historia con temática libre",
         fecha_cierre="2027-12-31",
         descripcion="Temática libre, recepción abierta. La fecha es un tope "
                     "administrativo, no un plazo real.",
         url="", fuente=_FUENTE),
    dict(revista="Confluencia de saberes",
         titulo="Convocatoria permanente", fecha_cierre="2028-12-31",
         descripcion="Convocatoria permanente. La fecha es un tope "
                     "administrativo, no un plazo real.",
         url="", fuente=_FUENTE),
    dict(revista="Contribuciones desde Coatepec",
         titulo="Convocatoria permanente", fecha_cierre="2029-12-31",
         descripcion="Convocatoria permanente. La fecha es un tope "
                     "administrativo, no un plazo real.",
         url="", fuente=_FUENTE),

    # Estas dos NO son convocatorias para publicar: convocan evaluadores. Se
    # incluyen porque estaban en el relevamiento, con el tipo aclarado en el
    # título para que no se confundan con un llamado a artículos.
    dict(revista="Revista Médica del Instituto Mexicano del Seguro Social",
         titulo="Convocatoria para REVISORES (no es un llamado a artículos)",
         fecha_cierre="2026-12-29",
         descripcion="Convocatoria para incorporar evaluadores al comité de "
                     "revisión por pares, no para enviar trabajos.",
         url="", fuente=_FUENTE),
    dict(revista="Millcayac. Revista Digital de Ciencias Sociales",
         titulo="Registro de REVISORES por pares (no es un llamado a artículos)",
         fecha_cierre="2026-12-30",
         descripcion="Registro para incorporarse como evaluador/a, no para "
                     "enviar trabajos.",
         url="", fuente=_FUENTE),
]

# Las que la fuente declara permanentes o continuas: ese es el dato útil, más
# allá del tope administrativo que figure como fecha de cierre.
PERMANENTES += [
    ("Antigua Matanza", "Convocatoria permanente de artículos", _FUENTE),
    ("Cotopaxi Tech", "Convocatoria continua para artículos originales", _FUENTE),
    ("Cuadernos del Sur. Letras", "Convocatoria abierta y permanente", _FUENTE),
    ("Jangwa Pana", "Convocatoria permanente de artículos", _FUENTE),
    ("[re]Design", "Recepción abierta de artículos científicos o ensayos "
                   "visuales", _FUENTE),
    ("Claves. Revista de Historia", "Recibe artículos de historia con temática "
                                    "libre de forma abierta", _FUENTE),
    ("Confluencia de saberes", "Convocatoria permanente", _FUENTE),
    ("Contribuciones desde Coatepec", "Convocatoria permanente", _FUENTE),
    ("Polifonías", "Recepción de artículos libres, por fuera de los dossiers "
                   "temáticos", _FUENTE),
]
