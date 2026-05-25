import 'package:latlong2/latlong.dart';

/// Coordenadas base usadas como centro inicial y fallback de ubicación.
///
/// El punto corresponde al centro aproximado de Cáceres y permite que la app
/// funcione aunque todavía no exista un fix real del dispositivo.
const LatLng kCaceresCenter = LatLng(39.4753, -6.3724);
const LatLng kMockUserLocation = LatLng(39.4753, -6.3724);