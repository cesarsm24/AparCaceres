import 'dart:async';
import 'dart:math';

import 'package:shared_preferences/shared_preferences.dart';

import '../network/api_client.dart';
import '../network/api_exceptions.dart';

/// Token JWT cacheado: el valor en sí + cuándo caduca para poder anticiparnos
/// a la expiración antes de que el backend devuelva 401.
class _CachedToken {
  const _CachedToken({required this.token, required this.expiresAt});

  final String token;
  final DateTime expiresAt;
}

/// Gestiona el `sub` del dispositivo y el JWT que el backend emite a partir
/// de él vía `POST /auth/session`.
///
/// Modelo:
///   - El `sub` se genera la primera vez que se ejecuta la app (24 chars hex
///     aleatorios) y se persiste en `SharedPreferences`. Es estable entre
///     arranques mientras no se desinstale la app o se borre el storage.
///   - El JWT vive 30 días en el backend; aquí lo refrescamos cuando faltan
///     menos de 24 h para `expiresAt` para no encadenar 401 → reintento.
///   - `tokenForRequest()` es lo que consume `ApiClient.tokenProvider`.
///     Devuelve un token válido o lanza la excepción del backend si la
///     emisión falla (la pantalla mostrará `ApiErrorState`).
///
/// Sin login real: el `sub` es opaco; el backend confía en lo que enviamos.
/// Cuando se introduzca OAuth/OIDC, este componente cambiará para
/// intercambiar el token externo por el JWT interno.
class AuthSession {
  AuthSession({
    required ApiClient apiClient,
    Future<SharedPreferences> Function()? prefsLoader,
    DateTime Function()? now,
    String Function()? subGenerator,
    Duration refreshLeeway = const Duration(days: 1),
  }) : _apiClient = apiClient,
       _prefsLoader = prefsLoader ?? SharedPreferences.getInstance,
       _now = now ?? DateTime.now,
       _subGenerator = subGenerator ?? _defaultSubGenerator,
       _refreshLeeway = refreshLeeway;

  static const String _kSubKey = 'aparcaceres.auth.sub';
  static const String _kTokenKey = 'aparcaceres.auth.token';
  static const String _kExpiresAtKey = 'aparcaceres.auth.expiresAtMs';

  final ApiClient _apiClient;
  final Future<SharedPreferences> Function() _prefsLoader;
  final DateTime Function() _now;
  final String Function() _subGenerator;
  final Duration _refreshLeeway;

  _CachedToken? _cached;
  Future<_CachedToken>? _inFlight;

  /// Devuelve un JWT válido. Reusa la cache si todavía vive más allá del
  /// `refreshLeeway`; si no, hace `POST /auth/session` y la actualiza.
  /// Las llamadas concurrentes comparten la misma future en vuelo para no
  /// duplicar la emisión.
  Future<String> tokenForRequest() async {
    final cached = _cached ?? await _loadFromPrefs();
    if (cached != null && _isFresh(cached)) {
      _cached = cached;
      return cached.token;
    }
    final pending = _inFlight ?? (_inFlight = _refresh());
    try {
      final issued = await pending;
      return issued.token;
    } finally {
      if (identical(_inFlight, pending)) _inFlight = null;
    }
  }

  /// Borra el token y el `sub` persistidos. Pensado para "cerrar sesión" o
  /// recuperarse de un estado corrupto en desarrollo.
  Future<void> clear() async {
    final prefs = await _prefsLoader();
    await prefs.remove(_kSubKey);
    await prefs.remove(_kTokenKey);
    await prefs.remove(_kExpiresAtKey);
    _cached = null;
  }

  bool _isFresh(_CachedToken token) {
    return token.expiresAt.subtract(_refreshLeeway).isAfter(_now());
  }

  Future<_CachedToken?> _loadFromPrefs() async {
    final prefs = await _prefsLoader();
    final token = prefs.getString(_kTokenKey);
    final expiresAtMs = prefs.getInt(_kExpiresAtKey);
    if (token == null || expiresAtMs == null) return null;
    return _CachedToken(
      token: token,
      expiresAt: DateTime.fromMillisecondsSinceEpoch(expiresAtMs, isUtc: true),
    );
  }

  Future<_CachedToken> _refresh() async {
    final prefs = await _prefsLoader();
    var sub = prefs.getString(_kSubKey);
    if (sub == null || sub.isEmpty) {
      sub = _subGenerator();
      await prefs.setString(_kSubKey, sub);
    }

    final response = await _apiClient.postJson(
      '/auth/session',
      body: {'sub': sub},
    );
    if (response is! Map<String, dynamic>) {
      throw ApiException('Unexpected /auth/session shape: ${response.runtimeType}');
    }
    final token = response['token'];
    final expiresAtRaw = response['expiresAt'];
    if (token is! String || expiresAtRaw is! String) {
      throw const ApiException('Missing token or expiresAt in /auth/session response');
    }
    final expiresAt = DateTime.parse(expiresAtRaw).toUtc();

    await prefs.setString(_kTokenKey, token);
    await prefs.setInt(_kExpiresAtKey, expiresAt.millisecondsSinceEpoch);

    final cached = _CachedToken(token: token, expiresAt: expiresAt);
    _cached = cached;
    return cached;
  }

  /// 24 chars hex con `Random.secure()`. Hex evita los caracteres prohibidos
  /// por el backend (`:*?[]` y whitespace) sin pasar por una librería de UUID.
  static String _defaultSubGenerator() {
    final rand = Random.secure();
    final buffer = StringBuffer();
    for (var i = 0; i < 24; i++) {
      buffer.write(rand.nextInt(16).toRadixString(16));
    }
    return buffer.toString();
  }
}
