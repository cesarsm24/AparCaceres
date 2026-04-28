# Changelog

Todas las novedades reseñables del proyecto se documentan en este fichero.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y
las versiones siguen [SemVer](https://semver.org/lang/es/). Cada release que se
publique como release de producción debe estar etiquetada en git
(`git tag vX.Y.Z`).

## [Unreleased] — Fase 2 + Fase 3 oportunista

Cierra la "Fase 2 — producción" del informe técnico (cliente Redis async,
autenticación firmada, rate limiting, métricas, doble buffer de imports y
guía operativa de despliegue) e incorpora la "Fase 3 oportunista" con el
subconjunto de items independientes implementables sobre la fase 2 ya
cerrada. Pendiente de tagear cuando se decida el corte de release.

Fase 3 (oportunista): empezada con un subconjunto de items independientes
del resto de la fase 3. Quedan fuera por ahora soporte multi-ciudad,
testcontainers (CI ya tiene Redis Stack como service) y cluster con
hash-tags (prematuro sin métricas).

### Added (Fase 3)
- **Resolución de fotos durante el import**: nuevo módulo
  `app/photo_resolver.py` que descarga las fichas del SIG municipal
  (`fichatoponimia.php` / `fichacalle.php`) y extrae la `<img>` de
  `/fotosOriginales/...` con un regex acotado. El importador la invoca
  para los places que no traen `URL_FOTO` explícita (todos menos
  `movilidad_reducida` y `parking_bicis`), con concurrencia controlada
  por semáforo (`PHOTO_FETCH_CONCURRENCY=20`) y caché Redis aparte
  (`parking_photo:{id}`, TTL 90 días) que cachea también el "no hay
  foto" como sentinel vacío para no rescraperar fichas estériles.
  Fallos de red o ficha 404 se tratan como "sin foto" sin abortar el
  import. Configurable por env (`FETCH_PHOTOS=true|false`,
  `PHOTO_FETCH_CONCURRENCY`, `PHOTO_FETCH_TIMEOUT_SECONDS`,
  `PHOTO_CACHE_TTL_SECONDS`). El summary del importer expone
  `photos_resolved`. Cliente móvil sin cambios (`ParkingThumbnail` ya
  consume `imageUrl` y cae al placeholder cuando es `None`).
- **Caché de `/parkings/nearby` con filtros de baja cardinalidad**: la clave
  canónica incorpora ahora `vehicleType`/`category`/`regulation`/`dataset`/
  `minSpaces` ordenados alfabéticamente, así que la combinación típica del
  cliente (centro + chip de filtro) reutiliza la misma entrada en lugar de
  hacer `BYPASS`. Solo `q`/`ids`/`limit`/`offset` siguen forzando bypass
  porque inflan la cardinalidad de la clave hasta hacerla contraproducente.
- **Logging cuando se descartan componentes de `MultiPolygon`/`MultiLineString`**
  en el importador: una entrada `INFO` por feature con más de una componente,
  con `dataset:hint_id`, `total`, `kept_index` y `dropped`. Facilita auditar
  datasets con digitalización heterogénea sin reventar el import.
- **Cap y TTL en favoritos por usuario**: `FAVORITES_MAX_PER_USER` (default
  500) recorta los más antiguos con `ZREMRANGEBYRANK` cuando se excede, y
  `FAVORITES_TTL_SECONDS` (default 365 días) renueva el TTL del sorted set
  en cada `PUT` como heartbeat de actividad. Ambos configurables por env;
  `FAVORITES_MAX_PER_USER=0` desactiva el cap (modo legacy).
- Tests nuevos: `test_polygon_centroid_weights_by_area_for_asymmetric_l`,
  `test_polygon_centroid_falls_back_when_collinear`,
  `test_favorites_cap_drops_oldest_when_max_reached`,
  `test_favorites_cap_disabled_when_zero`,
  `test_nearby_caches_low_cardinality_filters`,
  `test_nearby_cache_key_is_filter_aware`,
  `test_nearby_bypasses_cache_for_text_search`. Suite total: 227 tests.

### Changed (Fase 3)
- **`/parkings` y `/parkings/in-bounds` evitan el round-trip extra**:
  `FT.SEARCH` se llama sin `NOCONTENT`, así devuelve los hashes completos
  en la misma respuesta (antes: `FT.SEARCH NOCONTENT → ids → pipeline
  HGETALL`). Reduce a la mitad las llamadas Redis por request.
- **`/parkings/nearby` usa `FT.AGGREGATE … LOAD *`**: una sola llamada
  carga el hash completo + el `distance` calculado por `APPLY geodistance`,
  eliminando el pipeline `HGETALL` posterior. La respuesta se hidrata
  directamente como `ParkingPlaceNearbyOut`.
- **Centroide de polígono ponderado por área (Shoelace)** en
  `representative_point`: para polígonos no convexos el resultado siempre
  cae dentro de la envolvente convexa (el promedio aritmético podía
  salirse). Para polígonos colineales o degenerados cae al promedio
  aritmético como fallback para no perder el feature.
- `_load_places` eliminado de `app/search.py` al quedar sin callers tras
  la migración a `FT.SEARCH` con payload.

### Added (mobile · integración con backend)
- **`ApiClient` HTTP** sobre `package:http`: timeouts uniformes (10 s),
  cancelación cooperativa (`CancelToken`), inyección opcional de
  `Authorization: Bearer`, mapeo de fallos a `ApiException`/
  `ApiUnavailableException`/`ApiTimeoutException`/`ApiCancelledException`,
  y logging de cabeceras útiles (`X-Cache`, `X-Total-Count`,
  `X-RateLimit-Remaining`, `X-Request-ID`) en modo debug.
- **`ApiParkingRepository`** consume los endpoints reales:
  `GET /parkings`, `GET /parkings/nearby` (con `lat`/`lng`/`radiusMeters`),
  `GET /parkings/categories`, `GET /parkings/{id}` (404 → `null`) y
  `GET /users/me/favorites` con bearer.
- **`AuthSession`**: genera un `sub` aleatorio (24 hex) en el primer
  arranque, lo persiste en `SharedPreferences` y lo intercambia por un
  JWT vía `POST /auth/session`. Cachea token + `expiresAt`, refresca
  cuando faltan ≤ 1 día y dedupe peticiones concurrentes con una future
  en vuelo compartida.
- **`ServerFavoritesStore`**: cache en memoria con `contains` síncrono
  para el corazón; `add`/`remove`/`toggle` optimistas que disparan
  `PUT`/`DELETE /users/me/favorites/{id}` y revierten en error.
  `reload()` consume `GET /users/me/favorites` y solo notifica si hay
  diff (sin bucles con `ListenableBuilder`).
- **`ApiErrorState`** reutilizable en cada `FutureBuilder`: copia
  diferenciada para timeout, servicio no disponible, `detail` 4xx del
  backend o fallo genérico, con botón "Reintentar".
- **Banner "Estás fuera de Cáceres"** en `MapScreen` cuando un fix real
  cae fuera del bbox (`LocationService.isOutsideCaceres`), con CTA al
  picker (que sigue acotado a Cáceres por viewbox de Nominatim).
- **README de `mobile/`** con `--dart-define`s, comandos de tests,
  arquitectura abreviada y checklist de smoke test.
- Tests nuevos: `api_client_test`, `api_parking_repository_test`,
  `auth_session_test`, `server_favorites_store_test`,
  `api_error_state_test` (42 tests en total).

### Changed (mobile · integración con backend)
- **Cámara inicial del mapa** alineada con el botón de localización:
  cuando no hay centro explícito, la vista arranca centrada en el último
  fix con `_focusedZoom` (16) en lugar de `_initialZoom` (15) sobre la
  plaza. Misma vista la pulse el usuario o no el icono de "ubicación
  actual".
- **Cancelación de re-búsquedas** en `MapScreen`: cualquier cambio de
  filtros, picker o recentrado cancela la request anterior antes de
  emitir la siguiente; `dispose()` cancela la última pendiente.
- **`HomeScreen` y `FavoritesScreen` pasan a `StatefulWidget`** para que
  la `Future` se construya una sola vez y no se rehagan llamadas a la
  API en cada rebuild.
- **`FavoritesStore` ahora es abstracto**, con `LocalFavoritesStore`
  (modo demo) y `ServerFavoritesStore` (producción). El global
  `favoritesStore` se selecciona por `--dart-define=USE_LOCAL_DATA`.
- **`getFavorites()` simplificado**: deja de pasar por `/parkings?ids=`
  y consume `/users/me/favorites` directamente, que ya devuelve los
  `ParkingPlaceOut` ordenados por fecha de adición.

### Added (Fase 2)
- Auth firmada para favoritos: nuevo módulo `app/auth.py` con JWT HS256
  (`Authorization: Bearer <token>` o `X-Session-Token`) y endpoint
  `POST /auth/session` que emite tokens con TTL de 30 días. Sustituye al
  `X-User-Id` opaco previo y endurece el aislamiento entre usuarios.
- Rate limiting por IP con `slowapi`: 1/min en `POST /import-parkings` y
  120/min en `GET /parkings/nearby`. Configurable vía `RATE_LIMIT_ENABLED`.
- Métricas Prometheus en `/metrics` con
  `prometheus-fastapi-instrumentator`. Excluye `/healthz` y `/metrics` de
  los logs de acceso para no inundar el JSON con scrapes.
- Documentación operativa en `docs/operations.md`: topología nginx + TLS,
  configuración de variables en producción, runbook rápido y procedimiento
  de restore desde backup.
- Procedimiento de backup de Redis documentado sin helper versionado:
  snapshot manual con `BGSAVE`, copia de `dump.rdb` y `appendonlydir/`,
  y sincronización off-site definida en la guía operativa.
- Tests para `GET /healthz`, `RequestIdMiddleware` y versionado de
  `cache:version` (cierre de la fase 1 que se coló en esta rama).

### Changed
- Cliente Redis dual: `redis.asyncio.Redis` con `ConnectionPool`
  (`max_connections=50`, `health_check_interval=30`, `socket_keepalive`,
  `retry_on_timeout`) como cliente principal de los handlers async.
  Mantiene un cliente síncrono para el importador y para `app/search.py`,
  que se invocan vía `asyncio.to_thread` para no bloquear el event loop.
  Routers `health`, `favorites` y `parkings/{id}` resueltos directamente
  en async sin threadpool.
- Importador con doble buffer: la nueva generación se construye bajo
  `parking_v2:*` con su propio índice `idx:parkings_search_v2`. El swap al
  catálogo activo (drop + UNLINK + RENAME + recreación de índice) es la
  única ventana en la que las lecturas pueden ver datos a medias; antes
  era toda la duración del import.
- `RequestIdMiddleware` ahora se monta DESPUÉS de `CORSMiddleware` para que
  sea el outermost: el `X-Request-ID` se asigna también en las respuestas
  de preflight `OPTIONS`. (Cierre de un detalle de la fase 1 detectado al
  revisar el orden de middlewares.)
- Docstrings en `importer.py` y `routers/imports.py` actualizados para
  reflejar `INCR cache:version` y `UNLINK` en lugar del SCAN+DEL antiguo.

### Dependencies
- `slowapi==0.1.9`, `prometheus-fastapi-instrumentator==7.0.0`,
  `PyJWT==2.10.1` añadidas como directas. Lockfile actualizado con sus
  transitivas.
- `httpx>=0.27,<1` movida a runtime (antes solo en `requirements-dev`
  para `TestClient`). La usa el resolutor de fotos para scrapear
  fichas SIG con cliente async + timeouts.

### Hardening (Redis quick wins)
- **Socket timeouts en los clientes Redis** (`socket_timeout=5s`,
  `socket_connect_timeout=2s`) para acotar el peor caso ante conexiones
  colgadas: antes un comando podía esperar hasta el siguiente tick de
  `health_check_interval` (30 s).
- **`/healthz` reporta `degraded` cuando el índice está vacío**
  (`num_docs == 0`): antes el handler devolvía 200 aunque el catálogo no se
  hubiese importado, dejando réplicas servidoras de listas vacías en el
  rotation del balanceador. Ahora retorna 503 con `search_index.status:
  "empty"`.
- **`geometryType` fuera del esquema RediSearch** y enums fuera del campo
  `searchText`: el filtro por geometría no se usa desde el cliente y los
  enums ya están como `TAG` con filtros dedicados; mezclarlos en `TEXT`
  provocaba que `q="blue_zone"` trajera resultados que el usuario quería
  aislar con el chip de filtro.
- **slowapi con storage Redis** (`storage_uri` configurable, default al
  Redis del servicio). Antes cada worker contaba en memoria local: con dos
  workers el cupo efectivo se duplicaba. Ahora el cupo es global y honesto
  entre réplicas. `RATE_LIMIT_STORAGE_URI` permite forzar otro backend en
  tests/CI.
- **Precisión adaptativa en la clave de caché de `/parkings/nearby`**:
  `decimals = max(4, ceil(log10(111_000 / radius)))`. Con 4 decimales fijos
  el bucket era ~11 m, así que para radios pequeños (<11 m) dos centros
  distintos colisionaban. Ahora el bucket nunca supera al propio radio.
- Tests: `test_healthz_503_when_search_index_is_empty`,
  `test_nearby_cache_key_precision_adapts_to_radius`,
  `test_nearby_cache_key_distinguishes_close_centers_for_small_radius`.
  Suite total: 230 tests.

### Removed
- **`parkings_en_superficie.geojson` eliminado del repo y de toda referencia
  en código, docs, tests y respuesta del importador**. El fichero (15.000+
  LineStrings genéricas sin propiedades) llevaba excluido vía
  `EXCLUDED_DATASET_FILENAMES` desde fase 1; ahora se trata como si no
  hubiese existido nunca: el constante de exclusión, el campo
  `excluded_datasets` del summary del importer y los tests que verificaban
  el filtrado se eliminan también. Suite: 229 tests.

### Fixed
- **`POST /import-parkings` devolvía 500** en producción al activar el
  rate limiter: el handler no aceptaba `response: Response` y `slowapi`
  fallaba al inyectar `X-RateLimit-*` con `headers_enabled=True`. La suite
  no lo cogía porque `RATE_LIMIT_ENABLED=false` hace el decorador no-op;
  añadido test de regresión que activa el limiter explícitamente.

## [0.1.0] - 2026-04-26

Primera versión etiquetada del backend. Sirve de baseline para staging tras
la "Fase 1 — endurecimiento mínimo para staging" del informe técnico.

### Added
- Endpoint `GET /healthz` con comprobación de Redis (`PING`) y RediSearch
  (`FT.INFO`); devuelve 503 cuando alguna dependencia crítica está caída,
  con desglose por componente.
- Middleware `RequestIdMiddleware` que asigna y propaga `X-Request-ID` por
  request (lo respeta si llega del cliente o lo genera con UUID4).
- Logging estructurado JSON (`app/logging_config.py`) con `request_id` por
  línea, sin dependencias externas. Nivel raíz controlable con `LOG_LEVEL`.
- Variable de entorno `APP_ENV` para distinguir defaults de desarrollo y
  producción (afecta hoy a CORS).
- `Dockerfile` multi-stage del backend (Python 3.11 slim, usuario no root,
  HEALTHCHECK contra `/healthz`) y `.dockerignore` asociado.
- `docker-compose.yml` raíz con Redis Stack 7.4 (AOF habilitado, snapshots
  RDB, volumen `redis-data`) y la API conectada a él.
- Workflow `.github/workflows/backend-ci.yml`: ruff + pytest contra Redis
  Stack como servicio del runner.
- `requirements.in` (dependencias directas) separado de `requirements.txt`
  (lockfile). `requirements-dev.txt` añade `pip-tools` y `ruff`.
- `ruff.toml` con configuración mínima alineada al estilo actual.
- `CHANGELOG.md` (este fichero).

### Changed
- **CORS endurecido**: `CORS_ORIGINS` ya no aplica `*` por defecto. Cuando
  `APP_ENV=development` se aplica una whitelist de localhost útil para
  Flutter web; en producción la lista debe declararse explícitamente. Si se
  usa `*` se loggea un warning visible.
- **Invalidación de caché por versionado**: `POST /import-parkings` ya no
  recorre `cache:nearby:*` con `SCAN_ITER + DEL`. Incrementa `cache:version`
  (O(1)) y la clave de caché incluye `v{n}` como namespace; las claves
  antiguas quedan inalcanzables y caducan por su TTL.
- Cleanup masivo del importador (`parking:*`, índices legacy) usa `UNLINK`
  cuando el cliente lo soporta para no bloquear el event loop de Redis.
- La respuesta de `POST /import-parkings` sustituye `cache_invalidated` por
  `cache_version` (entero monotónico).

### Fixed
- El cleanup legacy del importador ya no borra `idx:parkings_search` antes
  de tiempo: ahora se delega íntegramente a `recreate_search_index`.

### Documentation
- `informe.md`: informe técnico del estado del backend que motiva esta fase.
- `.env.example` reescrito: documenta `APP_ENV`, `CORS_ORIGINS`, `LOG_LEVEL`
  y la guía de orígenes para Flutter web frente a clientes nativos.
