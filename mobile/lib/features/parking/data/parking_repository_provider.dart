import '../../../core/network/api_client.dart';
import '../domain/parking_repository.dart';
import 'api_parking_repository.dart';
import 'local_parking_repository.dart';

/// Permite forzar el repositorio mock con `--dart-define=USE_LOCAL_DATA=true`.
/// Pensado para desarrollo offline o demos sin backend levantado; en el flujo
/// normal apuntamos al FastAPI que define `ApiConfig.baseUrl`.
const bool _useLocalData = bool.fromEnvironment(
  'USE_LOCAL_DATA',
  defaultValue: false,
);

/// `ApiClient` se reusa en todas las pantallas para que el `http.Client`
/// subyacente mantenga su connection pool y los logs de debug salgan por un
/// único punto.
final ApiClient _sharedApiClient = ApiClient();

final ParkingRepository parkingRepository = _useLocalData
    ? LocalParkingRepository()
    : ApiParkingRepository(client: _sharedApiClient);
