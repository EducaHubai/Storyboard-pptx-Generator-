# Cómo desplegar — GitHub + Coolify

Esta guía asume que ya tienes acceso a GitHub y a Coolify en EDUCA EDTECH.
Todo el proyecto (frontend + backend) se despliega como **un solo servicio
Docker**.

---

## 0. Conseguir la API key de OpenAI (obligatorio)

El backend llama a **Claude**, no a ChatGPT — necesitas una key distinta.

1. Ve a **platform.openai.com**
2. Crea una cuenta de organización (o únete a la de EDUCA EDTECH si ya existe)
3. **Settings → API Keys → Create Key**
4. Copia la key (empieza por `sk-...`) — la necesitarás en el paso 3

OpenAI da algo de crédito gratuito al crear la cuenta; para uso real de
equipo conviene cargar saldo en **Settings → Billing**.

---

## 1. Subir el código a GitHub

1. Crea un repo nuevo en GitHub, por ejemplo `storyboard-generator`
2. Descarga la carpeta `storyboard-app/` completa (todos los archivos
   adjuntos a este mensaje, manteniendo la misma estructura de carpetas)
3. Súbela al repo:

```bash
git init
git add .
git commit -m "Initial commit — storyboard generator"
git branch -M main
git remote add origin https://github.com/TU-ORG/storyboard-generator.git
git push -u origin main
```

Si no tienes git en tu máquina, también puedes arrastrar los archivos
directamente desde la interfaz web de GitHub ("Add file → Upload files"),
respetando la estructura de carpetas exacta.

**Estructura final del repo:**
```
storyboard-generator/
├── Dockerfile
├── .dockerignore
├── .gitignore
├── server/
│   ├── index.js
│   ├── package.json
│   ├── storyboard.schema.json
│   └── system-prompt-upload-pdf.md
└── client/
    ├── package.json
    ├── public/
    │   └── index.html
    └── src/
        ├── index.js
        └── App.jsx
```

---

## 2. Crear el servicio en Coolify

1. Entra a tu instancia de Coolify
2. **Create → App** (o "Service" según la versión)
3. Elige **Source: GitHub** y conecta/selecciona el repo
   `storyboard-generator`, rama `main`
4. **Build method: Dockerfile** — Coolify detectará el `Dockerfile` en la
   raíz automáticamente
5. **Port: 3000** (coincide con `EXPOSE 3000` del Dockerfile y con
   `PORT=3000` por defecto en `server/index.js`)

---

## 3. Configurar la variable de entorno

En la sección **Environment** del servicio en Coolify, añade:

| Variable | Valor |
|---|---|
| `OPENAI_API_KEY` | tu key de platform.openai.com (`sk-...`) |

Esto es lo único que necesita configuración manual — todo lo demás está
ya resuelto en el código.

---

## 4. Dominio

Coolify suele asignar un subdominio automático (algo como
`storyboard-generator.tu-dominio.coolify.host`), o puedes apuntar un
dominio propio (`storyboard.educaedtech.com`) desde **Domains** en el panel
del servicio, con el DNS apuntando a tu servidor Coolify.

---

## 5. Deploy

Pulsa **Deploy**. Coolify:
1. Clona el repo
2. Construye la imagen Docker (compila el React, instala las dependencias
   del backend)
3. Levanta el contenedor en el puerto configurado

La primera build tarda 2-4 minutos. Verás los logs en tiempo real dentro
de Coolify — si algo falla, ahí aparecerá el error exacto (normalmente
faltará la variable de entorno o habrá un typo en algún `package.json`).

---

## 6. Verificar que funciona

Visita `https://tu-dominio/api/health` — debería devolver:

```json
{ "ok": true, "openaiConfigured": true }
```

Si `openaiConfigured` sale en `false`, revisa que la variable
`OPENAI_API_KEY` esté bien guardada en Coolify y vuelve a desplegar
(algunos paneles requieren un "Redeploy" después de cambiar env vars).

Luego visita `https://tu-dominio/` directamente — deberías ver la pantalla
de upload de la app. Sube un PDF de prueba y confirma que el flujo completo
funciona: storyboard generado → selección de gráficos → descarga del .pptx.

---

## Actualizaciones futuras

Cada vez que hagas `git push` a `main`, puedes configurar Coolify para
re-desplegar automáticamente (webhook de GitHub), o hacerlo manualmente
pulsando **Deploy** de nuevo en el panel.

---

## Si algo falla — checklist rápido

| Síntoma | Causa probable |
|---|---|
| Build falla en Coolify | Revisa los logs — normalmente falta un archivo o hay un typo en `package.json` |
| La web carga pero "Failed to fetch" al subir PDF | `OPENAI_API_KEY` no configurada o el deploy no se refrescó tras añadirla |
| `/api/health` da 404 | El servicio no está sirviendo bien — revisa que el puerto en Coolify coincida con el `EXPOSE 3000` del Dockerfile |
| El storyboard sale en inglés "raro" o mal formateado | Revisa `server/system-prompt-upload-pdf.md` — puedes editarlo directamente en el repo para ajustar el tono o el idioma por defecto |
| pptx con gráficos en blanco | Los 10 tipos de gráfico no están todos implementados todavía en `server/index.js` (`renderGraphic`) — `before_after`, `smart_grid` y `data_table` ya funcionan; el resto hay que portarlos siguiendo el mismo patrón (pide ayuda si necesitas que los complete) |
