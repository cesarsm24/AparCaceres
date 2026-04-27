# AparCáceres — cliente Flutter

Cliente móvil de [AparCáceres](../README.md). Habla con el backend FastAPI documentado en [`../backend/`](../backend/) y consume RediSearch a través de él.

## Arranque rápido

```bash
flutter pub get
flutter run
```

Por defecto la app apunta al backend dockerizado en `localhost:8000`:

| Plataforma | URL base por defecto |
|---|---|
| Android (emulador) | `http://10.0.2.2:8000` |
| iOS / macOS / Linux / Windows / Web | `http://localhost:8000` |

(El emulador Android resuelve `10.0.2.2` como el host; `localhost` apuntaría al propio AVD.)

## Variables de compilación

Se inyectan con `--dart-define`. Definidas en [`lib/core/config/api_config.dart`](lib/core/config/api_config.dart) y [`lib/features/parking/data/parking_repository_provider.dart`](lib/features/parking/data/parking_repository_provider.dart).

| Flag | Tipo | Default | Para qué |
|---|---|---|---|
| `API_BASE_URL` | `String` | resolución por plataforma | Forzar otro backend (staging, IP de la LAN, túnel ngrok, etc.). Sin trailing slash. |
| `USE_LOCAL_DATA` | `bool` | `false` | Modo demo: usa el fixture mock (`assets/mock/parking_places.json`) y un `FavoritesStore` en memoria; no toca la red. Útil para presentar la app sin levantar el backend. |

Ejemplos:

```bash
# dispositivo físico apuntando a un backend en la LAN
flutter run --dart-define=API_BASE_URL=http://192.168.1.10:8000

# modo demo offline
flutter run --dart-define=USE_LOCAL_DATA=true
```

## Tests

```bash
flutter test          # suite completa
flutter analyze       # lints + type checks
```

La cobertura actual es de unit tests sobre la capa `core/` (cliente HTTP, sesión auth, error states) y `data/` (repositorio, favoritos servidor). Los widget tests son ligeros — ver [`test/widget_test.dart`](test/widget_test.dart) y los tests bajo [`test/shared/widgets/`](test/shared/widgets/).

## Arquitectura

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

- `ApiClient` es un wrapper sobre `package:http` con timeouts, cancelación cooperativa (`CancelToken`), inyección opcional de `Authorization: Bearer`, y mapeo de errores a `ApiException` / `ApiUnavailableException` / `ApiTimeoutException`. Ver [`lib/core/network/api_client.dart`](lib/core/network/api_client.dart).
- `AuthSession` genera un `sub` aleatorio en el primer arranque, lo persiste en `SharedPreferences` y lo intercambia por un JWT con TTL de 30 días vía `POST /auth/session`. Refresca cuando faltan ≤ 1 día. Ver [`lib/core/auth/auth_session.dart`](lib/core/auth/auth_session.dart).
- `ServerFavoritesStore` mantiene la cache local en memoria (`contains` síncrono para el corazón) y aplica `add`/`remove` optimistas con rollback si el backend rechaza. Ver [`lib/features/parking/data/server_favorites_store.dart`](lib/features/parking/data/server_favorites_store.dart).
- `ApiErrorState` es la pantalla común de fallo (timeout / servicio caído / 4xx / genérico) que reaparece en cada `FutureBuilder`. Ver [`lib/shared/widgets/api_error_state.dart`](lib/shared/widgets/api_error_state.dart).

## Smoke test manual

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
| Backend caído | `docker compose stop backend` y refrescar lista | `ApiErrorState` con copy "Servicio no disponible" + botón Reintentar |
| Cancelación | Tocar varios filtros rápido | Solo la última request se ve reflejada (no hay flicker de resultados antiguos) |
| Fuera de Cáceres | En el emulador iOS: Features → Location → Custom (37.78, -122.41) | Banner "Estás fuera de Cáceres" con CTA Buscar; el picker filtra a Cáceres y permite continuar |
| Modo demo | `flutter run --dart-define=USE_LOCAL_DATA=true` | App funciona sin backend, usa fixtures locales |

## Modo demo

`USE_LOCAL_DATA=true` desconecta el cliente del backend completo:

- `parkingRepository` → `LocalParkingRepository` (lee `assets/mock/parking_places.json`).
- `favoritesStore` → `LocalFavoritesStore` con ids semilla en memoria.
- `AuthSession` y `ApiClient` siguen instanciados pero no se usan.

Pensado para demos sin docker. No se mantiene en producción.
