# corporate-ppt-bulk

Servicio API que genera en bulk los decks `.pptx` del sistema corporate-ppt de
EDUCA EDTECH Group (los mismos 6 tipos de slide / 5 variantes / paleta exacta
que la skill de Claude), pero redactando el contenido de cada epígrafe con un
modelo de OpenAI en vez de con Claude, para poder lanzar módulos o formaciones
completas de una sola vez.

## Cómo funciona

1. **`parser.py`** — Lee el PDF/temario (formato EDUCALLM: TOC + páginas de
   módulo + "Teaching unit N" + epígrafes "N.N Título") y reconstruye el árbol
   real: acción formativa → módulo formativo → unidad didáctica → epígrafe,
   con el texto fuente de cada epígrafe ya recortado.
2. **`author.py`** — Por cada epígrafe seleccionado, llama a un modelo de
   OpenAI con un system prompt que reproduce exactamente las reglas de
   `corporate-ppt/SKILL.md` (estructura de 12-15 slides, 5 variantes, paleta,
   iconos permitidos, densidad de texto, labels no-español) y le pide que
   devuelva el `plan.json` de ese epígrafe.
3. **`schema.py`** — Valida ese `plan.json` contra las reglas (nº de slides,
   variantes no repetidas en slides consecutivas, iconos permitidos, etc.). Si
   falla, se reintenta una vez pasándole los errores al modelo.
4. **`render/render.py`** — Es el motor de render tal cual (HTML→Chromium→
   pptx editable) copiado de la skill, sin tocar. No cambia nunca.
5. **`jobs.py` + `main.py`** — Orquestan todo como un servicio FastAPI con
   trabajos en background: subes el PDF, eliges el alcance (un epígrafe, una
   unidad, un módulo entero o la formación completa) y te descargas un zip con
   un `.pptx` por epígrafe, organizado por carpetas de módulo.

## Modelo recomendado

**`gpt-4.1`** por defecto. Es el que mejor sigue instrucciones estructuradas
largas (el system prompt es denso: variantes, iconos, densidad de palabras) y
soporta bien el modo `json_object` para forzar salida válida. Para tandas muy
grandes (una formación completa con 70+ epígrafes) donde el coste importa más
que el pulido, puedes sobreescribir el modelo por request y usar `gpt-4o` o
`o4-mini`, aunque con más probabilidad de que la primera pasada falle la
validación y consuma el reintento.

## Variables de entorno (Coolify)

| Variable | Obligatoria | Descripción |
|---|---|---|
| `OPENAI_API_KEY` | Sí | Tu clave de OpenAI, como secret en Coolify. |
| `OPENAI_MODEL` | No | Modelo por defecto si no se especifica en el request (`gpt-4.1`). |
| `DATA_DIR` | No | Dónde guarda PDFs subidos y zips generados (`/srv/data` por defecto). Móntalo como volumen persistente en Coolify si quieres que sobrevivan a un redeploy. |

Coolify ya protege el acceso con su propia contraseña, así que este servicio no añade una capa de autenticación propia.

## Despliegue en Coolify

1. Sube esta carpeta a un repo (GitHub/GitLab) o pega el Dockerfile directo.
2. En Coolify: New Resource → Dockerfile → apunta al repo/carpeta.
3. Puerto interno: `8000`.
4. Añade `OPENAI_API_KEY` como Secret (no como variable plana).
5. (Opcional pero recomendado) monta un volumen en `/srv/data` para persistir
   jobs entre despliegues.
6. Deploy. Prueba con `GET /health`.

## Uso

```bash
BASE="https://tu-servicio.coolify.app"

# 1. Subir el/los PDF(s) y ver la estructura real detectada.
#    Uno o varios — si son varios, se tratan como una misma acción formativa
#    (p. ej. un PDF por módulo) y se combinan en un único doc_id/structure.
#    También acepta un .zip con varios PDFs dentro (carpetas anidadas ok).
curl -s -X POST "$BASE/documents" \
  -F "files=@Certificate_in_eLearning_Production.pdf" | jq

curl -s -X POST "$BASE/documents" \
  -F "files=@Modulo1.pdf" -F "files=@Modulo2.pdf" -F "files=@Modulo3.pdf" | jq

curl -s -X POST "$BASE/documents" -F "files=@modulos.zip" | jq

# devuelve: {"doc_id": "...", "structure": {"certificado": "...", "modulos": [...]}}

# 2a. Generar UN epígrafe
curl -s -X POST "$BASE/jobs" -H "Content-Type: application/json" -d '{
  "doc_id": "DOC_ID",
  "language": "en",
  "selection": {"level": "epigrafe", "items": [{"modulo": "B1-01", "unidad": 1, "codigo": "1.1"}]}
}'

# 2b. Generar TODA una unidad didáctica
curl -s -X POST "$BASE/jobs" -H "Content-Type: application/json" -d '{
  "doc_id": "DOC_ID",
  "selection": {"level": "unidad", "items": [{"modulo": "B1-01", "unidad": 1}]}
}'

# 2c. Generar módulos completos (uno o varios)
curl -s -X POST "$BASE/jobs" -H "Content-Type: application/json" -d '{
  "doc_id": "DOC_ID",
  "selection": {"level": "modulo", "items": ["B1-01", "B6-02"]}
}'

# 2d. Generar la formación COMPLETA (todos los módulos)
curl -s -X POST "$BASE/jobs" -H "Content-Type: application/json" -d '{
  "doc_id": "DOC_ID",
  "selection": {"level": "formacion", "items": []}
}'

# 3. Consultar progreso — incluye "estimated_seconds_remaining" (null hasta
#    que termina el primer epígrafe, luego una estimación en base al ritmo real)
curl -s "$BASE/jobs/JOB_ID" | jq

# 3b. Parar el job — deja de arrancar epígrafes que no habían empezado
#     (marcados "skipped"); los que ya estaban en curso (máx. 2) terminan solos
curl -s -X POST "$BASE/jobs/JOB_ID/cancel" | jq

# 4. Descargar el zip cuando "download_ready": true
curl -s "$BASE/jobs/JOB_ID/download" -o decks.zip

# 5. Si algo falló o quedó "skipped" (uno de N, o el único epígrafe de un job
#    de 1), reintenta solo eso — no hace falta volver a subir el PDF ni
#    reelegir scope. Los que ya salieron bien se quedan tal cual en el zip.
curl -s -X POST "$BASE/jobs/JOB_ID/retry" | jq
```

## Límites conocidos (v1)

- **Estado en memoria, con autosave a partir de 50 epígrafes**: los
  documentos parseados y los jobs pequeños (≤50 epígrafes) viven solo en RAM
  — un redeploy/reinicio los borra sin más. Un job de más de 50 epígrafes
  (`jobs.AUTOSAVE_THRESHOLD`) escribe cada `.pptx` a disco (`/srv/data/jobs/`)
  en cuanto termina y persiste el estado del job tras cada cambio, en vez de
  guardar todo solo en memoria hasta el final. Si el proceso muere a mitad
  (crash, OOM, redeploy) montando `/srv/data` como volumen, al arrancar de
  nuevo `load_persisted_jobs()` recupera esos jobs: lo que ya estaba "done"
  se queda así, lo que estaba a medias vuelve a quedar como fallo reintentable
  (nunca se pierde en un estado fantasma). Si dejaste la pestaña abierta,
  el polling normal (`GET /jobs/{job_id}`) recoge el job recuperado solo con
  que el proceso vuelva a estar arriba — no hace falta ninguna acción nueva.
  Esto solo protege contra un crash del *proceso*; si `/srv/data` no está
  montado como volumen persistente, un contenedor nuevo tampoco tiene esos
  archivos y no hay nada que recuperar.
- **Parar un job en curso**: el botón "Stop" (o `POST /jobs/{id}/cancel`) deja
  de arrancar epígrafes que no habían empezado (quedan "skipped", reintentables
  después); los que ya estaban corriendo (máx. 2, por la concurrencia) se dejan
  terminar solos — no hay forma segura de abortar a mitad una llamada
  bloqueante a OpenAI o al render.
- **Instancia única**: no pensado para escalar horizontalmente (el job vive en
  la memoria de un solo proceso).
- **Concurrencia**: cada job procesa 2 epígrafes en paralelo (llamada a OpenAI
  + render) para no saturar rate limits ni CPU. Configurable en
  `jobs._run_job(..., max_workers=2)`.
- **Parser de dos niveles**: primero intenta el parser rápido/gratis
  calibrado al formato EDUCALLM visto hasta ahora ("Módulo formativo" +
  "Unidad didáctica N" + Índice). Si el PDF no encaja con esa forma exacta
  (otro layout de EDUCALLM, u otra fuente), cae a detección de estructura
  vía OpenAI (`OPENAI_STRUCTURE_MODEL`, por defecto `gpt-4.1-mini`): el
  modelo identifica módulo/unidad/epígrafe, pero el contenido solo se
  extrae si ese título aparece literal en el texto — si no, se descarta esa
  sección en vez de inventar contenido. Si ambos intentos fallan, el error
  final explica por qué falló cada uno.
- **Reintentos ante rate limit de OpenAI**: un 429 se reintenta hasta 5 veces
  honrando el "try again in Ns" del propio error de OpenAI. Otros fallos
  (timeout, error de render, plan.json inválido tras el reintento) dejan esa
  tarea en `error` con el mensaje, pero el resto del job sigue — el botón
  "Retry N failed" (o `POST /jobs/{job_id}/retry`) reintenta solo esas tareas
  sin volver a subir el PDF ni reelegir scope; funciona igual si falló una
  de muchas o la única de un job de un solo epígrafe.
- **PDFs múltiples del mismo bloque**: si subes varios, cada uno se parsea por
  separado y luego se combinan; un código de módulo repetido entre dos PDFs
  se rechaza (422) en vez de fusionarse en silencio.
