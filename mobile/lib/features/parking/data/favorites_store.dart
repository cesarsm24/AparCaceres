import 'package:flutter/foundation.dart';

import '../../../core/providers.dart';
import 'server_favorites_store.dart';

/// Cache local de los ids favoritos del usuario.
///
/// Sigue siendo un `ChangeNotifier` para que los widgets que pintan el
/// corazón usen `ListenableBuilder` y se actualicen al instante. Las dos
/// implementaciones son intercambiables:
///   - `LocalFavoritesStore`: se usa en modo `--dart-define=USE_LOCAL_DATA=true`
///     y vive solo en memoria con unos ids semilla del fixture.
///   - `ServerFavoritesStore`: el modo normal contra FastAPI; sincroniza la
///     cache con `GET /users/me/favorites` y aplica los toggles vía
///     `PUT/DELETE /users/me/favorites/{id}` con rollback si el servidor
///     rechaza la operación.
abstract class FavoritesStore extends ChangeNotifier {
  Set<String> get ids;
  bool contains(String id);
  void add(String id);
  void remove(String id);
  void toggle(String id);

  /// Refresca la cache contra la fuente de verdad. En la versión local es
  /// un no-op porque ya tenemos los ids en memoria desde el primer arranque.
  Future<void> reload();
}

/// Implementación in-memory para el modo demo (`USE_LOCAL_DATA=true`).
class LocalFavoritesStore extends FavoritesStore {
  LocalFavoritesStore({Iterable<String> seedIds = const <String>[]})
    : _ids = Set<String>.from(seedIds);

  final Set<String> _ids;

  @override
  Set<String> get ids => Set.unmodifiable(_ids);

  @override
  bool contains(String id) => _ids.contains(id);

  @override
  void add(String id) {
    if (_ids.add(id)) notifyListeners();
  }

  @override
  void remove(String id) {
    if (_ids.remove(id)) notifyListeners();
  }

  @override
  void toggle(String id) {
    if (!_ids.add(id)) _ids.remove(id);
    notifyListeners();
  }

  @override
  Future<void> reload() async {
    // No hay servidor que consultar; la cache ya es la fuente.
  }
}

/// Modo demo `--dart-define=USE_LOCAL_DATA=true`: el repo lee del fixture y
/// los favoritos viven en memoria con unos ids semilla. En producción
/// usamos `ServerFavoritesStore` contra FastAPI.
const bool _useLocalData = bool.fromEnvironment(
  'USE_LOCAL_DATA',
  defaultValue: false,
);

final FavoritesStore favoritesStore = _useLocalData
    ? LocalFavoritesStore(
        seedIds: const [
          'parking-obispo-galarza',
          'zona-azul-rodriguez-ledesma',
          'pmr-avenida-arenas',
          'parking-bicis-colon',
        ],
      )
    : ServerFavoritesStore(apiClient: sharedApiClient);
