<div align="center">

<img src="mobile/assets/images/logo.png" alt="Logo de AparCáceres" width="180" />

# AparCáceres

Localizador de aparcamientos públicos de Cáceres por proximidad.

</div>

## Descripción

AparCáceres es una aplicación móvil que permite buscar los aparcamientos públicos más cercanos a una ubicación dentro de la ciudad de Cáceres.

El proyecto utiliza datos abiertos municipales y pone el foco en **Redis Stack** como base de datos principal para realizar consultas geoespaciales, filtros y búsqueda textual con RediSearch.

## Estructura del repositorio

```
AparCaceres/
├── backend/    API REST en FastAPI + Redis Stack
│   ├── app/core/        Configuración, auth, logging, métricas y rate limit
│   ├── app/infra/redis/ Integración con Redis Stack, búsqueda e importador
│   └── app/routers/     Endpoints HTTP por dominio
└── mobile/     Cliente móvil en Flutter (Material 3)
```

## Objetivo

Permitir al usuario:
- buscar aparcamientos cercanos por latitud, longitud y radio
- filtrar por vehículo, categoría, regulación, plazas mínimas y dataset
- ver los resultados ordenados por distancia
- visualizar los aparcamientos en un mapa
- consultar información básica de cada aparcamiento

## Fuente de datos

- Open Data Cáceres: movilidad, aparcamientos, PMR, motos, bicis, zona azul y carga/descarga.

Datasets activos importados:
- `aparcamientos.geojson` → 24
- `parkings.geojson` → 8
- `aparcamientos_en_bateria.geojson` → 1424
- `aparcamientos_en_linea.geojson` → 4779
- `zona_azul.geojson` → 101
- `carga_descarga.geojson` → 73
- `movilidad_reducida.geojson` → 743
- `parking_bicis.geojson` → 68
- `parking_motos_areas.geojson` → 48
- `parking_motos_puntos.geojson` → 46

Total activo esperado: `7314` features.

## Tecnologías

- **Redis Stack / RediSearch** para almacenamiento, geoespacial, filtros y búsqueda
- Backend en **FastAPI** (Python)
- Cliente móvil en **Flutter** (Material 3)
- Datos en GeoJSON o CSV

## Backend

Requisitos:
- Python `>=3.11`
- Redis Stack con RediSearch habilitado

Estructura interna principal:
- `app/core/` concentra la configuración, autenticación, logging, métricas y rate limiting.
- `app/infra/redis/` contiene el cliente Redis, la búsqueda, el importador y la resolución de fotos.
- `app/routers/` expone la capa HTTP y mantiene la lógica de negocio fuera de los handlers.

### Ejecución local sin Docker

```bash
cd backend
python3.11 -m venv .venv311
. .venv311/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env   # ajustar CORS_ORIGINS, FAVORITES_SECRET, IMPORT_TOKEN, etc.
pytest
uvicorn main:app --reload
```

Tras la primera arrancada hay que poblar el catálogo:

```bash
curl -X POST http://localhost:8000/import-parkings
```

### Ejecución con Docker Compose

`docker-compose.yml` levanta Redis Stack con AOF persistente, la API y el
frontend web. Es la ruta pensada para un despliegue reproducible con Docker:

```bash
cp backend/.env.example backend/.env
# Completar backend/.env con CORS_ORIGINS, FAVORITES_SECRET e IMPORT_TOKEN.
docker compose up -d --build
docker compose logs -f bootstrap
docker compose exec api curl -s http://localhost:8000/healthz | jq
docker compose down       # parar; conserva el volumen redis-data
docker compose down -v    # parar y BORRAR los datos persistentes
```

### CORS

El cliente nativo Android/iOS no envía cabecera `Origin`, por lo que CORS no
le afecta. Solo hace falta declarar orígenes para Flutter web
(`flutter run -d chrome`) o paneles web futuros.

| Entorno      | `CORS_ORIGINS` recomendado                                    |
|--------------|---------------------------------------------------------------|
| Compose local| `http://localhost:5000` si el frontend se sirve desde el puerto expuesto |
| Staging      | URL pública del Flutter web de staging                        |
| Producción   | Lista explícita de dominios reales. Nunca `*`                 |

### Healthcheck

`GET /healthz` comprueba `PING` a Redis y `FT.INFO` sobre el índice
`idx:parkings_search`. Devuelve 200 cuando todo está sano y 503 con desglose
por componente cuando algo falla. Recomendado como liveness/readiness probe en
Kubernetes y como `HEALTHCHECK` del contenedor Docker (ya configurado).

### Logging

Los logs salen como JSON por línea (sin dependencias externas). Cada entrada
incluye `timestamp`, `level`, `logger`, `message` y `request_id`. El nivel se
controla con la variable `LOG_LEVEL` (`DEBUG`, `INFO`, `WARNING`, ...).

El middleware `RequestIdMiddleware` propaga la cabecera `X-Request-ID` de
extremo a extremo: si el cliente la envía se respeta, si no se genera un UUID4
y se devuelve en la respuesta para correlación.

### Reimportar el catálogo en producción

`POST /import-parkings` exige cabecera `X-Import-Token` cuando la variable de
entorno `IMPORT_TOKEN` está configurada (la comparación es constant-time):

```bash
curl -X POST https://api.aparcaceres.app/import-parkings \
  -H "X-Import-Token: $IMPORT_TOKEN"
```

La invalidación de caché es `O(1)`: incrementa `cache:version` y las claves
antiguas quedan inalcanzables (caducan por TTL).

## Frontend Flutter

El cliente móvil vive en [`mobile/`](mobile/) y consume el backend FastAPI
por HTTP. El flujo pensado para producción es el del `docker compose up`
de la raíz del repo, que levanta también el frontend web servido por nginx.

### Arranque rápido

```bash
cd mobile
flutter pub get
flutter run
```

Por defecto la app apunta al backend dockerizado en `localhost:8000`:

| Plataforma | URL base por defecto |
|---|---|
| Android (emulador) | `http://10.0.2.2:8000` |
| iOS / macOS / Linux / Windows / Web | `http://localhost:8000` |

(El emulador Android resuelve `10.0.2.2` como el host; `localhost` apuntaría
al propio AVD.)

### Variables de compilación

Se inyectan con `--dart-define` y se resuelven en
[`mobile/lib/core/config/api_config.dart`](mobile/lib/core/config/api_config.dart).

| Flag | Tipo | Default | Para qué |
|---|---|---|---|
| `API_BASE_URL` | `String` | resolución por plataforma | Forzar otro backend (staging, IP de la LAN, túnel ngrok, etc.). Sin trailing slash. |

Ejemplo:

```bash
cd mobile
flutter run --dart-define=API_BASE_URL=http://192.168.1.10:8000
```

### Tests

```bash
cd mobile
flutter test          # suite completa
flutter analyze       # lints + type checks
```

La cobertura actual se reparte entre:
- tests de `core/` para cliente HTTP, sesión auth y error states
- tests de `data/` para el repositorio de aparcamientos y favoritos
- widget tests ligeros en `test/widget_test.dart` y `test/shared/widgets/`

### Arquitectura

```
lib/
├── core/                  # Infraestructura compartida
│   ├── auth/              # AuthSession (POST /auth/session)
│   ├── config/            # ApiConfig
│   ├── network/           # ApiClient, excepciones, parser de envelope
│   └── providers.dart     # sharedApiClient + authSession singletons
├── features/              # Pantallas y datos por feature
│   ├── parking/
│   │   ├── data/          # ApiParkingRepository, ServerFavoritesStore, …
│   │   └── domain/        # ParkingPlace, ParkingQuery, ParkingRepository
│   ├── map/, home/, search/, favorites/, parking_detail/, …
│   └── location/          # LocationService (Geolocator + bbox de Cáceres)
└── shared/                # Widgets/temas reutilizables
```

Puntos clave:

- `ApiClient` es un wrapper sobre `package:http` con timeouts, cancelación
  cooperativa (`CancelToken`), inyección opcional de `Authorization: Bearer`,
  y mapeo de errores a `ApiException` / `ApiUnavailableException` /
  `ApiTimeoutException`.
- `AuthSession` genera un `sub` aleatorio en el primer arranque, lo persiste
  en `SharedPreferences` y lo intercambia por un JWT con TTL de 30 días vía
  `POST /auth/session`. Refresca cuando faltan ≤ 1 día.
- `ServerFavoritesStore` mantiene la caché local en memoria (`contains`
  síncrono para el corazón) y aplica `add`/`remove` optimistas con rollback si
  el backend rechaza.
- `ApiErrorState` es la pantalla común de fallo (timeout / servicio caído /
  4xx / genérico) que reaparece en cada `FutureBuilder`.

### Smoke test manual

Antes de cortar release, levantar el backend y recorrer este checklist:

```bash
# desde la raíz del repo
docker compose up -d
curl -s http://localhost:8000/healthz | jq .   # esperar status: ok
```

Luego, en `mobile/`:

```bash
flutter run
```

| Caso | Acción | Resultado esperado |
|---|---|---|
| Mapa carga | Abrir tab Mapa | Marcadores visibles, sin spinner persistente |
| Filtros | Abrir drawer, marcar Plazas≥10 + categoría Zona Azul | Resultados se reducen sin colgar |
| Detalle | Tap en un marcador → "Ver detalle" | Pantalla con datos del backend, sin "Ubicación sin nombre" |
| Favorito persistente | Tap en corazón en detalle → matar app → reabrir | El corazón sigue lleno (vino de `/users/me/favorites`) |
| Pantalla favoritos | Abrir tab Favoritos | Lista cargada del servidor, ordenada por fecha de adición desc |
| Backend caído | `docker compose stop api` y refrescar lista | `ApiErrorState` con copy "Servicio no disponible" + botón Reintentar |
| Cancelación | Tocar varios filtros rápido | Solo la última request se ve reflejada (no hay flicker de resultados antiguos) |
| Fuera de Cáceres | En el emulador iOS: Features → Location → Custom (37.78, -122.41) | Banner "Estás fuera de Cáceres" con CTA Buscar; el picker filtra a Cáceres y permite continuar |

## Redis Stack en el proyecto

Redis Stack es la pieza central del backend.

Se utiliza para:
- almacenar el contrato canónico en hashes `parking:{id}`
- indexar búsqueda con `idx:parkings_search`
- resolver filtros por TAG (`category`, `vehicleType`, `regulation`, `sourceDataset`)
- resolver geoespacial con `location`
- resolver bounds del mapa con `latitude` y `longitude`
- cachear búsquedas cercanas repetidas con TTL

Ejemplo de claves:
- `parking:{id}`
- `idx:parkings_search`
- `cache:nearby:{...}`

Los ids son namespaced por dataset: `{sourceDataset}:{key}`. Si no hay `mslink` ni id municipal fiable, se usa un fallback estable `sha256[:20]` de geometría y propiedades clave. Los pocos `mslink` repetidos del dataset oficial se desambiguan con sufijo ordinal estable dentro del import, evitando sobrescrituras.

## API principal

- `GET /parkings` → envelope paginado con filtros
- `GET /parkings/nearby` → envelope paginado con distancia
- `GET /parkings/in-bounds` → envelope paginado para viewport de mapa
- `GET /parkings/facets` → conteos por categoría, vehículo, regulación y dataset
- `GET /parkings/categories` → categorías presentes
- `GET /parkings/{id}` → detalle de un aparcamiento
- `POST /import-parkings` → reimporta datasets activos y recrea RediSearch

Los listados devuelven:

```json
{
  "items": [],
  "total": 0,
  "limit": 100,
  "offset": 0,
  "truncated": false,
  "facets": null
}
```

`POST /import-parkings` exige `X-Import-Token` en el stack de Compose. El
contenedor `bootstrap` reutiliza la misma clave para ejecutar la primera
importación tras el arranque.

## Despliegue, TLS y backups

La guía operativa vive en [`docs/operations.md`](docs/operations.md):

- topología `nginx → uvicorn → redis-stack` con un sample de configuración
  nginx con TLS y propagación de `X-Request-ID`,
- variables de entorno mínimas en producción (`FAVORITES_SECRET`,
  `IMPORT_TOKEN`, `RATE_LIMIT_ENABLED`, `METRICS_ENABLED`...),
- backups de Redis y procedimiento de restore documentados en
  [`docs/operations.md`](docs/operations.md),
- procedimiento de restore desde un snapshot,
- runbook rápido con los síntomas más comunes y por dónde mirar primero.

## Autores

César Sánchez Montes, Miguel Ángel Campón Iglesias
