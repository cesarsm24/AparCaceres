import '../../../core/network/api_client.dart';
import 'parking_place.dart';
import 'parking_query.dart';

/// Contrato de acceso al catálogo de aparcamientos.
///
/// La UI depende de esta abstracción para consultar listados, detalles,
/// categorías y favoritos sin acoplarse al transporte HTTP concreto.
abstract class ParkingRepository {
  /// Obtiene aparcamientos según los filtros dados.
  ///
  /// `cancelToken` permite descartar la petición cuando el usuario cambia
  /// filtros o centro antes de que llegue la respuesta.
  Future<List<ParkingPlace>> getNearby(
      ParkingQuery query, {
        CancelToken? cancelToken,
      });

  /// Busca un aparcamiento por id. Devuelve `null` si no existe.
  Future<ParkingPlace?> getById(String id);

  /// Devuelve las categorías presentes en el catálogo.
  Future<List<ParkingCategory>> getCategories();

  /// Devuelve los favoritos del usuario actual.
  Future<List<ParkingPlace>> getFavorites();
}