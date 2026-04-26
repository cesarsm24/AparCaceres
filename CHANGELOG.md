# Changelog

Todas las novedades reseñables del proyecto se documentan en este fichero.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y
las versiones siguen [SemVer](https://semver.org/lang/es/). Cada release que se
publique como release de producción debe estar etiquetada en git
(`git tag vX.Y.Z`).

## [Unreleased]

### Added
- Estructura para releases futuros.

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
