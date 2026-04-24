import 'package:flutter/material.dart';

class FavoriteParking {
  const FavoriteParking({
    required this.name,
    required this.distance,
    required this.priceLabel,
    required this.freeSpots,
    required this.thumbnailIcon,
  });

  final String name;
  final String distance;
  final String priceLabel;
  final int freeSpots;
  final IconData thumbnailIcon;
}

const List<FavoriteParking> kFavorites = [
  FavoriteParking(
    name: 'Plaza Mayor',
    distance: 'A 300 m',
    priceLabel: 'Gratis',
    freeSpots: 35,
    thumbnailIcon: Icons.account_balance_outlined,
  ),
  FavoriteParking(
    name: 'Parking Obispo Goicoechea',
    distance: 'A 460 m',
    priceLabel: 'De pago',
    freeSpots: 45,
    thumbnailIcon: Icons.local_parking_outlined,
  ),
  FavoriteParking(
    name: 'Aparcamiento El Rodeo',
    distance: 'A 850 m',
    priceLabel: 'Gratis',
    freeSpots: 20,
    thumbnailIcon: Icons.directions_car_outlined,
  ),
  FavoriteParking(
    name: 'Parking Colón',
    distance: 'A 1,2 km',
    priceLabel: 'De pago',
    freeSpots: 10,
    thumbnailIcon: Icons.local_parking_outlined,
  ),
];
