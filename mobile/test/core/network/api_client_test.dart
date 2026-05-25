import 'dart:async';
import 'dart:convert';
import 'dart:io' show SocketException;

import 'package:aparcaceres/core/network/api_client.dart';
import 'package:aparcaceres/core/network/api_envelope.dart';
import 'package:aparcaceres/core/network/api_exceptions.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

ApiClient _client(MockClientHandler handler, {TokenProvider? tokenProvider}) {
  return ApiClient(httpClient: MockClient(handler), tokenProvider: tokenProvider);
}

void main() {
  group('ApiClient', () {
    test('decodes 2xx JSON body and forwards default headers', () async {
      Map<String, String>? captured;
      Uri? capturedUri;
      final client = _client((http.Request req) async {
        captured = req.headers;
        capturedUri = req.url;
        return http.Response(
          jsonEncode({'items': [], 'total': 0}),
          200,
          headers: {'content-type': 'application/json'},
        );
      });

      final result = await client.getJson('/parkings', query: {'limit': '10'});

      expect(result, isA<Map<String, dynamic>>());
      expect(captured!['Accept'], 'application/json');
      expect(captured!['User-Agent'], contains('AparCaceres'));
      expect(captured!.containsKey('Authorization'), isFalse);
      expect(capturedUri!.path, '/parkings');
      expect(capturedUri!.queryParameters['limit'], '10');
    });

    test('injects bearer token when requiresAuth is true', () async {
      Map<String, String>? captured;
      final client = _client(
        (http.Request req) async {
          captured = req.headers;
          return http.Response('[]', 200);
        },
        tokenProvider: () async => 'jwt-abc',
      );

      await client.getJson('/users/me/favorites', requiresAuth: true);

      expect(captured!['Authorization'], 'Bearer jwt-abc');
    });

    test('omits Authorization when token provider returns null', () async {
      Map<String, String>? captured;
      final client = _client(
        (http.Request req) async {
          captured = req.headers;
          return http.Response('[]', 200);
        },
        tokenProvider: () async => null,
      );

      await client.getJson('/users/me/favorites', requiresAuth: true);

      expect(captured!.containsKey('Authorization'), isFalse);
    });

    test('maps 4xx into ApiException with FastAPI detail', () async {
      final client = _client(
        (_) async => http.Response(
          jsonEncode({'detail': 'parking not found'}),
          404,
        ),
      );

      await expectLater(
        client.getJson('/parkings/missing'),
        throwsA(
          isA<ApiException>()
              .having((e) => e.statusCode, 'statusCode', 404)
              .having((e) => e.message, 'message', 'parking not found'),
        ),
      );
    });

    test('maps 5xx into ApiUnavailableException', () async {
      final client = _client(
        (_) async => http.Response('upstream boom', 503),
      );

      await expectLater(
        client.getJson('/parkings'),
        throwsA(
          isA<ApiUnavailableException>().having(
            (e) => e.statusCode,
            'statusCode',
            503,
          ),
        ),
      );
    });

    test('maps SocketException into ApiUnavailableException', () async {
      final client = _client(
        (_) async => throw const SocketException('connection refused'),
      );

      await expectLater(
        client.getJson('/parkings'),
        throwsA(isA<ApiUnavailableException>()),
      );
    });

    test('maps timeout into ApiTimeoutException', () async {
      final client = _client(
        (_) async => throw TimeoutException('slow'),
      );

      await expectLater(
        client.getJson('/parkings'),
        throwsA(isA<ApiTimeoutException>()),
      );
    });

    test('cancellation wins the race and throws ApiCancelledException',
        () async {
      final completer = Completer<http.Response>();
      final client = _client((_) => completer.future);

      final cancelToken = CancelToken();
      final pending = client.getJson('/parkings', cancelToken: cancelToken);
      cancelToken.cancel();

      await expectLater(pending, throwsA(isA<ApiCancelledException>()));
      // El handler todavía no ha resuelto: la cancelación corre antes.
      expect(completer.isCompleted, isFalse);
      completer.complete(http.Response('[]', 200));
    });

    test('pre-cancelled token short-circuits before dispatch', () async {
      var dispatched = false;
      final client = _client((_) async {
        dispatched = true;
        return http.Response('[]', 200);
      });

      final cancelToken = CancelToken()..cancel();

      await expectLater(
        client.getJson('/parkings', cancelToken: cancelToken),
        throwsA(isA<ApiCancelledException>()),
      );
      expect(dispatched, isFalse);
    });

    test('postJson encodes body and sets Content-Type', () async {
      Map<String, String>? captured;
      String? capturedBody;
      final client = _client((http.Request req) async {
        captured = req.headers;
        capturedBody = req.body;
        return http.Response('{}', 200);
      });

      await client.postJson('/auth/session', body: {'email': 'a@b.c'});

      expect(captured!['Content-Type'], contains('application/json'));
      expect(jsonDecode(capturedBody!), {'email': 'a@b.c'});
    });
  });

  group('parseListResponse', () {
    test('reads items from envelope shape', () {
      final result = parseListResponse<int>(
        {'items': [1, 2, 3].map((i) => {'v': i}).toList(), 'total': 3},
        (m) => m['v'] as int,
      );
      expect(result, [1, 2, 3]);
    });

    test('reads items from flat list shape', () {
      final result = parseListResponse<String>(
        [
          {'name': 'a'},
          {'name': 'b'},
        ],
        (m) => m['name'] as String,
      );
      expect(result, ['a', 'b']);
    });

    test('throws ApiException on unexpected shape', () {
      expect(
        () => parseListResponse<int>(42, (_) => 0),
        throwsA(isA<ApiException>()),
      );
    });

    test('throws ApiException when items is not a list of objects', () {
      expect(
        () => parseListResponse<int>(
          {'items': [1, 2, 3]},
          (_) => 0,
        ),
        throwsA(isA<ApiException>()),
      );
    });
  });
}
