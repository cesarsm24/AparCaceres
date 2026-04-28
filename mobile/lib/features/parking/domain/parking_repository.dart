import '../../../core/network/api_client.dart';
import 'parking_place.dart';
import 'parking_query.dart';

abstract class ParkingRepository {
  /// `cancelToken` permite descartar la petición cuando el usuario cambia
  /// filtros o centro antes de que llegue la respuesta.
  Future<List<ParkingPlace>> getNearby(
    ParkingQuery query, {
    CancelToken? cancelToken,
  });

  Future<ParkingPlace?> getById(String id);

  Future<List<ParkingCategory>> getCategories();

  Future<List<ParkingPlace>> getFavorites();
}
