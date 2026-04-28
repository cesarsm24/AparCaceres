import 'package:flutter/foundation.dart';

import '../../../core/providers.dart';
import 'server_favorites_store.dart';

/// Cache local de los ids favoritos del usuario.
///
/// Sigue siendo un `ChangeNotifier` para que los widgets que pintan el
/// corazón usen `ListenableBuilder` y se actualicen al instante. La cache en
/// memoria es un espejo del sorted set que vive en Redis y se sincroniza con
/// `GET /users/me/favorites`, `PUT /users/me/favorites/{id}` y
/// `DELETE /users/me/favorites/{id}`.
abstract class FavoritesStore extends ChangeNotifier {
  Set<String> get ids;
  bool contains(String id);
  void add(String id);
  void remove(String id);
  void toggle(String id);

  /// Refresca la cache contra la fuente de verdad.
  Future<void> reload();
}

/// Implementación respaldada por el backend FastAPI.
final FavoritesStore favoritesStore = ServerFavoritesStore(
  apiClient: sharedApiClient,
);
