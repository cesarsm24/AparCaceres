<div align="center">

<img src="https://URL-DEL-LOGO-AQUI" alt="Logo de AparCáceres" width="180" />

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

Total activo esperado: `7314` features. `parkings_en_superficie.geojson` se ignora siempre porque es masivo, genérico y no trae propiedades útiles para usuarios reales.

## Tecnologías

- **Redis Stack / RediSearch** para almacenamiento, geoespacial, filtros y búsqueda
- Backend en **FastAPI** (Python)
- Cliente móvil en **Flutter** (Material 3)
- Datos en GeoJSON o CSV

## Backend

Requisitos:
- Python `>=3.11`
- Redis Stack con RediSearch habilitado

Comandos habituales:

```bash
cd backend
python3.11 -m venv .venv311
. .venv311/bin/activate
pip install -r requirements-dev.txt
pytest
uvicorn main:app --reload
```

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

`POST /import-parkings` acepta `X-Import-Token` si `IMPORT_TOKEN` está configurado. En desarrollo queda abierto si la variable está vacía.

## Autores

César Sánchez Montes, Miguel Ángel Campón Iglesias
