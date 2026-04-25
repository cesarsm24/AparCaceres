import 'package:latlong2/latlong.dart';

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
