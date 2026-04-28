import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:latlong2/latlong.dart';

import '../domain/route_path.dart';

/// Cliente HTTP para cálculo de rutas con OSRM.
///
/// Solicita una ruta entre origen y destino y normaliza la geometría GeoJSON
/// `[lon, lat]` a `LatLng` para que pueda pintarse directamente en el mapa.
class OsrmClient {
  OsrmClient({http.Client? client, String? userAgent})
      : _client = client ?? http.Client(),
        _userAgent = userAgent ?? _defaultUserAgent;

  static const String _defaultUserAgent = 'AparCaceres/1.0 (mobile app)';
  static const String _host = 'router.project-osrm.org';

  final http.Client _client;
  final String _userAgent;

  Future<RoutePath> route(
      String profile,
      LatLng origin,
      LatLng destination,
      ) async {
    final coords =
        '${origin.longitude},${origin.latitude};'
        '${destination.longitude},${destination.latitude}';
    final uri = Uri.https(_host, '/route/v1/$profile/$coords', {
      'overview': 'full',
      'geometries': 'geojson',
      'alternatives': 'false',
      'steps': 'false',
    });

    final response = await _client.get(
      uri,
      headers: {'User-Agent': _userAgent, 'Accept': 'application/json'},
    );

    if (response.statusCode != 200) {
      throw OsrmException('OSRM HTTP ${response.statusCode}');
    }

    final body = jsonDecode(response.body) as Map<String, dynamic>;
    final code = body['code'] as String?;

    if (code != 'Ok') {
      throw OsrmException('OSRM code=$code');
    }

    final routes = body['routes'] as List?;

    if (routes == null || routes.isEmpty) {
      throw OsrmException('OSRM returned no routes');
    }

    final route = routes.first as Map<String, dynamic>;
    final geometry = route['geometry'] as Map<String, dynamic>;
    final coordinatesJson = geometry['coordinates'] as List;
    final coordinates = coordinatesJson.map((point) {
      final pair = point as List;

      return LatLng(
        (pair[1] as num).toDouble(),
        (pair[0] as num).toDouble(),
      );
    }).toList(growable: false);

    return RoutePath(
      coordinates: coordinates,
      distanceMeters: (route['distance'] as num?)?.toDouble() ?? 0,
      durationSeconds: (route['duration'] as num?)?.toDouble() ?? 0,
    );
  }

  void close() => _client.close();
}

/// Error producido al consultar o interpretar una respuesta de OSRM.
class OsrmException implements Exception {
  OsrmException(this.message);

  final String message;

  @override
  String toString() => 'OsrmException: $message';
}