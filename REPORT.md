# Ingeniería inversa de Ultralytics HUB con REA

Fecha: 2026-11-06 · Herramienta: [REA](https://github.com/morluto/rea) `rea-agents@6.8.0`

## 1. Alcance y qué se pudo analizar

| Componente de HUB | Estado | Motivo |
|---|---|---|
| Web app `hub.ultralytics.com` (bundle JS) | **No analizado** | La red de este entorno bloquea `hub.ultralytics.com`, `platform.ultralytics.com` y `api.ultralytics.com` (el proxy responde 403 a CONNECT). |
| App móvil (Android/iOS) | **No analizado** | No hay APK/IPA local y las fuentes de APK están bloqueadas. |
| **Cliente Python de HUB**: `hub-sdk 0.0.25` | ✅ Analizado | Descargado de PyPI. |
| **Integración HUB en `ultralytics 8.4.100`** (`ultralytics/hub/*`, `callbacks/hub.py`) | ✅ Analizado | Última línea de versiones que trae `ultralytics/hub/`. En 8.4.120 ya no está. |
| **Sucesor, Ultralytics Platform**: `ultralytics-platform 0.1.104` y `callbacks/platform.py` de `ultralytics 8.4.203` | ✅ Analizado | Sustituye a HUB en las versiones actuales. |

Lo que se ve en este informe es **el protocolo cliente↔servidor de HUB tal como lo implementan los clientes que distribuye Ultralytics**. El backend no se observó directamente. Las respuestas del servidor que aparecen aquí son las que el cliente *espera*.

### Instalación de REA

```bash
npm install --global rea-agents      # rea 6.8.0
rea setup --yes --client claude_code # registra el MCP "rea" y el skill reverse-engineer-anything
rea doctor                           # registration: aligned, skill v49, 229 herramientas MCP
```

## 2. Evidencia de REA

Comandos `rea inspect-artifact` (inventario de los wheels) y `rea inspect-python-pyc` (objetos de código del bytecode compilado). La evidencia completa está en `evidence/rea/`.

| Artefacto | SHA-256 (prefijo) | Evidence ID (padre) | Nodos |
|---|---|---|---|
| `hub_sdk-0.0.25-py3-none-any.whl` | `b8046e49c17257f9` | `ev_6f905fe685249ea2f…` | 24 |
| `ultralytics-8.4.100-py3-none-any.whl` | `ee9d98cc570d673f` | `ev_25e62a938b9b32db5…` | 364 |
| `ultralytics_platform-0.1.104-py3-none-any.whl` | `8a09fe768cdc30c3` | `ev_be78e213bcb19b900…` | 36 |
| `server_clients.pyc` (hub-sdk, CPython 3.13) | — | `ev_86f6211baf395395e…` | 18 objetos de código |
| `session.pyc` (ultralytics.hub) | — | `ev_bde594ab8b58ce763…` | 16 objetos de código |

Límite declarado por REA: el inventario ZIP no establece el comportamiento en tiempo de ejecución. Ese comportamiento se verificó aparte (§5).

## 3. Arquitectura del cliente HUB (legado)

```
yolo train model=https://hub.ultralytics.com/models/<ID>
        │
        ▼
ultralytics/utils/callbacks/hub.py  ── callbacks del Trainer (solo si SETTINGS["hub"])
        │   on_pretrain_routine_start → HUBTrainingSession.create_session()
        │   on_fit_epoch_end          → cola de métricas (subida cada ≥3 s)
        │   on_model_save             → checkpoint (cada ≥900 s)
        │   on_train_end              → subida final de best.pt + mAP
        ▼
ultralytics/hub/session.py  HUBTrainingSession  (reintentos, backoff 2^i, cola de métricas fallidas)
        ▼
hub_sdk.HUBClient(Auth)  ──► Models / Datasets / Projects / Users (CRUDClient, PaginatedList)
        ▼                     ModelUpload / DatasetUpload / ProjectUpload (server_clients.py)
https://api.ultralytics.com/v1/...   (variable de entorno ULTRALYTICS_HUB_API)
```

### 3.1 Autenticación

- Cabecera `x-api-key: <API_KEY>`, o bien `authorization: Bearer <idToken>` (Firebase).
- Validación: `POST /v1/auth`, que devuelve `{"success": true|false}`.
- Una clave con formato `KEY_MODELID` se corta en `_`. Solo se usa la parte de la clave.
- En Colab, `POST /v1/auth/auto` con `credentials: 'include'` se inyecta como JavaScript en el notebook y reutiliza la cookie del navegador para obtener un `idToken`.
- Login con email y contraseña (`HUBClient.authorize`): `FIREBASE_AUTH_URL` apunta por defecto a `http://localhost:9099/...signInWithPassword?key=FIREBASE_API_KEY`, que es el **emulador de Firebase** con una clave de relleno. En producción este camino no funciona salvo que se configure `ULTRALYTICS_FIREBASE_AUTH_URL`.
- La clave se guarda en `settings.json` de Ultralytics (`SETTINGS["api_key"]`).

### 3.2 Endpoints de HUB (base `https://api.ultralytics.com`)

| Método | Ruta | Uso | Cuerpo |
|---|---|---|---|
| POST | `/v1/auth` | Validar credenciales | — |
| POST | `/v1/auth/auto` | Auth por cookie (Colab) | — |
| GET/POST/PATCH/DELETE | `/v1/{models,datasets,projects,users,teams}[/{id}]` | CRUD genérico (`DELETE ?hard=`) | JSON |
| GET | `/v1/{models,datasets,projects}?limit=&last_doc_id=&query=&public=` | Paginación por cursor (`data.results`, `data.total`, `data.lastRecordId`) | — |
| POST | `/v1/models` | Crear modelo | `{config:{batchSize,epochs,imageSize,patience,device,cache}, dataset:{name}, lineage:{architecture:{name}, parent:{name}}, meta:{name}}` |
| POST | `/v1/models/{id}` | Subir métricas | `{"type":"metrics","metrics":{"<epoch>":"<json str>"}}` |
| POST | `/v1/models/{id}/upload` | Checkpoint | multipart: `last.pt`, `epoch`, `type=epoch`, `isBest` |
| POST | `/v1/models/{id}/upload` | Modelo final | multipart: `best.pt`, `epoch`, `type=final`, `map` |
| GET | `/v1/models/{id}/metrics` | Leer métricas | — |
| POST | `/v1/models/{id}/export` | Lanzar exportación | `{"format": "..."}` |
| POST | `/v1/agent/heartbeat/models/{id}` | Heartbeat del agente de entrenamiento (cada 300 s) | `{"agent":"python-<ver>-local\|colab","agentId":...}` → `data.agentId` |
| POST | `/v1/predict/{id}` | Inferencia remota | multipart `image` + config |
| POST | `/v1/datasets/{id}/upload` | Subir dataset zip | multipart `<filename>` |
| POST | `/v1/projects/{id}/upload` | Imagen de proyecto | multipart `file` |
| POST | `/model-reset` | Resetear modelo (sin prefijo `/v1`) | `{"modelId"}` |
| POST | `/get-export` | URL de exportación (sin `/v1`) | `{"apiKey","modelId","format"}`: **la clave también va en el cuerpo** |

Campos del modelo que el cliente interpreta: `status` (`"trained"`), `has_last_weights` (permite reanudar), `has_best_weights`, `is_pretrained`, `is_custom`, `weights` (URL de best/parent), `resume` (URL de last), `cfg` (arquitectura), `data` (URL del dataset), `train_args`. El SDK convierte `batch_size/epochs/imgsz/patience/device/cache` a `config.{batchSize,…}` en el cliente.

### 3.3 Máquina de estados de entrenamiento

1. Si el identificador es una URL `…/models/<ID>[?api_key=]`, `load_model`. Si es `*.pt`/`*.yaml`, `create_model`.
2. Si el modelo ya está `trained`, se descargan los pesos `best` a `weights_dir/hub/<id>` y no se entrena.
3. Si tiene `has_last_weights`, se fija `train_args = {data: <url dataset>, resume: True}` con los pesos `last`. Si no, se usan `train_args` del servidor y los pesos `parent` o `cfg`.
4. Se arranca el heartbeat en un hilo daemon y se registran handlers de SIGINT y SIGTERM.
5. Límites de frecuencia en el cliente: métricas cada 3 s, checkpoint cada 900 s, heartbeat cada 300 s.
6. Reintentos: códigos 408/502/504 con backoff `2^i`. En 429 se leen las cabeceras `X-RateLimit-Remaining/Limit` y `Retry-After`. La subida final hace hasta 10 reintentos en 3600 s.

## 4. El sucesor: Ultralytics Platform

En `ultralytics ≥ 8.4.120` el módulo `ultralytics.hub` desaparece. Lo reemplazan `callbacks/platform.py` y el paquete `ultralytics-platform` (requiere Python 3.11 o superior).

- Base: `https://platform.ultralytics.com` (`ULTRALYTICS_PLATFORM_URL`). Las rutas van bajo `/api/...` y se autentican con `Authorization: Bearer <ul_…>`.
- **Las claves antiguas de HUB se borran.** Al migrar `settings.json`, toda clave que no cumpla `^ul_[0-9a-f]{40}$` se elimina y se muestra el aviso "Legacy API key removed".
- El entrenamiento pasa a ser por eventos: `POST /api/webhooks/training/metrics` con `event ∈ {training_started, epoch_end, console_output, checkpoint_saved, training_complete}`. Se identifica con `model_id` o con `project`+`name`.
- La respuesta puede traer `{"cancelled": true}`, que pone `trainer.stop = True`. Es decir, **el entrenamiento se puede cancelar en remoto desde la web**.
- Checkpoints: `POST /api/webhooks/models/upload` devuelve `uploadUrl` firmada (GCS) y `gcsPath`. La subida se hace directamente a GCS y luego se confirma con el evento `checkpoint_saved`.
- Telemetría que se envía en `training_started`: hostname, OS, ruta de `python`, CPU, RAM, disco, GPU, **origen, rama, commit y mensaje del repo git**, y todos los `trainArgs`. `console_output` sube la salida de consola por bloques.
- Hook poco visible (`_hooks.py`): tras un `POST` correcto a `…/ingest` o `…/training/start`, el SDK hace `GET http://127.0.0.1:8765/wake` con `Origin: <platform>`. Sirve para despertar un agente local, si existe.
- La tabla completa de **95 endpoints** se extrajo por AST, sin importar ni ejecutar el SDK: [`evidence/platform_endpoints.md`](evidence/platform_endpoints.md) y `evidence/platform_endpoints.json`. Generador: `tools/extract_platform_endpoints.py`.

## 5. Verificación dinámica (cliente real contra un servidor simulado)

`tools/mock_hub_server.py` reimplementa la API v1 descrita en §3.2. `tools/verify_hub_sdk.py` ejecuta el `hub-sdk 0.0.25` real contra ese servidor. Las peticiones capturadas están en `evidence/mock_hub_requests.jsonl` y la salida en `evidence/verify_hub_sdk.out`.

```
auth_ok: True                               # POST /v1/auth con x-api-key
bad_key_rejected: True
model_config_reshaped: True                 # imgsz → config.imageSize
heartbeat_agent_id: AGENT-1                 # agentId devuelto y reutilizado
users_data_empty_bug: True
teamlist_hits_datasets_endpoint_bug: True
teamlist_headers_passed_as_public_bug: True
```

Las peticiones capturadas confirman los campos multipart `["epoch","isBest","last.pt","type"]` del checkpoint y `["best.pt","epoch","map","type"]` del modelo final.

Para reproducir:

```bash
python3 tools/mock_hub_server.py --log /tmp/req.jsonl &
pip install hub-sdk==0.0.25 && python3 tools/verify_hub_sdk.py
```

## 6. Defectos encontrados (observados o verificados)

| # | Defecto | Evidencia |
|---|---|---|
| 1 | `Users` y `Teams` llaman a `self._reconstruct_data`, que solo existe en `Models`. El `AttributeError` se captura en silencio y `.data` queda en `{}`. | Verificado (§5) |
| 2 | `TeamList` consulta `/v1/datasets` en lugar de `/v1/teams`, y pasa `headers` en la posición de `public`. Resultado: `GET /v1/datasets?public=x-api-key` sin cabecera de auth, que devuelve 401. | Verificado (§5) |
| 3 | `callbacks/hub.py:on_train_end` hace `session.alive = False` para "parar los heartbeats", pero el flag real es `session.model.hub_client.alive`. El heartbeat sigue hasta que termina el proceso (el hilo es daemon). | Estático (`grep alive`) |
| 4 | El heartbeat envía `agent = python-<versión de CPython>` (p. ej. `python-3.13.18-local`), no la versión de ultralytics como hace `ultralytics.hub.session.AGENT_NAME`. | Verificado en el tráfico capturado |
| 5 | Login con email y contraseña apunta por defecto al emulador de Firebase en `localhost:9099` con `key=FIREBASE_API_KEY`. | Estático (`config.py`) |
| 6 | `/get-export` manda la API key en el cuerpo JSON además de en la cabecera, así que aparece en los logs de cuerpos. | Estático |
| 7 | `start_heartbeat` reemplaza los handlers globales de SIGINT y SIGTERM del proceso por `sys.exit(signum)`. | Estático |
| 8 | `upload_model` y `upload_dataset` leen el archivo entero en memoria (`f.read()`) antes de enviarlo. | Estático |

## 7. Pendiente / desconocido

- **Web app y app móvil**: sin analizar por la red. Con acceso a `hub.ultralytics.com` / `platform.ultralytics.com` el siguiente paso es `rea analyze-web-bundle` / `rea capture-browser-scenario` y, para Android, `rea inspect-android-package` sobre el APK.
- El comportamiento real del backend (validaciones, códigos de error, límites de cuota) **no se observó**. El servidor simulado es una reconstrucción a partir de lo que el cliente espera.
- No se sabe si `api.ultralytics.com/v1` sigue en servicio tras la migración a Platform.

## Archivos

- `tools/extract_platform_endpoints.py`: extractor AST de endpoints de `ultralytics-platform`
- `tools/mock_hub_server.py`: servidor HUB v1 simulado que registra las peticiones
- `tools/verify_hub_sdk.py`: verificación del protocolo y de los defectos con el SDK real
- `evidence/rea/`: evidencia de REA (`inspect-artifact`, `inspect-python-pyc`)
- `evidence/platform_endpoints.{md,json}`, `evidence/mock_hub_requests.jsonl`, `evidence/verify_hub_sdk.out`
