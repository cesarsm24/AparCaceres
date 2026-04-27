import '../../../core/providers.dart';
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

final ParkingRepository parkingRepository = _useLocalData
    ? LocalParkingRepository()
    : ApiParkingRepository(client: sharedApiClient);
