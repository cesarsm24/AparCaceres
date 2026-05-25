import 'package:latlong2/latlong.dart';

/// Ruta calculada entre dos puntos.
///
/// Contiene la polilínea lista para pintar en el mapa y los metadatos básicos
/// devueltos por el servicio de routing.
class RoutePath {
  const RoutePath({
    required this.coordinates,
    required this.distanceMeters,
    required this.durationSeconds,
  });

  final List<LatLng> coordinates;
  final double distanceMeters;
  final double durationSeconds;
}