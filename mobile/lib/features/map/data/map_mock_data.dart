import 'package:latlong2/latlong.dart';

class ParkingMarker {
  const ParkingMarker({
    required this.id,
    required this.name,
    required this.position,
    required this.isPaid,
    required this.freeSpots,
  });

  final String id;
  final String name;
  final LatLng position;
  final bool isPaid;
  final int freeSpots;
}

const LatLng kCaceresCenter = LatLng(39.4753, -6.3724);

const List<ParkingMarker> kParkingMarkers = [
  ParkingMarker(
    id: 'plaza-mayor',
    name: 'Plaza Mayor',
    position: LatLng(39.4746, -6.3723),
    isPaid: false,
    freeSpots: 18,
  ),
  ParkingMarker(
    id: 'obispo-galarza',
    name: 'Parking Obispo Galarza',
    position: LatLng(39.4762, -6.3710),
    isPaid: true,
    freeSpots: 42,
  ),
  ParkingMarker(
    id: 'canovas',
    name: 'Paseo de Cánovas',
    position: LatLng(39.4718, -6.3735),
    isPaid: false,
    freeSpots: 27,
  ),
  ParkingMarker(
    id: 'el-rodeo',
    name: 'Aparcamiento El Rodeo',
    position: LatLng(39.4775, -6.3755),
    isPaid: false,
    freeSpots: 64,
  ),
  ParkingMarker(
    id: 'obispo-goicoechea',
    name: 'Parking Obispo Goicoechea',
    position: LatLng(39.4738, -6.3698),
    isPaid: true,
    freeSpots: 45,
  ),
  ParkingMarker(
    id: 'colon',
    name: 'Parking Colón',
    position: LatLng(39.4705, -6.3702),
    isPaid: true,
    freeSpots: 31,
  ),
];

const LatLng kUserLocation = LatLng(39.4753, -6.3724);
