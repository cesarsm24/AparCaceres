import 'dart:io' show Platform;

import 'package:flutter/foundation.dart' show kIsWeb;

/// Configuración de la conexión con el backend de AparCáceres.
///
/// La `baseUrl` se resuelve por orden de precedencia:
///   1. Variable de compilación `--dart-define=API_BASE_URL=...`. Permite
///      sobrescribir el destino sin tocar código (CI, staging, dispositivo
///      físico contra una IP de la LAN).
///   2. Android nativo (incluye emulador): `http://10.0.2.2:8000`. La IP
///      `10.0.2.2` apunta al host desde dentro del emulador; `localhost`
///      desde el emulador resuelve al propio dispositivo virtual.
///   3. Resto (iOS simulator, escritorio, Flutter web): `http://localhost:8000`.
///
/// Los timeouts acotan el peor caso de la app frente a un backend lento o
/// caído: el cliente HTTP corta la espera con `Future.timeout` y el wrapper
/// la convierte en `ApiTimeoutException`.
class ApiConfig {
  const ApiConfig._();

  static const String _envBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: '',
  );

  /// URL base del backend. Sin trailing slash para que las rutas concretas
  /// se concatenen como `'$baseUrl/parkings/nearby'`.
  static String get baseUrl {
    if (_envBaseUrl.isNotEmpty) return _stripTrailingSlash(_envBaseUrl);
    if (kIsWeb) return 'http://localhost:8000';
    if (Platform.isAndroid) return 'http://10.0.2.2:8000';
    return 'http://localhost:8000';
  }

  /// Timeout aplicado a cada request HTTP (conexión + lectura combinadas,
  /// porque `package:http` no expone los dos por separado).
  static const Duration requestTimeout = Duration(seconds: 10);

  /// Identificador del cliente que se envía en `User-Agent`. El backend lo
  /// registra en logs de acceso y resulta útil para distinguir tráfico de la
  /// app frente a navegadores u otras herramientas durante depuración.
  static const String userAgent = 'AparCaceres/1.0 (mobile)';

  /// Reescribe URLs de imagen del SIG para pasar por el proxy del backend
  /// **solo en Flutter web**. El SIG no manda `Access-Control-Allow-Origin`,
  /// por lo que `Image.network` (que en web usa XHR) ve un CORS error y la
  /// imagen no se pinta. En nativo (Android/iOS) `Image.network` no usa XHR
  /// y por tanto no le aplica CORS, así que ahí mantenemos la URL directa
  /// para no enrutar tráfico innecesario por nuestro backend.
  static String? rewriteImageUrlForCurrentPlatform(String? rawUrl) {
    if (rawUrl == null || rawUrl.isEmpty) return rawUrl;
    if (!kIsWeb) return rawUrl;
    if (!rawUrl.contains('sig.caceres.es')) return rawUrl;
    final encoded = Uri.encodeQueryComponent(rawUrl);
    return '$baseUrl/photo-proxy?u=$encoded';
  }

  static String _stripTrailingSlash(String value) {
    if (value.endsWith('/')) return value.substring(0, value.length - 1);
    return value;
  }
}
