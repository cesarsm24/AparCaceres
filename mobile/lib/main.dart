import 'dart:async';

import 'package:flutter/material.dart';

import 'core/app.dart';
import 'features/parking/data/favorites_store.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  // Precarga la cache de favoritos para que el estado del corazón esté
  // disponible desde el inicio. Si la sincronización falla, el arranque
  // continúa y la siguiente vista dependiente mostrará el error correspondiente.
  unawaited(favoritesStore.reload().catchError((_) {}));
  runApp(const AparCaceresApp());
}
