# 📚 Panel de revistas académicas iberoamericanas

Rastrea **convocatorias y llamados a dossier** abiertos en 502 revistas de
ciencias sociales y humanidades de Iberoamérica, y avisa cuáles están por
cerrar.

Nació de un problema concreto: enterarse tarde de una convocatoria. La
información existe, pero está repartida en cientos de sitios que hay que
visitar de a uno.

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Streamlit](https://img.shields.io/badge/streamlit-1.40%2B-red)
![Licencia](https://img.shields.io/badge/licencia-MIT-green)

---

## Qué hace

| | |
|---|---|
| **502 revistas** | 324 del Núcleo Básico argentino + 178 de otros 19 países |
| **174 convocatorias** activas | 84 son dossiers, 57 con el tema identificado |
| **68 revistas** de recepción permanente | reciben artículos todo el año |
| **Nivel CONICET** | calculado según la Res. D 2249/2014 |
| **Indización verificada** | Scopus, SciELO y DOAJ, contra fuentes oficiales |
| **Boletín semanal** | resumen por correo de lo que vence y lo que apareció |

Países: Argentina, México, Brasil, Chile, Colombia, Perú, Uruguay, Paraguay,
Ecuador, Venezuela, Cuba, Bolivia, Costa Rica, Panamá, El Salvador, Guatemala,
Honduras, Nicaragua, Puerto Rico, República Dominicana, España y Portugal.

## Las seis pestañas

- **⏱️ Reloj** — convocatorias con plazo, ordenadas por urgencia
  (🔴 ≤3 días · 🟠 ≤7 · 🟡 ≤21 · 🟢 más). Los dossiers muestran su tema.
- **♾️ Permanentes** — revistas abiertas todo el año, cada una con la **frase
  textual** del sitio que lo declara y el enlace a esa página
- **📋 Convocatorias** — todas, con filtro *Solo dossiers* y búsqueda por tema
- **🔍 Buscar revistas** — por país, catálogo, nivel, base de indización,
  convocatoria abierta o recepción permanente
- **✉️ Boletín** — suscripción al resumen semanal
- **📊 Cobertura** — qué se pudo revisar y qué no

---

## Instalación

```bash
git clone https://github.com/eaguirre25/PANEL_REVISTAS_ACADEMICAS.git
cd PANEL_REVISTAS_ACADEMICAS
pip install -r requirements.txt
```

Primera carga de datos (tarda; son ~500 sitios):

```bash
python actualizar.py
```

Abrir el panel:

```bash
streamlit run app.py --server.address=localhost
```

En Windows alcanza con doble clic en **`iniciar.bat`**, que detecta Python,
instala lo que falte y abre el panel.

### Configuración opcional

| Archivo | Para qué | ¿Se versiona? |
|---|---|---|
| `config_local.json` | tu correo de contacto para las APIs (mejores límites de uso) | no |
| `config_email.json` | credenciales SMTP, para que el boletín se envíe | **no** |
| `config_sitio.json` | endpoint del formulario de suscripción del sitio | sí |

Los dos primeros tienen su `.ejemplo.json` al lado y están en `.gitignore`.

### Enviar el boletín desde tu correo

1. Copiá `config_email.ejemplo.json` como `config_email.json`
2. Completá servidor, puerto, usuario y contraseña
3. Con Gmail, **no pongas la contraseña de tu cuenta**: generá una
   [contraseña de aplicación](https://myaccount.google.com/apppasswords)
   (requiere verificación en dos pasos activada) y usá esa
4. Verificá antes de esperar al lunes:

```bash
python probar_correo.py
```

Manda un mensaje de prueba y, si algo falla, dice qué revisar en lugar de
mostrar el error crudo.

| Proveedor | servidor | puerto |
|---|---|---|
| Gmail | `smtp.gmail.com` | 465 |
| Outlook / Microsoft 365 | `smtp.office365.com` | 587 |
| Yahoo | `smtp.mail.yahoo.com` | 465 |
| Zoho | `smtp.zoho.com` | 465 |

Sin configurar nada el boletín igual se genera como HTML en `informes/`;
simplemente no se manda.

### Recibir suscripciones desde el sitio público

Un sitio estático no puede recibir los datos de un formulario: hace falta un
servicio que acepte el POST. La URL va en `config_sitio.json`, clave
`formulario_endpoint` — sirve Formspree, Getform, FormSubmit, Basin o similar.
Ese archivo **sí se versiona** (el workflow lo necesita) y no contiene nada
secreto: el endpoint queda visible en el HTML de todas formas.

### Actualización automática

En Windows, doble clic en `configurar-automatico.bat`: crea una tarea que cada
lunes a las 10:00 actualiza todo y arma el boletín.

En Linux/macOS, vía cron:

```bash
0 10 * * 1 cd /ruta/al/panel && python actualizar.py
```

---

## Cómo funciona

```
catalogo.py      nómina del NBRA (CAICYT-CONICET) + ficha de cada revista
externas.py      revistas de fuera de Argentina, resueltas y verificadas
convocatorias.py endpoint /announcement de OJS → convocatorias y temas
permanentes.py   /about/submissions → recepción abierta todo el año
indizacion.py    Scopus + SciELO + DOAJ → nivel CONICET
resolver_issn.py completa ISSN faltantes vía OpenAlex
boletin.py       informe HTML + envío por correo
app.py           interfaz Streamlit
```

La mayoría de las revistas usan **OJS**, que expone sus anuncios en
`{sitio}/announcement`. Eso hace posible revisarlas de forma uniforme.

### Fuentes de datos

| Dato | Fuente | Verificable en |
|---|---|---|
| Catálogo argentino | Nómina del NBRA, CAICYT-CONICET | ficha de cada revista |
| Convocatorias | Endpoint `/announcement` de OJS | enlace de cada convocatoria |
| Recepción permanente | `/about/submissions`, `/about` o portada | frase citada + enlace |
| Scopus | Scopus Source List (Elsevier, xlsx oficial) | se descarga sola |
| SciELO | API ArticleMeta, red completa (2206 revistas) | articlemeta.scielo.org |
| DOAJ, índice h | API pública de DOAJ y OpenAlex | doaj.org / openalex.org |
| Niveles | Res. D 2249/2014 del CONICET, anexo | PDF de la resolución |

### El nivel CONICET

La **Res. D 2249/2014** jerarquiza **las bases de indización**, no las revistas
una por una:

- **Nivel 1** — Web of Science/ISI, Scopus, ERIH, SciELO.org, CIRC-A
- **Nivel 2** — Sage, Springer, Taylor & Francis, Wiley, JSTOR, REDALyC y el
  **Núcleo Básico de Revistas Argentinas**
- **Nivel 3** — Latindex Catálogo, Philosopher's Index, MLA, ERIC, PsycInfo…

Las revistas del NBRA son **Nivel 2 como piso** y suben a Nivel 1 con Scopus o
SciELO. Las extranjeras no tienen ese piso: si no están en Scopus ni SciELO su
nivel queda *sin determinar*, porque haría falta verificar REDALyC o Latindex
Catálogo, que no publican listados abiertos comparables.

> La resolución advierte: *«dentro de un mismo nivel o grupo conviven revistas
> que, si bien de un nivel semejante en comparación con los otros, difieren
> entre sí respecto de su calidad»*. **No es un puntaje de calidad por
> revista.**

---

## ⚠️ Limitaciones

Esto **no reemplaza** revisar las revistas que te importan.

1. **Pocas convocatorias declaran su plazo** en formato legible. Las demás
   aparecen como "sin fecha declarada" y el reloj no puede avisar de ellas.
2. **~48 revistas usan protección anti-scraping** (Anubis, Cloudflare). **No se
   evaden**: se saltean y se listan en la pestaña *Cobertura* para revisarlas a
   mano.
3. **Muchas revistas no tienen página de anuncios** en su OJS; publican las
   convocatorias en su portada, redes o PDF.
4. **Puede haber falsos positivos.** Un aviso titulado "Suspensión de recepción
   de artículos" se cuela porque menciona la recepción. Verificá siempre en el
   enlace antes de preparar un envío.
5. **Las fechas solo se aceptan con año explícito.** Un aviso que dice "cierra
   el 15 de marzo" queda sin fecha a propósito: inferir el año generaba plazos
   falsos (un aviso de 2017 aparecía venciendo el año próximo).
6. **La indización de las revistas extranjeras está parcialmente verificada.**
   Las que no tienen ISSN resuelto figuran sin nivel: *"sin determinar"* no
   significa *"no indizada"*.

### Decisiones de diseño que vale la pena conocer

- **SCImago no se consulta**: su descarga está tras Cloudflare y no se evade.
  El dato de Scopus sale de la lista oficial de Elsevier, que es la misma base
  sobre la que SCImago calcula el SJR.
- **No se usa `is_in_scielo` de OpenAlex**: devuelve `False` para revistas que
  están efectivamente en SciELO (verificado con *Anclajes*, *Avá* y el *Boletín
  Ravignani*). Se usa la API ArticleMeta.
- **El match de Scopus por título es estricto** (igualdad de palabras
  significativas). Aceptar coincidencias parciales producía falsos positivos
  graves: *Cátedra* (Panamá) recibía un ISSN de otro país. Afirmar una
  indización falsa es peor que no afirmarla.
- **OpenAlex tiene cuota diaria gratuita** y se agota con ~324 consultas. Por
  eso la resolución de ISSN corre por separado y se retoma al día siguiente.

---

## Notas técnicas

**Antivirus que interceptan HTTPS** (AVG, Avast, Kaspersky) rompen la
verificación de certificados de Python. Se resuelve con
[`truststore`](https://pypi.org/project/truststore/), que usa el almacén del
sistema operativo; ya está en `requirements.txt` y se activa en cada módulo que
hace requests.

**La lista de Scopus (~26 MB) no está en el repositorio.** Es material de
Elsevier y no se redistribuye: `indizacion.py` la descarga automáticamente en
la primera ejecución.

---

## Licencia

MIT — ver [LICENSE](LICENSE).

El código es libre. Los **datos** provienen de terceros (CAICYT-CONICET,
Elsevier, SciELO, DOAJ, OpenAlex) y se rigen por sus propias condiciones de
uso.
