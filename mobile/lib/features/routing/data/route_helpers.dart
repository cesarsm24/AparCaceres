import '../../parking/domain/parking_place.dart';

/// Perfil OSRM más adecuado para una categoría de aparcamiento.
String osrmProfileFor(ParkingCategory category) {
  return switch (category) {
    ParkingCategory.bicycle => 'bike',
    _ => 'car',
  };
}

/// Modo de viaje usado al abrir la ruta en Google Maps.
String googleTravelModeFor(ParkingCategory category) {
  return switch (category) {
    ParkingCategory.bicycle => 'bicycling',
    ParkingCategory.motorbike => 'two-wheeler',
    _ => 'driving',
  };
}

/// Etiqueta breve para mensajes de cálculo de ruta.
String routingLabelFor(ParkingCategory category) {
  return switch (category) {
    ParkingCategory.bicycle => 'en bici',
    ParkingCategory.motorbike => 'en moto',
    ParkingCategory.accessible => 'PMR',
    _ => 'en coche',
  };
}