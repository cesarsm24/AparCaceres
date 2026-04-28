import 'dart:async';

import 'package:flutter/foundation.dart';

import '../../../core/network/api_client.dart';
import 'favorites_store.dart';

/// Caché local de favoritos respaldada por el backend.
///
/// Mantiene una lectura síncrona para la UI y sincroniza cambios mediante
/// escrituras optimistas contra la API. Si una escritura remota falla, revierte
/// el cambio local para conservar la coherencia con la fuente de verdad.
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