import '../../parking/domain/parking_place.dart';

/// Busca aparcamientos por texto en campos visibles de la UI.
///
/// La comparación es case-insensitive y accent-insensitive para que búsquedas
/// como `caceres`, `politecnica` o `dalia` funcionen aunque los datos lleven
/// mayúsculas o tildes.
List<ParkingPlace> searchParking(List<ParkingPlace> places, String query) {
  final normalized = _normalize(query);

  if (normalized.isEmpty) return const <ParkingPlace>[];

  return places.where((place) => _matches(place, normalized)).toList();
}

bool _matches(ParkingPlace place, String normalizedQuery) {
  final haystacks = <String?>[
    place.name,
    place.streetName,
    place.streetType,
    place.district,
    place.neighborhood,
  ];

  for (final field in haystacks) {
    if (field == null || field.isEmpty) continue;
    if (_normalize(field).contains(normalizedQuery)) return true;
  }

  return false;
}

String _normalize(String value) {
  final lower = value.toLowerCase().trim();
  const accents = {
    'á': 'a',
    'à': 'a',
    'ä': 'a',
    'â': 'a',
    'é': 'e',
    'è': 'e',
    'ë': 'e',
    'ê': 'e',
    'í': 'i',
    'ì': 'i',
    'ï': 'i',
    'î': 'i',
    'ó': 'o',
    'ò': 'o',
    'ö': 'o',
    'ô': 'o',
    'ú': 'u',
    'ù': 'u',
    'ü': 'u',
    'û': 'u',
    'ñ': 'n',
    'ç': 'c',
  };

  final buffer = StringBuffer();

  for (final rune in lower.runes) {
    final ch = String.fromCharCode(rune);
    buffer.write(accents[ch] ?? ch);
  }

  return buffer.toString();
}