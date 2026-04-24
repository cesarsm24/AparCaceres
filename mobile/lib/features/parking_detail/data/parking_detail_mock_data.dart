import 'package:flutter/material.dart';

class ParkingDetail {
  const ParkingDetail({
    required this.name,
    required this.address,
    required this.type,
    required this.isPaid,
    required this.schedule,
    required this.rate,
    required this.freeSpots,
    required this.totalSpots,
    required this.services,
    required this.headerIcon,
  });

  final String name;
  final String address;
  final String type;
  final bool isPaid;
  final String schedule;
  final String rate;
  final int freeSpots;
  final int totalSpots;
  final List<IconData> services;
  final IconData headerIcon;
}

const ParkingDetail kParkingDetailSample = ParkingDetail(
  name: 'Parking Obispo Goicoechea',
  address: 'Calle Obispo Goicoechea, s/n, 10001 Cáceres',
  type: 'De pago',
  isPaid: true,
  schedule: '24 horas',
  rate: '1,20 €/hora (máx. 10 €/día)',
  freeSpots: 45,
  totalSpots: 120,
  services: [
    Icons.house_outlined,
    Icons.accessible,
    Icons.videocam_outlined,
    Icons.ev_station_outlined,
  ],
  headerIcon: Icons.local_parking_outlined,
);
