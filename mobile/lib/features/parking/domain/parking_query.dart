import 'package:latlong2/latlong.dart';

import 'parking_place.dart';

/// Criterios de consulta para el catálogo de aparcamientos.
///
/// Si `center` es `null`, la consulta representa un listado global filtrado.
/// Si incluye centro, el repositorio usa búsqueda por radio y ordenación por
/// distancia.
class ParkingQuery {
  const ParkingQuery({
    this.center,
    this.radiusMeters = 1000,
    this.vehicleTypes = const {},
    this.categories = const {},
    this.regulations = const {},
    this.minSpaces = 0,
  });

  final LatLng? center;
  final int radiusMeters;
  final Set<ParkingVehicleType> vehicleTypes;
  final Set<ParkingCategory> categories;
  final Set<ParkingRegulation> regulations;
  final int minSpaces;
}