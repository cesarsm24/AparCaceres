import 'dart:io' show Platform;

import 'package:flutter/foundation.dart' show kIsWeb;

/// Configuración de acceso al backend de AparCáceres.
///
/// La URL base puede fijarse en compilación mediante `API_BASE_URL`. Si no se
/// define, se elige un valor adecuado para el entorno de ejecución: el emulador
/// Android usa la puerta de enlace al host y el resto de plataformas usan
/// `localhost`.
class ApiConfig {
  const ApiConfig._();

  static const String _envBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: '',
  );

  /// URL base del backend, sin barra final.
  static String get baseUrl {
    if (_envBaseUrl.isNotEmpty) return _stripTrailingSlash(_envBaseUrl);
    if (kIsWeb) return 'http://localhost:8000';
    if (Platform.isAndroid) return 'http://10.0.2.2:8000';
    return 'http://localhost:8000';
  }

  /// Tiempo máximo de espera por petición HTTP.
  static const Duration requestTimeout = Duration(seconds: 10);

  /// Identificador de cliente enviado en `User-Agent`.
  static const String userAgent = 'AparCaceres/1.0 (mobile)';

  /// Reescribe imágenes del SIG mediante el proxy del backend cuando conviene.
  ///
  /// En miniaturas siempre usamos el proxy para obtener la versión reducida.
  /// En imagen original solo lo hacemos en web, donde evita bloqueos CORS.
  static String? rewriteImageUrlForCurrentPlatform(
    String? rawUrl, {
    bool thumbnail = false,
  }) {
    if (rawUrl == null || rawUrl.isEmpty) return rawUrl;
    if (!rawUrl.contains('sig.caceres.es')) return rawUrl;
    if (!thumbnail && !kIsWeb) return rawUrl;

    final encoded = Uri.encodeQueryComponent(rawUrl);
    final size = thumbnail ? '&size=thumb' : '';
    return '$baseUrl/photo-proxy?u=$encoded$size';
  }

  static String _stripTrailingSlash(String value) {
    if (value.endsWith('/')) return value.substring(0, value.length - 1);
    return value;
  }
}
