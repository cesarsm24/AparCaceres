import '../../../core/network/api_client.dart';
import '../../../core/network/api_envelope.dart';
import '../../../core/network/api_exceptions.dart';
import '../domain/parking_place.dart';
import '../domain/parking_query.dart';
import '../domain/parking_repository.dart';

/// Repositorio de aparcamientos respaldado por la API HTTP.
///
/// Construye las consultas contra FastAPI y delega la transformación del wire
/// al modelo de dominio `ParkingPlace`.
class ApiParkingRepository implements ParkingRepository {
  ApiParkingRepository({required ApiClient client}) : _client = client;

  final ApiClient _client;

  /// Devuelve aparcamientos filtrados, usando búsqueda geográfica cuando hay centro.
  @override
  Future<List<ParkingPlace>> getNearby(
      ParkingQuery query, {
        CancelToken? cancelToken,
      }) async {
    final filters = _filterParams(query);
    final Map<String, dynamic> params;
    final String path;

    if (query.center == null) {
      path = '/parkings';
      params = filters;
    } else {
      path = '/parkings/nearby';
      params = {
        'lat': query.center!.latitude.toString(),
        'lng': query.center!.longitude.toString(),
        'radiusMeters': query.radiusMeters.toString(),
        ...filters,
      };
    }

    final json = await _client.getJson(
      path,
      query: params,
      cancelToken: cancelToken,
    );

    return parseListResponse<ParkingPlace>(json, ParkingPlace.fromJson);
  }

  @override
  Future<ParkingPlace?> getById(String id) async {
    try {
      final json = await _client.getJson('/parkings/$id');

      if (json is! Map<String, dynamic>) {
        throw ApiException('Unexpected place shape: ${json.runtimeType}');
      }

      return ParkingPlace.fromJson(json);
    } on ApiException catch (e) {
      if (e.statusCode == 404) return null;
      rethrow;
    }
  }

  @override
  Future<List<ParkingCategory>> getCategories() async {
    final json = await _client.getJson('/parkings/categories');

    if (json is! List) {
      throw ApiException('Unexpected categories shape: ${json.runtimeType}');
    }

    return json
        .map((value) => parkingCategoryFromWire(value as String?))
        .toSet()
        .toList()
      ..sort((a, b) => a.index.compareTo(b.index));
  }

  /// Devuelve los favoritos del usuario autenticado, ordenados por adición reciente.
  @override
  Future<List<ParkingPlace>> getFavorites() async {
    final json = await _client.getJson(
      '/users/me/favorites',
      requiresAuth: true,
    );

    if (json is! List) {
      throw ApiException('Unexpected favorites shape: ${json.runtimeType}');
    }

    return [
      for (final item in json)
        if (item is Map<String, dynamic>) ParkingPlace.fromJson(item),
    ];
  }

  Map<String, dynamic> _filterParams(ParkingQuery query) {
    final params = <String, dynamic>{};

    if (query.vehicleTypes.isNotEmpty) {
      params['vehicleType'] = query.vehicleTypes.map((type) => type.wire).toList();
    }

    if (query.categories.isNotEmpty) {
      params['category'] = query.categories.map((category) => category.wire).toList();
    }

    if (query.regulations.isNotEmpty) {
      params['regulation'] = query.regulations
          .map((regulation) => regulation.wire)
          .toList();
    }

    if (query.minSpaces > 0) {
      params['minSpaces'] = query.minSpaces.toString();
    }

    return params;
  }
}