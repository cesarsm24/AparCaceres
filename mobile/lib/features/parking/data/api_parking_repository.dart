import '../domain/parking_place.dart';
import '../domain/parking_query.dart';
import '../domain/parking_repository.dart';

class ApiParkingRepository implements ParkingRepository {
  const ApiParkingRepository({required this.baseUrl});

  final String baseUrl;

  @override
  Future<List<ParkingPlace>> getNearby(ParkingQuery query) {
    throw UnimplementedError(
      'ApiParkingRepository will call FastAPI when the backend is available.',
    );
  }

  @override
  Future<ParkingPlace?> getById(String id) {
    throw UnimplementedError(
      'ApiParkingRepository will call FastAPI when the backend is available.',
    );
  }

  @override
  Future<List<ParkingCategory>> getCategories() {
    throw UnimplementedError(
      'ApiParkingRepository will call FastAPI when the backend is available.',
    );
  }

  @override
  Future<List<ParkingPlace>> getFavorites() {
    throw UnimplementedError(
      'Favorites are local until the API contract includes them.',
    );
  }
}
