import 'package:flutter/foundation.dart';

class FavoritesStore extends ChangeNotifier {
  FavoritesStore({Iterable<String> seedIds = const <String>[]})
    : _ids = Set<String>.from(seedIds);

  final Set<String> _ids;

  Set<String> get ids => Set.unmodifiable(_ids);

  bool contains(String id) => _ids.contains(id);

  void add(String id) {
    if (_ids.add(id)) notifyListeners();
  }

  void remove(String id) {
    if (_ids.remove(id)) notifyListeners();
  }

  void toggle(String id) {
    if (!_ids.add(id)) _ids.remove(id);
    notifyListeners();
  }
}

final FavoritesStore favoritesStore = FavoritesStore(
  seedIds: const [
    'parking-obispo-galarza',
    'zona-azul-rodriguez-ledesma',
    'pmr-avenida-arenas',
    'parking-bicis-colon',
  ],
);
