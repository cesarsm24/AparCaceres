<div align="center">

<img src="mobile/assets/images/logo_transparente.png" alt="Logo de AparCáceres" width="250" />

<p>
Aplicación móvil para la consulta de aparcamientos en Cáceres con Flutter, FastAPI y Redis Stack.
</p>

<p>
  <img alt="backend-ci" src="https://img.shields.io/badge/backend--ci-ruff%20%2B%20pytest-2EA44F?logo=githubactions&logoColor=white" />
  <img alt="flutter-ci" src="https://img.shields.io/badge/flutter--ci-analyze%20%2B%20test-02569B?logo=githubactions&logoColor=white" />
  <img alt="Python 3.11" src="https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white" />
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-backend-009688?logo=fastapi&logoColor=white" />
  <img alt="Flutter" src="https://img.shields.io/badge/Flutter-frontend-02569B?logo=flutter&logoColor=white" />
  <img alt="Redis Stack" src="https://img.shields.io/badge/Redis%20Stack-data%20engine-DC382D?logo=redis&logoColor=white" />
  <img alt="Docker Compose" src="https://img.shields.io/badge/Docker%20Compose-deploy-2496ED?logo=docker&logoColor=white" />
</p>

</div>


<div style="margin-top: 2.5rem"></div>

---

## 🧭 Visión general

AparCáceres permite consultar aparcamientos públicos de Cáceres por mapa, cercanía, filtros, categoría y favoritos. El sistema está preparado para ejecutarse de forma reproducible con `docker compose` y mantiene una separación clara entre experiencia de usuario, contrato HTTP y persistencia.

| Capa | Tecnología | Responsabilidad |
|---|---|---|
| Backend | FastAPI | API, autenticación de favoritos, importación y contrato OpenAPI |
| Frontend | Flutter | UI móvil/web, mapa, búsqueda, favoritos y rutas |
| Datos | Redis Stack | Catálogo, RediSearch, geoespacial, caché y favoritos |
| Despliegue | Docker Compose | Stack reproducible con API, Redis, bootstrap y web |

<div style="margin-top: 2.5rem"></div>

---

## 🚀 Arranque con Docker Compose

El flujo principal del proyecto es levantar todo el stack desde la raíz:

```bash
cp backend/.env.example backend/.env
openssl rand -hex 32
openssl rand -hex 32
```

Después de generar los secretos, completar en `backend/.env`:

```env
CORS_ORIGINS=http://localhost:5000
IMPORT_TOKEN=<token-generado>
FAVORITES_SECRET=<secreto-generado>
```

Levantar el entorno:

```bash
docker compose up -d --build
docker compose logs -f bootstrap
docker compose exec api curl -s http://localhost:8000/healthz
```

Servicios expuestos en local:

| Servicio | URL |
|---|---|
| Frontend web | `http://localhost:5000` |
| Backend API | `http://localhost:8000` |
| OpenAPI | `http://localhost:8000/docs` |
| Healthcheck | `http://localhost:8000/healthz` |

<div style="margin-top: 2.5rem"></div>

---

## 📱 Arranque del cliente Flutter

El frontend móvil se ejecuta fuera de Docker, contra el backend que ya esté arriba en `localhost:8000`. El flujo es idéntico para emulador Android y para dispositivo real conectado por USB.

**Requisitos previos:** Flutter SDK, Android SDK con `adb` en el `PATH` y, para dispositivo físico, depuración USB activada.

1. Levantar el backend (sección anterior) y comprobar que `http://localhost:8000/healthz` responde.
2. Conectar el dispositivo o arrancar el emulador y verificar que aparece:

   ```bash
   adb devices
   ```

3. Redirigir el puerto del dispositivo al backend del host. Funciona tanto en emulador como en dispositivo real:

   ```bash
   adb reverse tcp:8000 tcp:8000
   ```

   `adb reverse` debe repetirse al reconectar el cable o reiniciar `adb`.

4. Ejecutar la app:

   ```bash
   cd mobile
   flutter pub get
   flutter run
   ```

   Si hay varios dispositivos disponibles, seleccionar con `flutter run -d <id>` (lista con `flutter devices`).

> **Sin `adb reverse` en emulador.** Como alternativa, puede arrancarse con `flutter run --dart-define=ANDROID_EMULATOR=true` para que la app use `10.0.2.2` (la puerta de enlace al host del emulador) en lugar de `localhost`.

Para iOS, web y escritorio no se requiere redirección: `flutter run` se conecta directamente a `localhost:8000`.

<div style="margin-top: 2.5rem"></div>

---

## 🗂️ Fuente de datos

El catálogo parte de datos abiertos municipales publicados por el Ayuntamiento de Cáceres en el portal [Open Data Cáceres](https://opendata.caceres.es/datosabiertos/catalogo/es/dataset/).

El importador procesa datasets GeoJSON relacionados con aparcamientos, movilidad reducida, zona azul, carga y descarga, bicicletas y motos. La normalización concreta de esos datasets se documenta en [`docs/redis.md`](docs/redis.md) y en la capa de importación del backend.

<div style="margin-top: 2.5rem"></div>

---

## 🧱 Estructura

```text
AparCaceres/
├── backend/              # FastAPI + Redis Stack
│   ├── app/core/         # Configuración, auth, logging, métricas y rate limit
│   ├── app/infra/redis/  # Cliente Redis, RediSearch, importador y fotos
│   ├── app/routers/      # Endpoints HTTP por dominio
│   └── tests/            # Suite pytest
├── mobile/               # Frontend Flutter
│   ├── lib/core/         # Configuración, red y sesión
│   ├── lib/features/     # Funcionalidades de aplicación
│   └── test/             # Suite Flutter
├── docs/                 # Arquitectura, operación y Redis
└── docker-compose.yml    # Stack reproducible
```

<div style="margin-top: 2.5rem"></div>

---

## 🧪 Calidad

El repositorio incluye CI separada para backend y frontend:

| Workflow | Validaciones |
|---|---|
| `backend-ci` | `ruff check`, Redis Stack real y `pytest -q` |
| `flutter-ci` | `flutter analyze` y `flutter test` |

Workflows:

| Workflow | Archivo |
|---|---|
| `backend-ci` | [`.github/workflows/backend-ci.yml`](.github/workflows/backend-ci.yml) |
| `flutter-ci` | [`.github/workflows/flutter-ci.yml`](.github/workflows/flutter-ci.yml) |

Comandos locales:

```bash
cd backend
ruff check app tests main.py
pytest -q
```

```bash
cd mobile
flutter analyze
flutter test
```

<div style="margin-top: 2.5rem"></div>

---

## 🗺️ Integración frontend-backend

El frontend consume el backend por HTTP y no accede directamente a Redis. Los flujos principales están alineados con los endpoints de producción:

| Flujo | Endpoint principal |
|---|---|
| Catálogo general | `GET /parkings` |
| Mapa por movimiento manual | `GET /parkings/in-bounds` |
| Centrar ubicación o dirección buscada | `GET /parkings/nearby` |
| Categorías disponibles | `GET /parkings/categories` |
| Detalle | `GET /parkings/{id}` |
| Favoritos | `GET/PUT/DELETE /users/me/favorites` |
| Importación inicial | `POST /import-parkings` |

<div style="margin-top: 2.5rem"></div>

---

## 🧠 Redis Stack

Redis Stack actúa como almacenamiento canónico y motor de consulta. El backend aprovecha hashes, sorted sets, RediSearch, campos geoespaciales, rangos numéricos, caché con versión y expiración de claves.

Resumen de piezas:

| Pieza | Uso |
|---|---|
| `parking:{id}` | Catálogo activo normalizado |
| `idx:parkings_search` | Índice RediSearch de producción |
| `parking_v2:{id}` | Generación temporal durante importación |
| `user:{sub}:favorites` | Favoritos ordenados por fecha |
| `cache:nearby:v{version}:...` | Caché versionada de consultas cercanas |
| `parking_photo:{id}` | Foto resuelta o caché negativa |

El detalle técnico está en [`docs/redis.md`](docs/redis.md).

<div style="margin-top: 2.5rem"></div>

---

## 📚 Documentación

| Documento | Contenido |
|---|---|
| [`docs/architecture.md`](docs/architecture.md) | Arquitectura, capas, flujos y decisiones de diseño |
| [`docs/operations.md`](docs/operations.md) | Despliegue, variables, TLS, persistencia y runbook |
| [`docs/redis.md`](docs/redis.md) | Modelo de datos, índices, búsquedas, caché e importación |

<div style="margin-top: 2.5rem"></div>

---

## ⚖️ Licencia

Este proyecto se distribuye bajo [`PolyForm Noncommercial 1.0.0`](LICENSE). El uso comercial no está permitido sin autorización expresa de los autores.

<div style="margin-top: 2.5rem"></div>

---

## 👥 Autores

| Autor | GitHub |
|---|---|
| César Sánchez Montes | [@cesarsm24](https://github.com/cesarsm24) |
| Miguel Ángel Campón Iglesias | [@Miguelit011](https://github.com/Miguelit011) |
