import '../../../core/providers.dart';
import '../domain/parking_repository.dart';
import 'api_parking_repository.dart';

/// Repositorio HTTP de la app. Toda la UI consulta el backend FastAPI a
/// través de `ApiClient`; no existe una ruta local alternativa.
final ParkingRepository parkingRepository = ApiParkingRepository(
  client: sharedApiClient,
);
