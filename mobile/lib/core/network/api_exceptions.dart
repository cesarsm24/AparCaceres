/// Excepciones tipadas que produce `ApiClient`.
///
/// Mantenerlas separadas del `ApiClient` evita que las pantallas dependan
/// del cliente HTTP concreto: capturan la jerarquía aquí definida y
/// reaccionan según el caso (estado vacío, retry, snackbar de "servicio no
/// disponible", etc.).
library;

/// Raíz de las excepciones de red. Las pantallas que solo quieran reaccionar
/// con un mensaje genérico pueden capturar `ApiException`.
class ApiException implements Exception {
  const ApiException(this.message, {this.statusCode, this.body});

  /// Mensaje legible. Nunca `null`.
  final String message;

  /// Código HTTP cuando aplica. `null` para fallos previos (DNS, socket).
  final int? statusCode;

  /// Cuerpo en bruto de la respuesta cuando estuvo disponible. Se evita
  /// almacenar respuestas grandes en memoria: solo se conserva si el caller
  /// lo va a mostrar o loggear.
  final String? body;

  @override
  String toString() {
    final code = statusCode == null ? '' : ' [$statusCode]';
    return 'ApiException$code: $message';
  }
}

/// Backend inalcanzable: error de DNS, conexión rechazada, 5xx o el cliente
/// HTTP cayó antes de leer el cuerpo. La UI debe mostrar un estado de
/// "servicio no disponible" con opción de reintentar.
class ApiUnavailableException extends ApiException {
  const ApiUnavailableException(super.message, {super.statusCode, super.body});

  @override
  String toString() => 'ApiUnavailableException: $message';
}

/// La request superó `ApiConfig.requestTimeout` sin recibir respuesta.
/// Tratado como un caso particular de "no disponible" porque el síntoma es
/// equivalente desde el punto de vista del usuario.
class ApiTimeoutException extends ApiUnavailableException {
  const ApiTimeoutException(super.message);

  @override
  String toString() => 'ApiTimeoutException: $message';
}

/// La request fue cancelada explícitamente por el caller (cambio de filtros,
/// cambio de pantalla, etc.). No es un error que deba mostrarse al usuario.
class ApiCancelledException extends ApiException {
  const ApiCancelledException() : super('Request cancelled by caller');

  @override
  String toString() => 'ApiCancelledException';
}
