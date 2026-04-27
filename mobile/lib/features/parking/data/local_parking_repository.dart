import 'dart:convert';

import 'package:flutter/services.dart';
import 'package:latlong2/latlong.dart';

import '../../../core/network/api_client.dart';
import '../domain/parking_place.dart';
import '../domain/parking_query.dart';
import '../domain/parking_repository.dart';
import 'favorites_store.dart';

class LocalParkingRepository implements ParkingRepository {
  LocalParkingRepository({AssetBundle? bundle, FavoritesStore? favorites})
    : _bundle = bundle ?? rootBundle,
      _favorites = favorites ?? favoritesStore;

  static const String _fixturePath = 'assets/mock/parking_places.json';

  final AssetBundle _bundle;
  final FavoritesStore _favorites;
  List<ParkingPlace>? _cache;

  @override
  Future<List<ParkingPlace>> getNearby(
    ParkingQuery query, {
    CancelToken? cancelToken,
  }) async {
    final places = await _loadPlaces();
    final distance = const Distance();
    final filtered = places.where((place) {
      if (query.vehicleTypes.isNotEmpty &&
          !query.vehicleTypes.contains(place.vehicleType)) {
        return false;
      }
      if (query.categories.isNotEmpty &&
          !query.categories.contains(place.category)) {
        return false;
      }
      if (query.regulations.isNotEmpty &&
          !query.regulations.contains(place.regulation)) {
        return false;
      }
      if (query.minSpaces > 0 &&
          (place.totalSpaces == null || place.totalSpaces! < query.minSpaces)) {
        return false;
      }
      if (query.center != null) {
        final meters = distance(query.center!, place.position);
        if (meters > query.radiusMeters) return false;
      }
      return true;
    }).toList();

    if (query.center != null) {
      filtered.sort(
        (a, b) => distance(
          query.center!,
          a.position,
        ).compareTo(distance(query.center!, b.position)),
      );
    }

    return filtered;
  }

  @override
  Future<ParkingPlace?> getById(String id) async {
    final places = await _loadPlaces();
    for (final place in places) {
      if (place.id == id) return place;
    }
    return null;
  }

  @override
  Future<List<ParkingCategory>> getCategories() async {
    final places = await _loadPlaces();
    return places.map((p) => p.category).toSet().toList()
      ..sort((a, b) => a.index.compareTo(b.index));
  }

  @override
  Future<List<ParkingPlace>> getFavorites() async {
    final places = await _loadPlaces();
    final ids = _favorites.ids;
    return places.where((place) => ids.contains(place.id)).toList();
  }

  Future<List<ParkingPlace>> _loadPlaces() async {
    final cached = _cache;
    if (cached != null) return cached;

    final raw = await _bundle.loadString(_fixturePath);
    final decoded = jsonDecode(raw) as Map<String, dynamic>;
    final features = decoded['places'] as List<dynamic>;
    final places = features
        .map((json) => ParkingPlace.fromJson(json as Map<String, dynamic>))
        .toList();
    _cache = places;
    return places;
  }
}
