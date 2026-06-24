# Chat con IA — cómo funciona

Melomano tiene un asistente de IA integrado en dos lugares:

- **Chat general** (burbuja 💬 abajo a la derecha en cualquier página): responde sobre tu colección, recitales y bares, usando datos reales de tu cuenta.
- **Chat por disco** (botón "🤖 Resumen del disco" en la página de cada álbum): habla únicamente sobre ese disco puntual.

No es magia: el modelo de IA no tiene acceso directo a la base de datos. El backend consulta tus datos con SQLAlchemy, los convierte en texto y se los "lee" al modelo antes de cada respuesta. A esto se le llama **RAG simplificado** (Retrieval-Augmented Generation).

## 1. Proveedor y modelo actual

- **Proveedor:** [Groq](https://groq.com) — free tier sin tarjeta de crédito.
- **Modelo:** `llama-3.3-70b-versatile` (Llama 3.3, 70B parámetros). Es más preciso que modelos chicos como `llama-3.1-8b-instant`, a cambio de tardar un poco más en responder.

Por qué Groq y no otro: probamos primero Gemini (Google AI Studio), pero su free tier exige vincular tarjeta de crédito para activar la cuota real (aunque no cobra mientras te mantengas debajo del límite). Groq no pide tarjeta en ningún momento — cero riesgo de cobro.

## 2. Cómo conseguir tu propia API key

1. Entrá a **https://console.groq.com/keys**
2. Iniciá sesión (podés usar tu cuenta de Google, no pide tarjeta)
3. Click en **"Create API Key"**, le ponés un nombre (ej: `Melomano`) y la copiás — Groq la muestra una sola vez.

## 3. Configuración (variables de entorno)

En el archivo `.env`, sección "Chat IA":

```env
AI_BASE_URL=https://api.groq.com/openai/v1
AI_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxxxxxx
AI_MODEL=llama-3.3-70b-versatile
```

Después de cambiar el `.env`, hay que **recrear el contenedor** (no alcanza con un restart) para que tome la nueva variable:

```bash
docker compose up -d
```

### Cambiar de proveedor/modelo

El cliente (`app/services/ai_chat.py`) habla el formato **compatible con OpenAI** (`/chat/completions`), que también usan Gemini y OpenRouter. Cambiar de proveedor es modificar solo esas 3 variables, sin tocar código:

| Proveedor | `AI_BASE_URL` | Necesita tarjeta |
|---|---|---|
| Groq (actual) | `https://api.groq.com/openai/v1` | No |
| Google Gemini | `https://generativelanguage.googleapis.com/v1beta/openai` | Sí, para activar cuota real |
| OpenRouter | `https://openrouter.ai/api/v1` | No, para los modelos marcados `:free` |

Modelos más rápidos pero menos precisos en Groq: `llama-3.1-8b-instant`.

## 4. Límites del free tier (Groq, `llama-3.3-70b-versatile`)

Se pueden ver en vivo desde la app: **menú → 🤖 IA** (solo visible/accesible para el usuario admin). Esa página muestra:

- Requests restantes hoy (límite diario)
- Tokens restantes en el minuto actual
- Cuándo se reinicia cada contador

También se puede consultar directo en https://console.groq.com/settings/limits.

Para un uso personal normal (unos pocos mensajes por día) es prácticamente imposible quedarse sin cuota.

## 5. Qué contexto recibe la IA

### Chat general (`/api/chat`)
Antes de cada respuesta, se le pasa un resumen armado con queries reales a la base:
- Total de discos, cuántos en colección / escuchados / wishlist
- Conteo de discos por formato (Vinyl, CD, etc.)
- Total de recitales y bares hifi registrados
- Listado de bateas (ubicación física) y qué discos contiene cada una

Todo esto **filtrado por el usuario logueado** — cada persona solo ve su propia colección.

### Chat por disco (`/api/chat/album/{id}`)
Se le pasa todo lo que se sabe de ESE disco puntual:
- Título, artista, año (aclarando que es el año de la edición/pressing, no necesariamente el original), género, sello, formato
- Puntuación y reseña personal del usuario
- En qué batea está ubicado
- Si el disco está vinculado a Discogs (`discogs_id`): tracklist, notas del release, país de la edición, rating promedio, y cuánta gente lo tiene/quiere en Discogs

## 6. Reglas que le imponemos al modelo

Tanto el chat general como el de disco tienen instrucciones explícitas en el "system prompt" para que:
- Solo use los datos reales que se le pasan (si no tiene el dato, que lo diga, no que invente)
- No hable de temas fuera de música/discos/recitales/bares de la app (nada de programación, noticias, etc.)
- El chat de disco además solo puede hablar de ESE disco, ignorando cualquier otro tema
- Nunca puede "ejecutar" acciones (borrar, modificar, crear) — solo responde con texto

Estas reglas son instrucciones de prompt, no una barrera de seguridad infalible — son suficientes para el uso normal de la app, pero no reemplazan permisos reales a nivel de base de datos (que de hecho no tiene: el modelo nunca puede tocar la base, solo leer lo que el backend le pasa en el contexto).

## 7. Archivos relevantes

| Archivo | Qué hace |
|---|---|
| `app/services/ai_chat.py` | Cliente HTTP genérico (formato OpenAI-compatible), streaming, y chequeo de rate limits |
| `app/routers/chat.py` | Endpoints `/api/chat` y `/api/chat/album/{id}`, armado del contexto desde la BD |
| `app/routers/admin_ai.py` | Dashboard de límites de uso (`/admin/ia`), solo admin |
| `app/templates/base.html` | Widget de chat flotante (general) |
| `app/templates/albums/detail.html` | Panel de chat acotado al disco |
| `app/templates/admin/ia.html` | Vista del dashboard de límites |
| `.env` | Variables `AI_BASE_URL`, `AI_API_KEY`, `AI_MODEL` |
