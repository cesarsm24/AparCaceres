# Changelog

Todas las novedades reseñables del proyecto se documentan en este fichero.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y
las versiones siguen [SemVer](https://semver.org/lang/es/). Cada release que se
publique como release de producción debe estar etiquetada en git
(`git tag vX.Y.Z`).

## [Unreleased] — Fase 2 (en progreso) + Fase 3 oportunista

Trabajo en curso hacia v0.2.0 ("Fase 2 — producción" del informe técnico).
Pendiente Fase 2: migración del cliente Redis a `redis.asyncio` con
connection pool y reintentos, documentación de despliegue (reverse proxy +
TLS + backups), y un par de tests adicionales antes del tag.

Fase 3 (oportunista): empezada con un subconjunto de items independientes
de la migración async pendiente. Quedan fuera por ahora soporte multi-ciudad,
testcontainers (CI ya tiene Redis Stack como service) y cluster con
hash-tags (prematuro sin métricas).

### Added (Fase 3)
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
- Cierre de la fase 1: tests para `GET /healthz`, `RequestIdMiddleware` y
  el versionado de caché `cache:version`. (Llegan tarde respecto al tag
  `v0.1.0` original; se cuelan en este release porque convivían en la
  misma rama de trabajo.)

### Changed
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
