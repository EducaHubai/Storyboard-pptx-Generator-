# Historial de jobs (History)

Pantalla + endpoints para ver, retomar y borrar jobs de generación pasados
en `corporate-ppt-bulk`. Ya funcional tras los últimos fixes.

## Qué guarda

- Cada job (uno o más epígrafes) se persiste en disco en
  `DATA_DIR/jobs/{job_id}/` (`job.json` + carpeta `decks/` con los `.pptx`
  ya generados) apenas se crea, sin importar su tamaño.
- El historial (`GET /jobs`) sobrevive a un reinicio/redeploy — se
  reconstruye leyendo esos `job.json` al arrancar (`load_persisted_jobs()`
  en `main.py`), siempre que `DATA_DIR` esté montado como volumen
  persistente en Coolify. Si no lo está, cada redeploy vacía el historial
  (no es un bug, es infraestructura).
- **Retención: 30 días.** Un job `"done"` con más de 30 días se borra solo
  (memoria + `job.json` + `decks/` + zip) al arrancar el proceso y luego
  una vez al día. Un job `"running"`/`"pending"` nunca se borra por edad.

## Endpoints

| Método | Ruta | Qué hace |
|---|---|---|
| `GET` | `/jobs` | Lista todos los jobs, más recientes primero (resumen: estado, contadores done/error/skipped, `certificado`, fecha). |
| `GET` | `/jobs/{job_id}` | Detalle completo de un job (progreso por epígrafe, ETA). |
| `POST` | `/jobs/{job_id}/retry` | Reintenta lo fallido/skipped de ese job (todo, o solo las tareas indicadas en `tasks`). |
| `DELETE` | `/jobs/{job_id}` | Borra el job del historial — memoria, `job.json`, `decks/` y el zip. **Rechaza (400) un job todavía `"running"`** — hay que esperar a que termine o pararlo (`POST /jobs/{id}/cancel`) primero. |

```bash
# borrar un job del historial
curl -s -X DELETE "$BASE/jobs/JOB_ID" | jq
# → {"deleted": "JOB_ID"}   (404 si no existe, 400 si sigue "running")
```

## UI (pantalla History)

- Botón "History" en la barra superior (`openHistory()`), abre el listado
  vía `GET /jobs`.
- Cada tarjeta de job tiene: **View** (abre el detalle/progreso), **⬇
  Download** (si ya tiene zip listo), **↻ Retry N** (si hay fallos/skipped),
  y **🗑 Delete** (oculto mientras el job está `"running"`; pide
  confirmación antes de llamar al `DELETE`).

## Bugs corregidos (2026-09-08)

1. **El historial te sacaba solo de la pantalla.** El polling que sigue el
   progreso de un job (`pollJob()`) forzaba `state.screen = "result"` en
   cuanto el job terminaba, sin mirar en qué pantalla estabas — si abrías
   un job en curso desde History y volvías al listado, en cuanto ese job
   terminaba te expulsaba de vuelta a la pantalla de resultado. Arreglado:
   solo cambia de pantalla si seguías en `"progress"`.
2. **Texto desactualizado.** La pantalla decía que los jobs pequeños "no se
   guardan si el servidor se reinicia" — descripción de antes de que todo
   job se persistiera sin importar el tamaño. Corregido a "guardado 30
   días".
3. **Borrado manual añadido.** Antes solo se podía esperar los 30 días de
   retención automática; ahora se puede borrar un job a mano desde la UI o
   con `DELETE /jobs/{job_id}`.
