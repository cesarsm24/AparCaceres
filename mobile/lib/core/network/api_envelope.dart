import 'api_exceptions.dart';

/// Extrae los `items` de una respuesta del backend.
///
/// El backend usa dos formatos según el endpoint:
///   - Listados paginados (`/parkings`, `/parkings/nearby`, `/parkings/in-bounds`):
///     envelope `{items, total, limit, offset, truncated, facets}`.
///   - Endpoints sencillos (`/users/me/favorites`, `/parkings/categories`):
///     lista plana en la raíz.
///
/// Este helper acepta ambos shapes para que el caller no tenga que
/// distinguirlos: si recibe una `List`, la mapea directa; si recibe un
/// `Map`, busca `items`. Cualquier otra cosa lanza `ApiException` para
/// abortar pronto y no propagar tipos inválidos a la capa de dominio.
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
