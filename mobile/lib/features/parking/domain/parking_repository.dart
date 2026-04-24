import 'parking_place.dart';
import 'parking_query.dart';

abstract class ParkingRepository {
  Future<List<ParkingPlace>> getNearby(ParkingQuery query);

  Future<ParkingPlace?> getById(String id);

  Future<List<ParkingCategory>> getCategories();

  Future<List<ParkingPlace>> getFavorites();
}
