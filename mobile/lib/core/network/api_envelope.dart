import 'api_exceptions.dart';

/// Extrae una lista tipada desde una respuesta JSON del backend.
///
/// Acepta tanto listas planas como envelopes paginados con campo `items`.
/// Cualquier forma inesperada se rechaza con `ApiException` para impedir que
/// tipos inválidos alcancen la capa de dominio.
List<T> parseListResponse<T>(
    Object? json,
    T Function(Map<String, dynamic> item) fromItem,
    ) {
  if (json is List) {
    return _mapList(json, fromItem);
  }

  if (json is Map<String, dynamic>) {
    final items = json['items'];
    if (items is List) {
      return _mapList(items, fromItem);
    }
  }

  throw ApiException('Unexpected list shape: ${json.runtimeType}');
}

List<T> _mapList<T>(
    List<dynamic> source,
    T Function(Map<String, dynamic> item) fromItem,
    ) {
  final result = <T>[];

  for (final raw in source) {
    if (raw is Map<String, dynamic>) {
      result.add(fromItem(raw));
    } else if (raw is Map) {
      result.add(fromItem(Map<String, dynamic>.from(raw)));
    } else {
      throw ApiException('Item is not a JSON object: ${raw.runtimeType}');
    }
  }

  return result;
}