<div align="center">

<img width="1254" height="1254" alt="Logotipo AparCáceres" src="https://github.com/user-attachments/assets/7c7066e0-978d-4adb-9049-593985eb5e37" />

# AparCáceres

Localizador de aparcamientos públicos de Cáceres por proximidad.

</div>

## Descripción

AparCáceres es una aplicación web que permite buscar los aparcamientos públicos más cercanos a una ubicación dentro de la ciudad de Cáceres.

El proyecto utiliza datos abiertos municipales y pone el foco en el uso de **RedisDB** como base de datos principal para realizar consultas geoespaciales rápidas y eficientes.

## Objetivo

Permitir al usuario:
- buscar aparcamientos cercanos por latitud, longitud y radio
- ver los resultados ordenados por distancia
- visualizar los aparcamientos en un mapa
- consultar información básica de cada aparcamiento

## Fuente de datos

- Open Data Cáceres  
  https://opendata.caceres.es/datosabiertos/catalogo/dataset/aparcamientos-y-parking

## Tecnologías previstas

- **RedisDB** para almacenamiento geoespacial
- Backend con Node.js / Express o FastAPI
- Frontend web
- Leaflet para el mapa
- Datos en GeoJSON o CSV

## RedisDB en el proyecto

RedisDB es la pieza central del sistema.

Se utilizará para:
- almacenar coordenadas de aparcamientos
- realizar búsquedas por proximidad
- guardar metadatos básicos
- cachear búsquedas repetidas con TTL

Ejemplo de claves:
- `geo:parkings`
- `parking:{id}`
- `cache:nearby:{...}`

## API mínima

- `GET /parkings/nearby` → devuelve aparcamientos cercanos
- `GET /parkings/{id}` → devuelve el detalle de un aparcamiento
- `POST /import-parkings` → carga el dataset en RedisDB

## Estado

Proyecto en fase inicial.

## Autores

- César Sánchez Montes
- Miguel Ángel Campón Iglesias
