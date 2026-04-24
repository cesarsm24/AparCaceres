import 'dart:convert';

import 'package:aparcaceres/features/parking/domain/parking_place.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test(
    'parking fixture parses representative geometry and categories',
    () async {
      final raw = await rootBundle.loadString(
        'assets/mock/parking_places.json',
      );
      final decoded = jsonDecode(raw) as Map<String, dynamic>;
      final places = (decoded['places'] as List<dynamic>)
          .map((json) => ParkingPlace.fromJson(json as Map<String, dynamic>))
          .toList();

      expect(places, isNotEmpty);
      expect(
        places.any((p) => p.geometryType == ParkingGeometryType.point),
        true,
      );
      expect(
        places.any((p) => p.geometryType == ParkingGeometryType.polygon),
        true,
      );
      expect(
        places.any((p) => p.geometryType == ParkingGeometryType.lineString),
        true,
      );
      expect(
        places.map((p) => p.category).toSet(),
        contains(ParkingCategory.blueZone),
      );
      expect(
        places.map((p) => p.category).toSet(),
        contains(ParkingCategory.accessible),
      );
      expect(places.any((p) => p.imageUrl != null), true);
    },
  );
}
