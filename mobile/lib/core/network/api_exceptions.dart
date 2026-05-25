/// Excepciones tipadas producidas por la capa HTTP.
library;

/// Error base de comunicación con la API.
class ApiException implements Exception {
  const ApiException(this.message, {this.statusCode, this.body});

  /// Mensaje legible asociado al fallo.
  final String message;

  /// Código HTTP asociado, si el fallo procede de una respuesta del servidor.
  final int? statusCode;

  /// Cuerpo bruto de la respuesta, si está disponible.
  final String? body;

  @override
  String toString() {
    final code = statusCode == null ? '' : ' [$statusCode]';
    return 'ApiException$code: $message';
  }
}

/// Fallo de disponibilidad del backend o del transporte de red.
class ApiUnavailableException extends ApiException {
  const ApiUnavailableException(super.message, {super.statusCode, super.body});

  @override
  String toString() => 'ApiUnavailableException: $message';
}

/// Petición agotada por timeout antes de recibir respuesta útil.
class ApiTimeoutException extends ApiUnavailableException {
  const ApiTimeoutException(super.message);

  @override
  String toString() => 'ApiTimeoutException: $message';
}

/// Petición cancelada de forma explícita por el llamador.
class ApiCancelledException extends ApiException {
  const ApiCancelledException() : super('Request cancelled by caller');

  @override
  String toString() => 'ApiCancelledException';
}