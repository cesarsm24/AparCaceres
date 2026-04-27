import 'package:latlong2/latlong.dart';

enum ParkingCategory {
  parking,
  paidParking,
  streetLine,
  streetBattery,
  blueZone,
  accessible,
  motorbike,
  bicycle,
  loading,
}

enum ParkingVehicleType { car, motorbike, bike }

enum ParkingRegulation { free, paid, blueZone, loading, reserved }

enum ParkingGeometryType { point, polygon, lineString }

/// Serialización al vocabulario wire del backend. Se mantiene aquí para que
/// quede al lado de los `_*FromWire` y cualquier cambio en el contrato se
/// vea en un único archivo.
extension ParkingCategoryWire on ParkingCategory {
  String get wire => switch (this) {
    ParkingCategory.parking => 'parking',
    ParkingCategory.paidParking => 'paid_parking',
    ParkingCategory.streetLine => 'street_line',
    ParkingCategory.streetBattery => 'street_battery',
    ParkingCategory.blueZone => 'blue_zone',
    ParkingCategory.accessible => 'accessible',
    ParkingCategory.motorbike => 'motorbike',
    ParkingCategory.bicycle => 'bicycle',
    ParkingCategory.loading => 'loading',
  };
}

extension ParkingVehicleTypeWire on ParkingVehicleType {
  String get wire => switch (this) {
    ParkingVehicleType.car => 'car',
    ParkingVehicleType.motorbike => 'motorbike',
    ParkingVehicleType.bike => 'bike',
  };
}

extension ParkingRegulationWire on ParkingRegulation {
  String get wire => switch (this) {
    ParkingRegulation.free => 'free',
    ParkingRegulation.paid => 'paid',
    ParkingRegulation.blueZone => 'blue_zone',
    ParkingRegulation.loading => 'loading',
    ParkingRegulation.reserved => 'reserved',
  };
}

/// Decodifica un valor wire del backend en su `ParkingCategory`. Reutiliza el
/// mismo switch que `ParkingPlace.fromJson` para que el contrato quede en un
/// único sitio. Devuelve `ParkingCategory.parking` ante valores desconocidos
/// para no romper la UI si el backend introduce categorías nuevas.
ParkingCategory parkingCategoryFromWire(String? value) => switch (value) {
  'paid_parking' => ParkingCategory.paidParking,
  'street_line' => ParkingCategory.streetLine,
  'street_battery' => ParkingCategory.streetBattery,
  'blue_zone' => ParkingCategory.blueZone,
  'accessible' => ParkingCategory.accessible,
  'motorbike' => ParkingCategory.motorbike,
  'bicycle' => ParkingCategory.bicycle,
  'loading' => ParkingCategory.loading,
  _ => ParkingCategory.parking,
};

class ParkingPlace {
  const ParkingPlace({
    required this.id,
    required this.name,
    required this.category,
    required this.vehicleType,
    required this.regulation,
    required this.geometryType,
    required this.latitude,
    required this.longitude,
    required this.polygonRings,
    required this.linePoints,
    this.totalSpaces,
    this.streetName,
    this.streetType,
    this.district,
    this.neighborhood,
    this.sourceDataset,
    this.imageUrl,
    this.urlFicha,
    this.urlVia,
    this.management,
  });

  final String id;
  final String name;
  final ParkingCategory category;
  final ParkingVehicleType vehicleType;
  final ParkingRegulation regulation;
  final ParkingGeometryType geometryType;
  final double latitude;
  final double longitude;
  final List<List<LatLng>> polygonRings;
  final List<LatLng> linePoints;
  final int? totalSpaces;
  final String? streetName;
  final String? streetType;
  final String? district;
  final String? neighborhood;
  final String? sourceDataset;
  final String? imageUrl;
  final String? urlFicha;
  final String? urlVia;
  final String? management;

  LatLng get position => LatLng(latitude, longitude);

  String get displayName {
    if (name.trim().isNotEmpty) return name;
    final street = streetName?.trim();
    if (street != null && street.isNotEmpty) return street;
    return 'Ubicacion sin nombre';
  }

  String get addressLabel {
    final parts = [
      if (streetType != null && streetType!.trim().isNotEmpty) streetType,
      if (streetName != null && streetName!.trim().isNotEmpty) streetName,
    ];
    if (parts.isNotEmpty) return parts.join(' ');
    return neighborhood ?? district ?? 'Caceres';
  }

  factory ParkingPlace.fromJson(Map<String, dynamic> json) {
    final geometryType = _geometryTypeFromWire(json['geometryType'] as String?);
    final latitude = _toDouble(json['latitude']);
    final longitude = _toDouble(json['longitude']);
    final coordinates = json['coordinates'];

    return ParkingPlace(
      id: json['id'] as String,
      name: json['name'] as String? ?? '',
      category: _categoryFromWire(json['category'] as String?),
      vehicleType: _vehicleTypeFromWire(json['vehicleType'] as String?),
      regulation: _regulationFromWire(json['regulation'] as String?),
      geometryType: geometryType,
      latitude: latitude,
      longitude: longitude,
      polygonRings: geometryType == ParkingGeometryType.polygon
          ? _parsePolygon(coordinates)
          : const [],
      linePoints: geometryType == ParkingGeometryType.lineString
          ? _parseLineString(coordinates)
          : const [],
      totalSpaces: _toNullableInt(json['totalSpaces']),
      streetName: json['streetName'] as String?,
      streetType: json['streetType'] as String?,
      district: json['district'] as String?,
      neighborhood: json['neighborhood'] as String?,
      sourceDataset: json['sourceDataset'] as String?,
      imageUrl: json['imageUrl'] as String?,
      urlFicha: json['urlFicha'] as String?,
      urlVia: json['urlVia'] as String?,
      management: json['management'] as String?,
    );
  }

  static ParkingCategory _categoryFromWire(String? value) {
    return switch (value) {
      'paid_parking' => ParkingCategory.paidParking,
      'street_line' => ParkingCategory.streetLine,
      'street_battery' => ParkingCategory.streetBattery,
      'blue_zone' => ParkingCategory.blueZone,
      'accessible' => ParkingCategory.accessible,
      'motorbike' => ParkingCategory.motorbike,
      'bicycle' => ParkingCategory.bicycle,
      'loading' => ParkingCategory.loading,
      _ => ParkingCategory.parking,
    };
  }

  static ParkingVehicleType _vehicleTypeFromWire(String? value) {
    return switch (value) {
      'motorbike' => ParkingVehicleType.motorbike,
      'bike' => ParkingVehicleType.bike,
      _ => ParkingVehicleType.car,
    };
  }

  static ParkingRegulation _regulationFromWire(String? value) {
    return switch (value) {
      'paid' => ParkingRegulation.paid,
      'blue_zone' => ParkingRegulation.blueZone,
      'loading' => ParkingRegulation.loading,
      'reserved' => ParkingRegulation.reserved,
      _ => ParkingRegulation.free,
    };
  }

  static ParkingGeometryType _geometryTypeFromWire(String? value) {
    return switch (value) {
      'polygon' => ParkingGeometryType.polygon,
      'line_string' => ParkingGeometryType.lineString,
      _ => ParkingGeometryType.point,
    };
  }

  static double _toDouble(Object? value) {
    if (value is num) return value.toDouble();
    if (value is String) return double.parse(value);
    throw FormatException('Invalid coordinate value: $value');
  }

  static int? _toNullableInt(Object? value) {
    if (value == null) return null;
    if (value is int) return value;
    if (value is num) return value.round();
    if (value is String) return int.tryParse(value);
    return null;
  }

  static List<List<LatLng>> _parsePolygon(Object? coordinates) {
    if (coordinates is! List) return const [];
    return coordinates
        .map(_parseLineString)
        .where((ring) => ring.length >= 3)
        .toList();
  }

  static List<LatLng> _parseLineString(Object? coordinates) {
    if (coordinates is! List) return const [];
    return coordinates.map(_parseCoordinate).whereType<LatLng>().toList();
  }

  static LatLng? _parseCoordinate(Object? coordinate) {
    if (coordinate is! List || coordinate.length < 2) return null;
    return LatLng(_toDouble(coordinate[1]), _toDouble(coordinate[0]));
  }
}
