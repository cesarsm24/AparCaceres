import 'dart:async';
import 'dart:convert';

import 'package:aparcaceres/core/network/api_client.dart';
import 'package:aparcaceres/features/parking/data/server_favorites_store.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

ServerFavoritesStore _store(MockClientHandler handler) {
  return ServerFavoritesStore(
    apiClient: ApiClient(
      httpClient: MockClient(handler),
      tokenProvider: () async => 'jwt-test',
    ),
  );
}

void main() {
  test('reload populates ids from /users/me/favorites response', () async {
    final store = _store(
      (_) async => http.Response(
        jsonEncode([
          {'id': 'a', 'name': 'A'},
          {'id': 'b', 'name': 'B'},
        ]),
        200,
      ),
    );

    await store.reload();

    expect(store.ids, {'a', 'b'});
  });

  test('add updates cache optimistically and PUTs to backend', () async {
    Uri? captured;
    final store = _store(
      (http.Request req) async {
        captured = req.url;
        return http.Response('{"id":"x","addedAt":"...","created":true}', 200);
      },
    );

    store.add('x');

    expect(store.contains('x'), isTrue);
    // Yield para que la PUT en background se complete antes de aserciones.
    await Future<void>.delayed(Duration.zero);
    expect(captured!.path, '/users/me/favorites/x');
  });

  test('add rolls back on backend failure', () async {
    final completer = Completer<http.Response>();
    final store = _store((_) => completer.future);

    var notifications = 0;
    store.addListener(() => notifications++);

    store.add('x');
    expect(store.contains('x'), isTrue);
    expect(notifications, 1); // optimistic

    completer.complete(http.Response('{"detail":"no"}', 404));
    await Future<void>.delayed(Duration.zero);

    expect(store.contains('x'), isFalse);
    expect(notifications, 2); // rollback notify
  });

  test('remove updates cache and DELETEs', () async {
    Uri? captured;
    final store = _store(
      (http.Request req) async {
        captured = req.url;
        return http.Response('{"id":"x","removed":true}', 200);
      },
    );
    store.add('x');
    await Future<void>.delayed(Duration.zero);

    store.remove('x');

    expect(store.contains('x'), isFalse);
    await Future<void>.delayed(Duration.zero);
    expect(captured!.path, '/users/me/favorites/x');
  });

  test('toggle adds when missing and removes when present', () async {
    final store = _store(
      (_) async => http.Response('{}', 200),
    );

    store.toggle('x');
    expect(store.contains('x'), isTrue);

    store.toggle('x');
    expect(store.contains('x'), isFalse);
  });

  test('reload does not notify when ids match cache', () async {
    final store = _store(
      (_) async => http.Response(
        jsonEncode([
          {'id': 'a'},
        ]),
        200,
      ),
    );
    await store.reload();
    var notifications = 0;
    store.addListener(() => notifications++);

    await store.reload();

    expect(notifications, 0);
  });
}
