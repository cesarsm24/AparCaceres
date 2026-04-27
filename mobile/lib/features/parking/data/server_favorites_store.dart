import 'dart:async';

import 'package:flutter/foundation.dart';

import '../../../core/network/api_client.dart';
import 'favorites_store.dart';

/// Cache local de favoritos respaldada por el backend.
///
/// El truco está en mantener `contains` síncrono — el ícono del corazón
/// necesita decidir su estado en el frame actual — pero sin perder la
/// fuente de verdad: el set en memoria es un espejo del sorted set que
/// vive en Redis (`user:{sub}:favorites`), refrescable bajo demanda.
///
/// Reglas:
///   - `add` / `remove` actualizan la cache primero (UI optimista) y luego
///     disparan `PUT` / `DELETE`. Si el backend rechaza, se hace rollback y
///     se vuelve a notificar para que la UI corrija.
///   - `reload` consulta `GET /users/me/favorites` y reescribe la cache.
///     Solo notifica si hay un cambio real, así no entra en bucle con un
///     `ListenableBuilder` que cuelgue de la propia store.
///   - `toggle` simplemente delega en `add` / `remove`. Ningún caller debe
///     llamar al endpoint a mano.
class ServerFavoritesStore extends FavoritesStore {
  ServerFavoritesStore({required ApiClient apiClient}) : _apiClient = apiClient;

  final ApiClient _apiClient;
  final Set<String> _ids = <String>{};

  @override
  Set<String> get ids => Set.unmodifiable(_ids);

  @override
  bool contains(String id) => _ids.contains(id);

  @override
  void add(String id) {
    if (!_ids.add(id)) return;
    notifyListeners();
    unawaited(_putRemote(id));
  }

  @override
  void remove(String id) {
    if (!_ids.remove(id)) return;
    notifyListeners();
    unawaited(_deleteRemote(id));
  }

  @override
  void toggle(String id) {
    if (_ids.contains(id)) {
      remove(id);
    } else {
      add(id);
    }
  }

  @override
  Future<void> reload() async {
    final json = await _apiClient.getJson(
      '/users/me/favorites',
      requiresAuth: true,
    );
    if (json is! List) return;
    final next = <String>{};
    for (final item in json) {
      if (item is Map && item['id'] is String) {
        next.add(item['id'] as String);
      }
    }
    if (setEquals(_ids, next)) return;
    _ids
      ..clear()
      ..addAll(next);
    notifyListeners();
  }

  Future<void> _putRemote(String id) async {
    try {
      await _apiClient.putJson(
        '/users/me/favorites/$id',
        requiresAuth: true,
      );
    } catch (_) {
      // El servidor rechazó el alta (404 si el id no está en el catálogo,
      // 401 si la sesión cayó, 503 si Redis no responde): rollback.
      _ids.remove(id);
      notifyListeners();
    }
  }

  Future<void> _deleteRemote(String id) async {
    try {
      await _apiClient.deleteJson(
        '/users/me/favorites/$id',
        requiresAuth: true,
      );
    } catch (_) {
      _ids.add(id);
      notifyListeners();
    }
  }
}
