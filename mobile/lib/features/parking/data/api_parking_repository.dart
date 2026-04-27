import '../../../core/network/api_client.dart';
import '../../../core/network/api_envelope.dart';
import '../../../core/network/api_exceptions.dart';
import '../domain/parking_place.dart';
import '../domain/parking_query.dart';
import '../domain/parking_repository.dart';
import 'favorites_store.dart';

/// Adapta la API HTTP de FastAPI al contrato `ParkingRepository` que consume
/// la UI. La traducción wire ↔ dominio vive en `parking_place.dart`; aquí
/// solo se construyen las URLs y se manejan los códigos de respuesta.
class ApiParkingRepository implements ParkingRepository {
  ApiParkingRepository({required ApiClient client, FavoritesStore? favorites})
    : _client = client,
      _favorites = favorites ?? favoritesStore;

  final ApiClient _client;
  final FavoritesStore _favorites;

  /// Si `query.center` es nulo cae a `/parkings` (listado global con filtros);
  /// con centro usa `/parkings/nearby` para que el backend ordene por
  /// distancia con RediSearch geo.
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
      // 404 es un caso esperado (id desconocido o caducado): la UI lo
      // distingue de un fallo de red mostrando "no encontrado".
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

  /// Hasta Fase D los favoritos viven en `FavoritesStore` local. Aquí solo
  /// resolvemos los ids contra `/parkings?ids=` para devolver el detalle
  /// fresco del backend en lugar del fixture mock.
  @override
  Future<List<ParkingPlace>> getFavorites() async {
    final ids = _favorites.ids.toList();
    if (ids.isEmpty) return const <ParkingPlace>[];
    final json = await _client.getJson(
      '/parkings',
      query: {'ids': ids},
    );
    return parseListResponse<ParkingPlace>(json, ParkingPlace.fromJson);
  }

  Map<String, dynamic> _filterParams(ParkingQuery query) {
    final params = <String, dynamic>{};
    if (query.vehicleTypes.isNotEmpty) {
      params['vehicleType'] = query.vehicleTypes.map((v) => v.wire).toList();
    }
    if (query.categories.isNotEmpty) {
      params['category'] = query.categories.map((c) => c.wire).toList();
    }
    if (query.regulations.isNotEmpty) {
      params['regulation'] = query.regulations.map((r) => r.wire).toList();
    }
    if (query.minSpaces > 0) {
      params['minSpaces'] = query.minSpaces.toString();
    }
    return params;
  }
}
