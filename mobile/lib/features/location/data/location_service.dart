import 'package:flutter/foundation.dart';
import 'package:geolocator/geolocator.dart';
import 'package:latlong2/latlong.dart';

import '../../parking/data/parking_constants.dart';

class LocationService {
  LocationService();

  final ValueNotifier<LatLng> position = ValueNotifier<LatLng>(
    kMockUserLocation,
  );
  bool _granted = false;
  bool _serviceEnabled = false;

  bool get granted => _granted;
  bool get serviceEnabled => _serviceEnabled;
  bool get hasRealFix => _granted && _serviceEnabled;

  /// Requests permission (if needed) and tries to get a first fix.
  /// Returns true if a real position was stored, false on any failure
  /// (in which case the value falls back to [kMockUserLocation]).
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

  /// Re-fetches the device position. Requires permission to have already
  /// been granted; otherwise no-op and returns false. Fixes outside the
  /// Cáceres bounding box are discarded and the fallback is kept — that
  /// way an emulator pretending to be in Mountain View doesn't leak into
  /// the UI, but a real device in Cáceres still gets a real location.
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
      if (!_isWithinCaceres(fix)) return false;
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
