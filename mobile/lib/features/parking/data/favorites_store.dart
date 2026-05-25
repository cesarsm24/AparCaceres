import 'package:flutter/foundation.dart';

import '../../../core/providers.dart';
import 'server_favorites_store.dart';

/// Caché observable de ids favoritos del usuario.
///
/// Actúa como espejo local de los favoritos persistidos en backend y notifica
/// cambios para actualizar la UI de forma inmediata.
abstract class FavoritesStore extends ChangeNotifier {
  Set<String> get ids;

  bool contains(String id);

  void add(String id);

  void remove(String id);

  void toggle(String id);

  /// Sincroniza la caché con la fuente de verdad remota.
  Future<void> reload();
}

/// Instancia compartida de favoritos respaldada por la API.
final FavoritesStore favoritesStore = ServerFavoritesStore(
  apiClient: sharedApiClient,
);