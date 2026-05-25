import '../../../core/providers.dart';
import '../domain/parking_repository.dart';
import 'api_parking_repository.dart';

/// Repositorio compartido de aparcamientos respaldado por la API HTTP.
final ParkingRepository parkingRepository = ApiParkingRepository(
  client: sharedApiClient,
);