import 'package:latlong2/latlong.dart';

/// Sugerencia de ubicación seleccionable por el usuario.
///
/// Representa un resultado normalizado del servicio de geocodificación con
/// identificador externo, nombre completo, etiqueta corta y coordenadas.
class PlaceSuggestion {
  const PlaceSuggestion({
    required this.id,
    required this.displayName,
    required this.shortName,
    required this.position,
  });

  final String id;
  final String displayName;
  final String shortName;
  final LatLng position;
}