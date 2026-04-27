import 'dart:async';
import 'dart:convert';
import 'dart:io' show SocketException;

import 'package:flutter/foundation.dart' show debugPrint, kDebugMode;
import 'package:http/http.dart' as http;

import '../config/api_config.dart';
import 'api_exceptions.dart';

/// Devuelve el JWT a inyectar en `Authorization` o `null` si la request es
/// pública. Se resuelve por petición para que el cliente pueda renovar el
/// token sin reconstruir el `ApiClient`.
typedef TokenProvider = Future<String?> Function();

/// Token cooperativo de cancelación. El caller lo crea, lo pasa a la request
/// y llama a [cancel] cuando ya no quiere el resultado (cambio de pantalla,
/// nuevos filtros, etc.). El `ApiClient` corre la request contra este
/// completer y lanza [ApiCancelledException] si gana la cancelación.
class CancelToken {
  final Completer<void> _completer = Completer<void>();

  bool get isCancelled => _completer.isCompleted;

  Future<void> get whenCancelled => _completer.future;

  void cancel() {
    if (!_completer.isCompleted) _completer.complete();
  }
}

/// Cliente HTTP de la app. Envuelve `package:http` para añadir:
///   - URL base (`ApiConfig.baseUrl`) y cabeceras por defecto.
///   - Inyección opcional de `Authorization: Bearer <jwt>` vía [TokenProvider].
///   - Timeout uniforme con [ApiConfig.requestTimeout].
///   - Mapeo de fallos a la jerarquía de [ApiException] para que las pantallas
///     reaccionen sin conocer detalles del transporte.
///   - Cancelación cooperativa con [CancelToken].
///   - Logging en modo debug de cabeceras útiles del backend (`X-Cache`,
///     `X-Total-Count`, `X-RateLimit-Remaining`, `X-Request-ID`) y latencia.
class ApiClient {
  ApiClient({http.Client? httpClient, this.tokenProvider})
    : _http = httpClient ?? http.Client();

  final http.Client _http;
  final TokenProvider? tokenProvider;

  Future<dynamic> getJson(
    String path, {
    Map<String, String>? query,
    bool requiresAuth = false,
    CancelToken? cancelToken,
  }) {
    return _send(
      method: 'GET',
      path: path,
      query: query,
      requiresAuth: requiresAuth,
      cancelToken: cancelToken,
    );
  }

  Future<dynamic> postJson(
    String path, {
    Object? body,
    Map<String, String>? query,
    bool requiresAuth = false,
    CancelToken? cancelToken,
  }) {
    return _send(
      method: 'POST',
      path: path,
      query: query,
      body: body,
      requiresAuth: requiresAuth,
      cancelToken: cancelToken,
    );
  }

  Future<dynamic> putJson(
    String path, {
    Object? body,
    Map<String, String>? query,
    bool requiresAuth = false,
    CancelToken? cancelToken,
  }) {
    return _send(
      method: 'PUT',
      path: path,
      query: query,
      body: body,
      requiresAuth: requiresAuth,
      cancelToken: cancelToken,
    );
  }

  Future<dynamic> deleteJson(
    String path, {
    Map<String, String>? query,
    bool requiresAuth = false,
    CancelToken? cancelToken,
  }) {
    return _send(
      method: 'DELETE',
      path: path,
      query: query,
      requiresAuth: requiresAuth,
      cancelToken: cancelToken,
    );
  }

  void close() => _http.close();

  Future<dynamic> _send({
    required String method,
    required String path,
    Map<String, String>? query,
    Object? body,
    bool requiresAuth = false,
    CancelToken? cancelToken,
  }) async {
    final uri = _buildUri(path, query);
    final headers = await _buildHeaders(
      requiresAuth: requiresAuth,
      hasBody: body != null,
    );
    final encodedBody = body == null ? null : jsonEncode(body);

    final stopwatch = Stopwatch()..start();
    final http.Response response;
    try {
      response = await _race(
        _dispatch(method, uri, headers, encodedBody),
        cancelToken,
      );
    } on TimeoutException {
      throw const ApiTimeoutException('Request timed out');
    } on SocketException catch (e) {
      throw ApiUnavailableException('Network unreachable: ${e.message}');
    } on http.ClientException catch (e) {
      throw ApiUnavailableException('HTTP client error: ${e.message}');
    } finally {
      stopwatch.stop();
    }

    if (kDebugMode) _logResponse(method, uri, response, stopwatch.elapsed);

    return _decode(response);
  }

  Future<http.Response> _dispatch(
    String method,
    Uri uri,
    Map<String, String> headers,
    String? encodedBody,
  ) {
    final Future<http.Response> future;
    switch (method) {
      case 'GET':
        future = _http.get(uri, headers: headers);
        break;
      case 'POST':
        future = _http.post(uri, headers: headers, body: encodedBody);
        break;
      case 'PUT':
        future = _http.put(uri, headers: headers, body: encodedBody);
        break;
      case 'DELETE':
        future = _http.delete(uri, headers: headers, body: encodedBody);
        break;
      default:
        throw ArgumentError.value(method, 'method', 'Unsupported HTTP method');
    }
    return future.timeout(ApiConfig.requestTimeout);
  }

  /// Carrera entre la request real y la cancelación cooperativa. Si gana la
  /// cancelación, propagamos `ApiCancelledException`; si gana la request,
  /// devolvemos su resultado normal.
  Future<http.Response> _race(
    Future<http.Response> request,
    CancelToken? cancelToken,
  ) {
    if (cancelToken == null) return request;
    if (cancelToken.isCancelled) {
      return Future<http.Response>.error(const ApiCancelledException());
    }
    return Future.any<http.Response>([
      request,
      cancelToken.whenCancelled.then<http.Response>(
        (_) => throw const ApiCancelledException(),
      ),
    ]);
  }

  Uri _buildUri(String path, Map<String, String>? query) {
    final normalisedPath = path.startsWith('/') ? path : '/$path';
    final base = Uri.parse('${ApiConfig.baseUrl}$normalisedPath');
    if (query == null || query.isEmpty) return base;
    return base.replace(queryParameters: {...base.queryParameters, ...query});
  }

  Future<Map<String, String>> _buildHeaders({
    required bool requiresAuth,
    required bool hasBody,
  }) async {
    final headers = <String, String>{
      'Accept': 'application/json',
      'User-Agent': ApiConfig.userAgent,
    };
    if (hasBody) headers['Content-Type'] = 'application/json';
    if (requiresAuth) {
      final token = await tokenProvider?.call();
      if (token != null && token.isNotEmpty) {
        headers['Authorization'] = 'Bearer $token';
      }
    }
    return headers;
  }

  dynamic _decode(http.Response response) {
    final status = response.statusCode;
    if (status >= 200 && status < 300) {
      if (response.body.isEmpty) return null;
      try {
        return jsonDecode(response.body);
      } on FormatException catch (e) {
        throw ApiException(
          'Malformed JSON response: ${e.message}',
          statusCode: status,
          body: response.body,
        );
      }
    }
    final message = _extractErrorMessage(response.body) ?? 'HTTP $status';
    if (status >= 500) {
      throw ApiUnavailableException(
        message,
        statusCode: status,
        body: response.body,
      );
    }
    throw ApiException(message, statusCode: status, body: response.body);
  }

  /// FastAPI devuelve errores como `{"detail": "..."}`. Si el cuerpo no encaja
  /// con ese shape devolvemos `null` y dejamos que el caller use el genérico.
  String? _extractErrorMessage(String body) {
    if (body.isEmpty) return null;
    try {
      final decoded = jsonDecode(body);
      if (decoded is Map<String, dynamic>) {
        final detail = decoded['detail'];
        if (detail is String) return detail;
      }
    } on FormatException {
      // Cuerpo no JSON (HTML de un proxy, texto plano de un 502): lo dejamos
      // pasar para usar el mensaje genérico.
    }
    return null;
  }

  void _logResponse(
    String method,
    Uri uri,
    http.Response response,
    Duration elapsed,
  ) {
    final cache = response.headers['x-cache'];
    final total = response.headers['x-total-count'];
    final rate = response.headers['x-ratelimit-remaining'];
    final reqId = response.headers['x-request-id'];
    final tags = <String>[
      if (cache != null) 'cache=$cache',
      if (total != null) 'total=$total',
      if (rate != null) 'rate=$rate',
      if (reqId != null) 'req=$reqId',
    ];
    final suffix = tags.isEmpty ? '' : ' ${tags.join(' ')}';
    debugPrint(
      '[api] $method ${uri.path} -> ${response.statusCode} '
      'in ${elapsed.inMilliseconds}ms$suffix',
    );
  }
}
