import 'package:flutter/foundation.dart';
import 'package:geolocator/geolocator.dart';
import 'package:latlong2/latlong.dart';

import '../../parking/data/parking_constants.dart';

/// Servicio de ubicación activa de la aplicación.
///
/// Mantiene una posición observable con fallback dentro de Cáceres y solo
/// sustituye ese valor cuando obtiene un fix real autorizado y válido para el
/// ámbito geográfico cubierto por la app.
class LocationService {
  LocationService();

  final ValueNotifier<LatLng> position = ValueNotifier<LatLng>(
    kMockUserLocation,
  );

  bool _granted = false;
  bool _serviceEnabled = false;
  bool _outsideCaceres = false;

  bool get granted => _granted;
  bool get serviceEnabled => _serviceEnabled;
  bool get hasRealFix => _granted && _serviceEnabled;

  /// Indica que el último fix real quedó fuera del área cubierta por la app.
  bool get isOutsideCaceres => _outsideCaceres;

  /// Solicita permisos si es necesario e intenta obtener una primera posición real.
  Future<bool> ensurePosition() async {
    _serviceEnabled = await Geolocator.isLocationServiceEnabled();
    if (!_serviceEnabled) return false;

    LocationPermission permission = await Geolocator.checkPermission();
    if (permission == LocationPermission.denied) {
      permission = await Geolocator.requestPermission();
    }

    if (permission == LocationPermission.denied ||
        permission == LocationPermission.deniedForever) {
      _granted = false;
      return false;
    }

    _granted = true;
    return refresh();
  }

  /// Actualiza la posición si existe permiso y el fix pertenece a Cáceres.
  ///
  /// Los fixes fuera del área cubierta se descartan para no desplazar la UI a
  /// zonas sin catálogo; la posición anterior se conserva como fallback.
  Future<bool> refresh() async {
    if (!_granted) return false;

    try {
      final pos = await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(
          accuracy: LocationAccuracy.high,
          timeLimit: Duration(seconds: 8),
        ),
      );
      final fix = LatLng(pos.latitude, pos.longitude);

      if (!_isWithinCaceres(fix)) {
        _outsideCaceres = true;
        return false;
      }

      _outsideCaceres = false;
      position.value = fix;

      return true;
    } catch (_) {
      return false;
    }
  }

  static bool _isWithinCaceres(LatLng p) {
    return p.latitude >= 39.42 &&
        p.latitude <= 39.52 &&
        p.longitude >= -6.45 &&
        p.longitude <= -6.30;
  }
}

final LocationService locationService = LocationService();