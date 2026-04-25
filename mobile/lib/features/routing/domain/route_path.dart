import 'package:latlong2/latlong.dart';

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
