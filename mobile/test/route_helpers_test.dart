import 'package:aparcaceres/features/parking/domain/parking_place.dart';
import 'package:aparcaceres/features/routing/data/route_helpers.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('routing label keeps PMR visible for accessible destinations', () {
    expect(routingLabelFor(ParkingCategory.accessible), 'PMR');
  });
}
