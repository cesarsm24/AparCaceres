import 'package:flutter/material.dart';

import '../../../theme/app_colors.dart';
import '../domain/parking_place.dart';

/// Presentación visual de las categorías de aparcamiento.
extension ParkingCategoryUi on ParkingCategory {
  String get label {
    return switch (this) {
      ParkingCategory.parking => 'Aparcamiento',
      ParkingCategory.paidParking => 'Parking de pago',
      ParkingCategory.streetLine => 'En línea',
      ParkingCategory.streetBattery => 'En batería',
      ParkingCategory.blueZone => 'Zona azul',
      ParkingCategory.accessible => 'PMR',
      ParkingCategory.motorbike => 'Motos',
      ParkingCategory.bicycle => 'Bicis',
      ParkingCategory.loading => 'Carga/descarga',
    };
  }

  IconData get icon {
    return switch (this) {
      ParkingCategory.parking => Icons.local_parking_outlined,
      ParkingCategory.paidParking => Icons.local_parking,
      ParkingCategory.streetLine => Icons.align_horizontal_left,
      ParkingCategory.streetBattery => Icons.view_week_outlined,
      ParkingCategory.blueZone => Icons.payments_outlined,
      ParkingCategory.accessible => Icons.accessible,
      ParkingCategory.motorbike => Icons.two_wheeler,
      ParkingCategory.bicycle => Icons.pedal_bike,
      ParkingCategory.loading => Icons.local_shipping_outlined,
    };
  }

  Color get color {
    return switch (this) {
      ParkingCategory.parking => AppColors.success,
      ParkingCategory.paidParking => AppColors.primary,
      ParkingCategory.streetLine => const Color(0xFF0F766E),
      ParkingCategory.streetBattery => const Color(0xFF047857),
      ParkingCategory.blueZone => AppColors.accent,
      ParkingCategory.accessible => const Color(0xFF7C3AED),
      ParkingCategory.motorbike => const Color(0xFFEA580C),
      ParkingCategory.bicycle => const Color(0xFF16A34A),
      ParkingCategory.loading => const Color(0xFFD97706),
    };
  }
}

/// Presentación visual de los tipos de vehículo.
extension ParkingVehicleUi on ParkingVehicleType {
  String get label {
    return switch (this) {
      ParkingVehicleType.car => 'Coche',
      ParkingVehicleType.motorbike => 'Moto',
      ParkingVehicleType.bike => 'Bici',
    };
  }

  IconData get icon {
    return switch (this) {
      ParkingVehicleType.car => Icons.directions_car_outlined,
      ParkingVehicleType.motorbike => Icons.two_wheeler,
      ParkingVehicleType.bike => Icons.pedal_bike,
    };
  }
}

/// Presentación visual de los regímenes de aparcamiento.
extension ParkingRegulationUi on ParkingRegulation {
  String get label {
    return switch (this) {
      ParkingRegulation.free => 'Libre',
      ParkingRegulation.paid => 'Pago',
      ParkingRegulation.blueZone => 'Zona azul',
      ParkingRegulation.loading => 'Carga/descarga',
      ParkingRegulation.reserved => 'Reservada',
    };
  }

  Color get color {
    return switch (this) {
      ParkingRegulation.free => AppColors.success,
      ParkingRegulation.paid => AppColors.primary,
      ParkingRegulation.blueZone => AppColors.accent,
      ParkingRegulation.loading => const Color(0xFFD97706),
      ParkingRegulation.reserved => const Color(0xFF7C3AED),
    };
  }
}

String formatDistance(double meters) {
  if (meters >= 1000) {
    return 'A ${(meters / 1000).toStringAsFixed(1)} km';
  }

  return 'A ${meters.round()} m';
}

String? formatSpaces(int? spaces) {
  if (spaces == null) return null;
  if (spaces == 1) return '1 plaza registrada';

  return '$spaces plazas registradas';
}