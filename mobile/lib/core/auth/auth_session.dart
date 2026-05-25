import 'dart:async';
import 'dart:math';

import 'package:shared_preferences/shared_preferences.dart';

import '../network/api_client.dart';
import '../network/api_exceptions.dart';

/// JWT persistido con su fecha de expiración para anticipar renovaciones.
class _CachedToken {
  const _CachedToken({required this.token, required this.expiresAt});

  final String token;
  final DateTime expiresAt;
}

/// Gestiona la identidad opaca del dispositivo y su token de sesión.
///
/// La identidad (`sub`) se genera una vez, se persiste localmente y se usa para
/// solicitar un JWT interno al backend. El token se reutiliza mientras siga
/// dentro de la ventana de validez y se renueva antes de expirar para evitar
/// respuestas 401 durante el uso normal de la aplicación.
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

  /// Devuelve un JWT válido para adjuntar a una petición autenticada.
  ///
  /// Las renovaciones concurrentes comparten la misma operación en vuelo para
  /// evitar emisiones duplicadas contra `/auth/session`.
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

  /// Elimina la identidad local y el token persistido.
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

  /// Genera un identificador hexadecimal compatible con las restricciones del backend.
  static String _defaultSubGenerator() {
    final rand = Random.secure();
    final buffer = StringBuffer();

    for (var i = 0; i < 24; i++) {
      buffer.write(rand.nextInt(16).toRadixString(16));
    }

    return buffer.toString();
  }
}