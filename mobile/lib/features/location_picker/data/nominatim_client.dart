import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:latlong2/latlong.dart';

import '../domain/place_suggestion.dart';

/// Cliente de búsqueda de direcciones mediante Nominatim.
///
/// Restringe las consultas a España y al área aproximada de Cáceres para que
/// el selector de ubicación solo proponga resultados útiles para el catálogo.
class NominatimClient {
  NominatimClient({http.Client? client, this.userAgent = _defaultUserAgent})
      : _client = client ?? http.Client();

  static const String _defaultUserAgent = 'AparCaceres/1.0 (mobile app)';
  static const String _host = 'nominatim.openstreetmap.org';
  static const String _viewbox = '-6.45,39.52,-6.30,39.42';

  final http.Client _client;
  final String userAgent;

  /// Busca lugares dentro del área configurada y devuelve sugerencias normalizadas.
  Future<List<PlaceSuggestion>> search(String query, {int limit = 8}) async {
    final trimmed = query.trim();
    if (trimmed.isEmpty) return const <PlaceSuggestion>[];

    final uri = Uri.https(_host, '/search', {
      'q': trimmed,
      'format': 'jsonv2',
      'addressdetails': '1',
      'limit': '$limit',
      'countrycodes': 'es',
      'viewbox': _viewbox,
      'bounded': '1',
      'accept-language': 'es',
    });

    final response = await _client.get(
      uri,
      headers: {'User-Agent': userAgent, 'Accept': 'application/json'},
    );

    if (response.statusCode != 200) {
      throw NominatimException(
        'Nominatim returned ${response.statusCode}',
        response.statusCode,
      );
    }

    final decoded = jsonDecode(response.body) as List<dynamic>;

    return decoded
        .map((item) => _parse(item as Map<String, dynamic>))
        .where((suggestion) => suggestion != null)
        .cast<PlaceSuggestion>()
        .toList();
  }

  PlaceSuggestion? _parse(Map<String, dynamic> json) {
    final lat = double.tryParse('${json['lat']}');
    final lon = double.tryParse('${json['lon']}');

    if (lat == null || lon == null) return null;

    final displayName = (json['display_name'] as String?) ?? '';
    final address = json['address'] as Map<String, dynamic>?;
    final shortName = _shortName(json, address) ?? displayName;

    return PlaceSuggestion(
      id: '${json['osm_type']}-${json['osm_id']}',
      displayName: displayName,
      shortName: shortName,
      position: LatLng(lat, lon),
    );
  }

  String? _shortName(Map<String, dynamic> json, Map<String, dynamic>? address) {
    final name = json['name'] as String?;
    if (name != null && name.trim().isNotEmpty) return name;
    if (address == null) return null;

    for (final key in const [
      'road',
      'pedestrian',
      'square',
      'neighbourhood',
      'suburb',
      'city',
      'town',
      'village',
    ]) {
      final value = address[key] as String?;
      if (value != null && value.trim().isNotEmpty) return value;
    }

    return null;
  }

  void close() => _client.close();
}

/// Error devuelto por el servicio de geocodificación.
class NominatimException implements Exception {
  const NominatimException(this.message, this.statusCode);

  final String message;
  final int statusCode;

  @override
  String toString() => 'NominatimException($statusCode): $message';
}