import 'dart:convert';

import 'package:aparcaceres/core/network/api_client.dart';
import 'package:aparcaceres/core/network/api_exceptions.dart';
import 'package:aparcaceres/features/parking/data/api_parking_repository.dart';
import 'package:aparcaceres/features/parking/data/favorites_store.dart';
import 'package:aparcaceres/features/parking/domain/parking_place.dart';
import 'package:aparcaceres/features/parking/domain/parking_query.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:latlong2/latlong.dart';

Map<String, dynamic> _samplePlace(String id) => {
  'id': id,
  'name': 'Sample $id',
  'category': 'paid_parking',
  'vehicleType': 'car',
  'regulation': 'paid',
  'geometryType': 'point',
  'latitude': 39.4753,
  'longitude': -6.3724,
  'totalSpaces': 50,
};

ApiParkingRepository _repo(
  MockClientHandler handler, {
  FavoritesStore? favorites,
}) {
  final client = ApiClient(httpClient: MockClient(handler));
  return ApiParkingRepository(client: client, favorites: favorites);
}

void main() {
  group('ApiParkingRepository.getNearby', () {
    test('without center hits /parkings with filter params', () async {
      Uri? captured;
      final repo = _repo((http.Request req) async {
        captured = req.url;
        return http.Response(
          jsonEncode({'items': [_samplePlace('a')], 'total': 1}),
          200,
        );
      });

      final places = await repo.getNearby(
        ParkingQuery(
          categories: {ParkingCategory.paidParking, ParkingCategory.blueZone},
          minSpaces: 10,
        ),
      );

      expect(places, hasLength(1));
      expect(captured!.path, '/parkings');
      expect(
        captured!.queryParametersAll['category'],
        containsAll(<String>['paid_parking', 'blue_zone']),
      );
      expect(captured!.queryParameters['minSpaces'], '10');
      expect(captured!.queryParameters.containsKey('lat'), isFalse);
    });

    test('with center hits /parkings/nearby with lat/lng/radiusMeters',
        () async {
      Uri? captured;
      final repo = _repo((http.Request req) async {
        captured = req.url;
        return http.Response(
          jsonEncode({'items': [_samplePlace('b')], 'total': 1}),
          200,
        );
      });

      await repo.getNearby(
        const ParkingQuery(
          center: LatLng(39.47, -6.37),
          radiusMeters: 800,
          vehicleTypes: {ParkingVehicleType.motorbike},
        ),
      );

      expect(captured!.path, '/parkings/nearby');
      expect(captured!.queryParameters['lat'], '39.47');
      expect(captured!.queryParameters['lng'], '-6.37');
      expect(captured!.queryParameters['radiusMeters'], '800');
      expect(captured!.queryParameters['vehicleType'], 'motorbike');
    });

    test('omits empty filter sets to keep URL clean', () async {
      Uri? captured;
      final repo = _repo((http.Request req) async {
        captured = req.url;
        return http.Response(
          jsonEncode({'items': <Map<String, dynamic>>[], 'total': 0}),
          200,
        );
      });

      await repo.getNearby(const ParkingQuery());

      expect(captured!.queryParameters, isEmpty);
    });
  });

  group('ApiParkingRepository.getById', () {
    test('returns the place on 200', () async {
      final repo = _repo(
        (_) async => http.Response(jsonEncode(_samplePlace('xyz')), 200),
      );

      final place = await repo.getById('xyz');

      expect(place, isNotNull);
      expect(place!.id, 'xyz');
    });

    test('returns null on 404 instead of throwing', () async {
      final repo = _repo(
        (_) async => http.Response(
          jsonEncode({'detail': 'not found'}),
          404,
        ),
      );

      expect(await repo.getById('missing'), isNull);
    });

    test('rethrows non-404 ApiException', () async {
      final repo = _repo(
        (_) async => http.Response('boom', 500),
      );

      await expectLater(
        repo.getById('any'),
        throwsA(isA<ApiUnavailableException>()),
      );
    });
  });

  group('ApiParkingRepository.getCategories', () {
    test('decodes flat list of wire strings into enum, sorted by index',
        () async {
      final repo = _repo(
        (_) async => http.Response(
          jsonEncode(['blue_zone', 'paid_parking', 'parking', 'unknown_x']),
          200,
        ),
      );

      final categories = await repo.getCategories();

      // unknown_x falls back to ParkingCategory.parking — collapsed by toSet().
      expect(categories, [
        ParkingCategory.parking,
        ParkingCategory.paidParking,
        ParkingCategory.blueZone,
      ]);
    });
  });

  group('ApiParkingRepository.getFavorites', () {
    test('returns empty without hitting the network when no local ids',
        () async {
      var hit = false;
      final favorites = FavoritesStore();
      final repo = _repo(
        (_) async {
          hit = true;
          return http.Response('[]', 200);
        },
        favorites: favorites,
      );

      expect(await repo.getFavorites(), isEmpty);
      expect(hit, isFalse);
    });

    test('queries /parkings?ids= with all favorited ids', () async {
      Uri? captured;
      final favorites = FavoritesStore(seedIds: ['a', 'b']);
      final repo = _repo(
        (http.Request req) async {
          captured = req.url;
          return http.Response(
            jsonEncode({'items': [_samplePlace('a'), _samplePlace('b')], 'total': 2}),
            200,
          );
        },
        favorites: favorites,
      );

      final places = await repo.getFavorites();

      expect(places, hasLength(2));
      expect(captured!.path, '/parkings');
      expect(captured!.queryParametersAll['ids'], containsAll(['a', 'b']));
    });
  });
}
