import 'dart:convert';

import 'package:aparcaceres/core/auth/auth_session.dart';
import 'package:aparcaceres/core/network/api_client.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

AuthSession _session({
  required MockClientHandler handler,
  DateTime Function()? now,
  String Function()? subGenerator,
}) {
  final apiClient = ApiClient(httpClient: MockClient(handler));
  return AuthSession(
    apiClient: apiClient,
    prefsLoader: SharedPreferences.getInstance,
    now: now,
    subGenerator: subGenerator,
  );
}

Map<String, dynamic> _sessionResponse(String token, DateTime expiresAt) {
  return {
    'token': token,
    'sub': 'whatever',
    'expiresAt': expiresAt.toUtc().toIso8601String(),
    'tokenType': 'Bearer',
  };
}

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues({});
  });

  test('mints a token via POST /auth/session on first call', () async {
    final calls = <Map<String, dynamic>>[];
    final session = _session(
      handler: (http.Request req) async {
        calls.add(jsonDecode(req.body) as Map<String, dynamic>);
        return http.Response(
          jsonEncode(
            _sessionResponse(
              'jwt-fresh',
              DateTime.utc(2026, 5, 1),
            ),
          ),
          200,
        );
      },
      now: () => DateTime.utc(2026, 4, 1),
      subGenerator: () => 'fixed-sub',
    );

    final token = await session.tokenForRequest();

    expect(token, 'jwt-fresh');
    expect(calls, hasLength(1));
    expect(calls.first['sub'], 'fixed-sub');
  });

  test('reuses cached token on second call within validity window', () async {
    var calls = 0;
    final session = _session(
      handler: (_) async {
        calls++;
        return http.Response(
          jsonEncode(
            _sessionResponse('jwt-1', DateTime.utc(2026, 5, 1)),
          ),
          200,
        );
      },
      now: () => DateTime.utc(2026, 4, 1),
      subGenerator: () => 'sub-1',
    );

    final t1 = await session.tokenForRequest();
    final t2 = await session.tokenForRequest();

    expect(t1, t2);
    expect(calls, 1);
  });

  test('refreshes when within the leeway window before expiresAt', () async {
    var calls = 0;
    var clock = DateTime.utc(2026, 4, 1);
    final session = AuthSession(
      apiClient: ApiClient(
        httpClient: MockClient((_) async {
          calls++;
          // 30-day TTL each issue.
          return http.Response(
            jsonEncode(
              _sessionResponse(
                'jwt-$calls',
                clock.add(const Duration(days: 30)),
              ),
            ),
            200,
          );
        }),
      ),
      now: () => clock,
      subGenerator: () => 'sub-x',
      refreshLeeway: const Duration(days: 1),
    );

    final first = await session.tokenForRequest();
    expect(first, 'jwt-1');

    // Avanza el reloj a 30 días después: dentro del leeway → debe refrescar.
    clock = clock.add(const Duration(days: 29, hours: 12));
    final second = await session.tokenForRequest();

    expect(second, 'jwt-2');
    expect(calls, 2);
  });

  test('parallel calls share a single in-flight refresh', () async {
    var calls = 0;
    final session = _session(
      handler: (_) async {
        calls++;
        await Future<void>.delayed(const Duration(milliseconds: 5));
        return http.Response(
          jsonEncode(
            _sessionResponse('jwt-1', DateTime.utc(2026, 5, 1)),
          ),
          200,
        );
      },
      now: () => DateTime.utc(2026, 4, 1),
      subGenerator: () => 'sub-x',
    );

    final results = await Future.wait([
      session.tokenForRequest(),
      session.tokenForRequest(),
      session.tokenForRequest(),
    ]);

    expect(results.toSet(), {'jwt-1'});
    expect(calls, 1);
  });

  test('persists sub across instances', () async {
    SharedPreferences.setMockInitialValues({});

    final first = _session(
      handler: (http.Request req) async {
        return http.Response(
          jsonEncode(
            _sessionResponse(
              'jwt-1',
              DateTime.utc(2026, 5, 1),
            ),
          ),
          200,
        );
      },
      now: () => DateTime.utc(2026, 4, 1),
      subGenerator: () => 'first-sub',
    );
    await first.tokenForRequest();

    Map<String, dynamic>? secondCall;
    final second = _session(
      handler: (http.Request req) async {
        secondCall = jsonDecode(req.body) as Map<String, dynamic>;
        return http.Response(
          jsonEncode(
            _sessionResponse(
              'jwt-2',
              DateTime.utc(2026, 6, 1),
            ),
          ),
          200,
        );
      },
      now: () => DateTime.utc(2026, 5, 5), // past first expiresAt
      // El subGenerator nuevo no debería ejecutarse: esperamos el sub del prefs.
      subGenerator: () => 'should-not-be-used',
    );
    await second.tokenForRequest();

    expect(secondCall, isNotNull);
    expect(secondCall!['sub'], 'first-sub');
  });
}
