import 'dart:async';

import 'package:flutter/material.dart';

import 'core/app.dart';
import 'features/parking/data/favorites_store.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  // Pre-warm el cache de favoritos contra el servidor para que el corazón
  // aparezca relleno en los detalles antes de que el usuario abra la
  // pantalla de favoritos. Best-effort: si falla (offline, sesión caída)
  // seguimos sin parar el arranque; la siguiente entrada a favoritos
  // mostrará el `ApiErrorState`.
  unawaited(favoritesStore.reload().catchError((_) {}));
  runApp(const AparCaceresApp());
}
