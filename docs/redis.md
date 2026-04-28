# Redis Stack en AparCáceres

<div style="margin-top: 2.5rem"></div>

> Redis Stack es la base de datos principal del proyecto y el motor que resuelve catálogo, búsqueda, geolocalización, favoritos y cachés.

<div style="margin-top: 2.5rem"></div>

---

## 🧭 Propósito

Redis Stack no se utiliza como caché secundaria aislada. En este proyecto actúa como motor central para:

- almacenar el catálogo canónico de aparcamientos;
- indexar búsqueda textual, filtros y geolocalización con RediSearch;
- resolver listados por proximidad y por encuadre de mapa;
- persistir favoritos por usuario;
- mantener cachés de consultas repetidas;
- soportar el flujo de importación sin ventanas largas de inconsistencia.

La elección encaja con el problema porque el catálogo es relativamente estable, las lecturas son frecuentes y las consultas relevantes son geoespaciales e indexables. Redis permite responder con baja latencia sin introducir una arquitectura de persistencia más pesada.

<div style="margin-top: 2.5rem"></div>

---

## 🧱 Modelo de datos

Los aparcamientos se almacenan como hashes Redis. Cada registro representa un aparcamiento ya normalizado al contrato público de la API.

### Claves principales

| Clave | Descripción |
|---|---|
| `parking:{id}` | Catálogo activo |
| `parking_v2:{id}` | Generación temporal usada por el importador |
| `user:{sub}:favorites` | Favoritos por usuario |
| `cache:nearby:{...}` | Caché de consultas cercanas |
| `cache:version` | Entero de invalidación global para caché de consultas |
| `parking_photo:{id}` | URL de foto resuelta o sentinel negativo |

La estructura evita mezclar datos operativos distintos en la misma clave y permite borrar o invalidar conjuntos concretos sin recorrer toda la base.

<div style="margin-top: 2.5rem"></div>

---

## 📇 Índices y esquema

El índice de producción es `idx:parkings_search`. Durante la importación se crea una generación temporal `idx:parkings_search_v2` para construir el catálogo nuevo antes del swap.

Ambos índices se crean sobre hashes con este esquema:

| Campo | Tipo | Motivo |
|---|---|---|
| `id` | `TAG` | Identificador filtrable |
| `category` | `TAG` | Valor discreto |
| `vehicleType` | `TAG` | Valor discreto |
| `regulation` | `TAG` | Valor discreto |
| `sourceDataset` | `TAG` | Valor discreto |
| `location` | `GEO` | Consultas por radio sobre coordenadas |
| `latitude` | `NUMERIC` | Filtrado por bounding box |
| `longitude` | `NUMERIC` | Filtrado por bounding box |
| `totalSpaces` | `NUMERIC` | Límite de plazas |
| `searchText` | `TEXT NOSTEM` | Búsqueda textual sin lematización |

`TEXT NOSTEM` evita una lematización agresiva que no aporta valor en este dominio.

El índice no usa RedisJSON. El catálogo se almacena en hashes porque el modelo es plano, fácil de reconstruir y suficiente para el contrato HTTP del proyecto.

<div style="margin-top: 2.5rem"></div>

---

## 🔎 Consultas de búsqueda

La capa de consultas vive en [`backend/app/infra/redis/search.py`](../backend/app/infra/redis/search.py). Ese módulo exige RediSearch de forma explícita y no ofrece fallback en memoria en producción.

### Listado general

`GET /parkings` combina filtros por `TAG` sobre `id`, `category`, `vehicleType`, `regulation` y `sourceDataset`, búsqueda textual sobre `searchText`, mínimo de plazas sobre `totalSpaces` y filtrado adicional por bbox si se solicita. La consulta se ejecuta con `FT.SEARCH` sobre `idx:parkings_search`.

### Próximos

`GET /parkings/nearby` usa `FT.AGGREGATE` y calcula la distancia con `geodistance(@location, lng, lat)`. Esto permite ordenar por distancia sin cargar todo el catálogo en el backend, limitar el conjunto ya ordenado en el propio motor y devolver el contrato completo de cada aparcamiento con un campo extra `distanceMeters`.

### En bounds

`GET /parkings/in-bounds` filtra por latitud y longitud usando rangos numéricos. El mapa suele consultar ventanas acotadas y el motor puede resolverlo directamente sobre los campos indexados.

### Facetas

`GET /parkings/facets` usa `FT.AGGREGATE` para contar valores por `category`, `vehicleType`, `regulation` y `sourceDataset`. Estas facetas alimentan los filtros de la interfaz sin duplicar lógica en Flutter.

<div style="margin-top: 2.5rem"></div>

---

## 🧮 Caché

### Nearby

Las consultas cercanas se cachean con claves `cache:nearby:v{version}:...`. La clave incorpora la versión global para que la invalidación sea barata: en lugar de borrar claves antiguas una a una, el importador incrementa `cache:version` al completar una reimportación correcta. Desde ese momento las consultas nuevas construyen claves distintas y las anteriores quedan inaccesibles hasta su expiración natural.

| Ventaja | Detalle |
|---|---|
| Invalidación `O(1)` | Sin `SCAN` ni barridos globales |
| Comportamiento predecible | La versión cambia solo tras un import correcto |

### Fotos

Las fotos resueltas se almacenan en `parking_photo:{id}`. El valor puede ser una URL válida resuelta desde la ficha municipal o un sentinel vacío que indica que ya se comprobó y no existe foto útil. Ese sentinel evita repetir scraping sobre fichas que no contienen una imagen aprovechable.

<div style="margin-top: 2.5rem"></div>

---

## 🔁 Importación y swap

La importación se implementa en [`backend/app/infra/redis/importer.py`](../backend/app/infra/redis/importer.py).

```
leer GeoJSON activos
  → normalizar cada feature al contrato público
  → escribir nueva generación en parking_v2:{id}
  → crear índice temporal idx:parkings_search_v2
  → borrar generación activa anterior
  → renombrar generación temporal a parking:{id}
  → recrear índice definitivo idx:parkings_search
  → incrementar cache:version
```

Este enfoque reduce la ventana en la que el catálogo podría quedar parcialmente actualizado. No elimina todos los riesgos operativos, pero evita el patrón de borrar y volver a cargar sin control.

<div style="margin-top: 2.5rem"></div>

---

## ⭐ Favoritos

Los favoritos se guardan como sorted sets con la clave `user:{sub}:favorites` y el instante UTC en milisegundos como score.

| Decisión | Motivo |
|---|---|
| Sorted set | `ZREVRANGE` lista favoritos más recientes primero |
| Score temporal | Conserva la secuencia de alta |
| Sin índice secundario | El modelo es suficientemente simple |

El backend valida que el aparcamiento exista antes de escribir en el sorted set, evitando persistir ids que no pertenecen al catálogo activo.

<div style="margin-top: 2.5rem"></div>

---

## 🎛️ Características aprovechadas

| Característica | Uso en el proyecto |
|---|---|
| Hashes | Persistencia del catálogo — modelo plano, bajo coste operativo |
| RediSearch | Búsqueda textual, filtros por tag, geosearch, facetas y ordenación por distancia |
| Sorted sets | Favoritos por usuario con orden temporal estable |
| Claves con versión | Invalidación rápida de caché sin operaciones globales costosas |
| Expiración y caché negativa | Fotos resueltas y consultas frecuentes |

<div style="margin-top: 2.5rem"></div>

---

## 🧾 Consideraciones operativas

- Redis Stack debe estar disponible en producción, ya que la búsqueda depende de RediSearch.
- La capa de consulta no ofrece fallback en memoria en producción; si el índice falta o el módulo no está presente, el backend falla de forma explícita.
- El importador puede continuar aunque falle la resolución de fotos, dado que esa parte no debe bloquear la carga del catálogo.
- El volumen de Redis debe persistirse y respaldarse fuera del contenedor si el despliegue va a ser duradero.

<div style="margin-top: 2.5rem"></div>

---

## 📚 Documentación relacionada

- [`README.md`](../README.md) — Entrada general del proyecto
- [`docs/architecture.md`](architecture.md) — Visión global del sistema
- [`docs/operations.md`](operations.md) — Despliegue y operación
- [`backend/app/core/config.py`](../backend/app/core/config.py) — Claves, límites y variables de entorno que afectan a Redis
- [`backend/app/infra/redis/search.py`](../backend/app/infra/redis/search.py) — Consultas y creación de índices
- [`backend/app/infra/redis/importer.py`](../backend/app/infra/redis/importer.py) — Importación, swap e invalidación
- [`backend/app/routers/favorites.py`](../backend/app/routers/favorites.py) — Persistencia de favoritos por usuario