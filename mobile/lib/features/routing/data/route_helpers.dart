import '../../parking/domain/parking_place.dart';

String osrmProfileFor(ParkingCategory category) {
  return switch (category) {
    ParkingCategory.bicycle => 'bike',
    _ => 'car',
  };
}

String googleTravelModeFor(ParkingCategory category) {
  return switch (category) {
    ParkingCategory.bicycle => 'bicycling',
    ParkingCategory.motorbike => 'two-wheeler',
    _ => 'driving',
  };
}

String routingLabelFor(ParkingCategory category) {
  return switch (category) {
    ParkingCategory.bicycle => 'en bici',
    ParkingCategory.motorbike => 'en moto',
    _ => 'en coche',
  };
}
