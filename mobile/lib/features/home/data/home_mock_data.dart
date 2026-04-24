import 'package:flutter/material.dart';

class ParkingSuggestion {
  const ParkingSuggestion({
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

class NearbySummary {
  const NearbySummary({
    required this.radiusMeters,
    required this.availableParkings,
    required this.freeSpots,
    required this.occupancy,
  });

  final int radiusMeters;
  final int availableParkings;
  final int freeSpots;
  final double occupancy;
}

const NearbySummary kNearbySummary = NearbySummary(
  radiusMeters: 500,
  availableParkings: 6,
  freeSpots: 213,
  occupancy: 0.7,
);

const List<ParkingSuggestion> kSuggestions = [
  ParkingSuggestion(
    name: 'Plaza Mayor',
    distance: 'A 300 m',
    priceLabel: 'Gratis',
    freeSpots: 35,
    thumbnailIcon: Icons.account_balance_outlined,
  ),
  ParkingSuggestion(
    name: 'Parking Obispo Galarza',
    distance: 'A 450 m',
    priceLabel: '1,20 €/h',
    freeSpots: 48,
    thumbnailIcon: Icons.local_parking_outlined,
  ),
  ParkingSuggestion(
    name: 'Paseo de Cánovas',
    distance: 'A 800 m',
    priceLabel: 'Gratis',
    freeSpots: 22,
    thumbnailIcon: Icons.park_outlined,
  ),
];
