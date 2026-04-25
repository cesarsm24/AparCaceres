import 'package:flutter/foundation.dart';

import '../../parking/domain/parking_place.dart';

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
