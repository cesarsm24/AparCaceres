import 'dart:async';

import 'package:flutter/material.dart';

import 'core/app.dart';
import 'features/parking/data/favorites_store.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();

  // La precarga de favoritos no bloquea el arranque: si falla, las pantallas
  // dependientes volverán a sincronizar y gestionarán el error en su propio estado.
  unawaited(favoritesStore.reload().catchError((_) {}));

  runApp(const AparCaceresApp());
}