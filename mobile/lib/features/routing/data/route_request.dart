import 'package:flutter/foundation.dart';

import '../../parking/domain/parking_place.dart';

/// Canal simple para solicitar una ruta desde otras pantallas.
///
/// El detalle publica el aparcamiento destino y el mapa consume la petición al
/// recibirla, evitando acoplar navegación y cálculo de ruta entre pantallas.
class RouteRequestNotifier extends ChangeNotifier {
  ParkingPlace? _request;

  ParkingPlace? get request => _request;

  void requestRoute(ParkingPlace place) {
    _request = place;
    notifyListeners();
  }

  void consume() {
    _request = null;
  }
}

final RouteRequestNotifier routeRequest = RouteRequestNotifier();