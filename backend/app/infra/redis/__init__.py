"""Integración con Redis Stack.

Agrupa el cliente compartido de Redis, la capa de búsqueda con RediSearch,
el importador del catálogo y la resolución de fotos vinculadas a las fichas
municipales. Esta es la frontera de infraestructura del backend: los routers
delegan aquí la persistencia, la consulta y la ingestión del catálogo.
"""
