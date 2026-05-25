import 'dart:convert';

import 'package:aparcaceres/features/routing/data/osrm_client.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:latlong2/latlong.dart';

String _osrmResponse() {
  return jsonEncode({
    'code': 'Ok',
    'routes': [
      {
        'distance': 120.0,
        'duration': 60.0,
        'geometry': {
          'coordinates': [
            [-6.37, 39.47],
            [-6.36, 39.48],
          ],
        },
      },
    ],
  });
}

void main() {
  test(
    'omits User-Agent when configured for browser-compatible requests',
    () async {
      Map<String, String>? captured;
      final client = OsrmClient(
        sendUserAgent: false,
        client: MockClient((http.Request req) async {
          captured = req.headers;
          return http.Response(_osrmResponse(), 200);
        }),
      );

      await client.route(
        'driving',
        const LatLng(39.47, -6.37),
        const LatLng(39.48, -6.36),
      );

      expect(captured!['Accept'], 'application/json');
      expect(captured!.containsKey('User-Agent'), isFalse);
    },
  );

  test('keeps User-Agent for native-style requests', () async {
    Map<String, String>? captured;
    final client = OsrmClient(
      sendUserAgent: true,
      userAgent: 'AparCaceres-test',
      client: MockClient((http.Request req) async {
        captured = req.headers;
        return http.Response(_osrmResponse(), 200);
      }),
    );

    await client.route(
      'walking',
      const LatLng(39.47, -6.37),
      const LatLng(39.48, -6.36),
    );

    expect(captured!['User-Agent'], 'AparCaceres-test');
  });
}
