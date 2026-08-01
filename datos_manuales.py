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
