# Redis Stack en AparCáceres

> Redis Stack es la base de datos principal del proyecto y el motor que
> resuelve catálogo, búsqueda, geolocalización, favoritos y cachés.

## 🧭 Propósito

Redis Stack no se utiliza como una caché secundaria aislada. En este proyecto
actúa como motor central para:

• almacenar el catálogo canónico de aparcamientos;
• indexar búsqueda textual, filtros y geolocalización con RediSearch;
• resolver listados por proximidad y por encuadre de mapa;
• persistir favoritos por usuario;
• mantener cachés de consultas repetidas;
• soportar el flujo de importación sin ventanas largas de inconsistencia.

La elección encaja con el problema porque el catálogo es relativamente
estable, las lecturas son frecuentes y las consultas relevantes son geoespacial
e indexables. Redis permite responder con baja latencia sin introducir una
arquitectura de persistencia más pesada.

## 🧱 Modelo de datos

El backend guarda los aparcamientos como hashes Redis. Cada registro representa
un aparcamiento ya normalizado al contrato público del API.

### Claves principales

• `parking:{id}`: catálogo activo.
• `parking_v2:{id}`: generación temporal usada por el importador.
• `user:{sub}:favorites`: favoritos por usuario.
• `cache:nearby:{...}`: caché de consultas cercanas.
• `cache:version`: entero de invalidación global para caché de consultas.
• `parking_photo:{id}`: URL de foto resuelta o sentinel negativo.

La estructura evita mezclar datos operativos distintos en la misma clave y
permite borrar o invalidar conjuntos concretos sin recorrer toda la base.

## 📇 Índices y esquema

El índice de producción es `idx:parkings_search`.
Durante la importación se crea una generación temporal `idx:parkings_search_v2`
para construir el catálogo nuevo antes del swap.

Ambos índices se crean sobre hashes con este esquema:

• `id` como `TAG`
• `category` como `TAG`
• `vehicleType` como `TAG`
• `regulation` como `TAG`
• `sourceDataset` como `TAG`
• `location` como `GEO`
• `latitude` como `NUMERIC`
• `longitude` como `NUMERIC`
• `totalSpaces` como `NUMERIC`
• `searchText` como `TEXT NOSTEM`

### Por qué este esquema

• `TAG` se usa para valores discretos y filtrables, como categoría o tipo de
  vehículo.
• `GEO` se usa para consultas por radio sobre coordenadas.
• `NUMERIC` se usa para límites de plazas y filtrado por bounding box.
• `TEXT NOSTEM` se usa para el texto de búsqueda del nombre y metadatos
  normalizados, evitando lematización agresiva que no aporta valor en este
  dominio.

El índice no usa RedisJSON. El catálogo se almacena en hashes porque el modelo
es plano, fácil de reconstruir y suficiente para el contrato HTTP del proyecto.

## 🔎 Consultas de búsqueda

La capa de consultas vive en [`backend/app/infra/redis/search.py`](../backend/app/infra/redis/search.py).
Ese módulo exige RediSearch de forma explícita y no ofrece un fallback en
memoria en producción.

### Listado general

`GET /parkings` combina:

• filtros por `id`, `category`, `vehicleType`, `regulation` y `sourceDataset`
  mediante `TAG`;
• búsqueda textual sobre `searchText`;
• mínimo de plazas sobre `totalSpaces`;
• filtrado adicional por bbox si se solicita.

La consulta se ejecuta con `FT.SEARCH` sobre `idx:parkings_search`.

### Próximos

`GET /parkings/nearby` usa `FT.AGGREGATE` y calcula la distancia con
`geodistance(@location, lng, lat)`.

Esto permite:

• ordenar por distancia sin cargar todo el catálogo en el backend;
• limitar el conjunto ya ordenado en el propio motor;
• devolver el contrato completo de cada aparcamiento con un campo extra de
  `distanceMeters`.

### En bounds

`GET /parkings/in-bounds` filtra por latitud y longitud usando rangos
numéricos. Este caso responde bien al índice porque el mapa suele consultar
ventanas acotadas y el motor puede resolverlo directamente sobre los campos
indexados.

### Facetas

`GET /parkings/facets` usa `FT.AGGREGATE` para contar valores por:

• `category`
• `vehicleType`
• `regulation`
• `sourceDataset`

Estas facetas alimentan filtros de interfaz sin duplicar lógica en Flutter.

## 🧮 Caché

### Nearby

Las consultas cercanas se cachean con claves `cache:nearby:v{version}:...`.
La clave incorpora la versión global para que la invalidación sea barata.

En vez de borrar claves antiguas una a una, el importador incrementa
`cache:version` al completar una reimportación correcta. Desde ese momento las
consultas nuevas construyen claves distintas y las anteriores quedan
inaccesibles hasta su expiración natural.

Ventajas:

• invalidación `O(1)`;
• sin `SCAN`;
• sin barridos globales;
• comportamiento predecible tras un import.

### Fotos

Las fotos resueltas se almacenan en `parking_photo:{id}`.
El valor puede ser:

• una URL válida resuelta desde la ficha municipal;
• un sentinel vacío para indicar que ya se comprobó y no existe foto útil.

Ese sentinel evita repetir scraping sobre fichas que ya se sabe que no
contienen una imagen aprovechable.

## 🔁 Importación y swap

La importación se implementa en [`backend/app/infra/redis/importer.py`](../backend/app/infra/redis/importer.py).

El flujo es:

• leer los GeoJSON activos;
• normalizar cada feature al contrato público;
• escribir la nueva generación en `parking_v2:{id}`;
• crear el índice temporal `idx:parkings_search_v2`;
• borrar la generación activa anterior;
• renombrar o mover la generación temporal a `parking:{id}`;
• recrear el índice definitivo `idx:parkings_search`;
• incrementar `cache:version`.

Este enfoque reduce la ventana en la que el catálogo podría quedar
parcialmente actualizado. No elimina todos los riesgos operativos, pero sí
evita el patrón de “borrar y volver a cargar” sin control.

## ⭐ Favoritos

Los favoritos se guardan como sorted sets:

• clave por usuario: `user:{sub}:favorites`
• score: instante UTC en milisegundos

Razones de diseño:

• `ZREVRANGE` permite listar favoritos más recientes primero;
• el score conserva la secuencia de alta;
• la operación sigue siendo simple de consultar y de depurar;
• no hace falta una tabla adicional ni un índice secundario.

El backend valida que el aparcamiento exista antes de escribir en el sorted
set. Eso evita persistir ids que no pertenecen al catálogo activo.

## 🎛️ Características aprovechadas

### Hashes

Se usan como formato principal de persistencia del catálogo porque:

• el contrato es plano;
• la reconstrucción del objeto es directa;
• el coste operativo es bajo;
• el modelo encaja bien con importación por lotes.

### RediSearch

Se aprovecha para:

• búsqueda textual;
• filtros por tag;
• geosearch;
• agregaciones de facetas;
• ordenación por distancia.

### Sorted sets

Se aprovechan para favoritos por usuario con orden temporal estable.

### Claves con versión

Se aprovechan para invalidación rápida de caché sin operaciones globales
costosas.

### Expiración y caché negativa

Se aprovechan para fotos resueltas y consultas frecuentes, reduciendo trabajo
repetido en importaciones y en lecturas.

## 🧾 Consideraciones operativas

• Redis Stack debe estar disponible en producción, porque la búsqueda depende
  de RediSearch.
• La capa de consulta no ofrece fallback en memoria en producción; si el
  índice falta o el módulo no está presente, el backend falla de forma
  explícita.
• El importador puede continuar aunque falle la resolución de fotos, ya que
  esa parte no debe bloquear toda la carga del catálogo.
• El volumen de Redis debe persistirse y respaldarse fuera del contenedor si
  el despliegue va a ser duradero.

## 📚 Documentación relacionada

• [`README.md`](../README.md): entrada general del proyecto.
• [`docs/architecture.md`](architecture.md): visión global del sistema.
• [`docs/operations.md`](operations.md): despliegue y operación.
• [`backend/app/core/config.py`](../backend/app/core/config.py): claves,
  límites y variables de entorno que afectan a Redis.
• [`backend/app/infra/redis/search.py`](../backend/app/infra/redis/search.py):
  consultas y creación de índices.
• [`backend/app/infra/redis/importer.py`](../backend/app/infra/redis/importer.py):
  importación, swap e invalidación.
• [`backend/app/routers/favorites.py`](../backend/app/routers/favorites.py):
  persistencia de favoritos por usuario.
