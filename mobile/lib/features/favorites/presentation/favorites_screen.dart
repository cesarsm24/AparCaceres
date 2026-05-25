import 'package:flutter/material.dart';
import 'package:latlong2/latlong.dart';

import '../../../shared/constants/app_strings.dart';
import '../../../shared/widgets/api_error_state.dart';
import '../../../shared/widgets/app_top_bar.dart';
import '../../../theme/app_colors.dart';
import '../../../theme/app_spacing.dart';
import '../../location/data/location_service.dart';
import '../../parking/data/favorites_store.dart';
import '../../parking/data/parking_repository_provider.dart';
import '../../parking/domain/parking_place.dart';
import '../../parking_detail/presentation/parking_detail_screen.dart';
import 'widgets/favorite_tile.dart';

/// Pantalla de favoritos del usuario.
///
/// Obtiene la lista persistida en backend, la mantiene sincronizada con el
/// estado local de favoritos y permite abrir el detalle de cada aparcamiento.
class FavoritesScreen extends StatefulWidget {
  const FavoritesScreen({super.key});

  @override
  State<FavoritesScreen> createState() => _FavoritesScreenState();
}

class _FavoritesScreenState extends State<FavoritesScreen> {
  late Future<List<ParkingPlace>> _favoritesFuture;

  @override
  void initState() {
    super.initState();
    _favoritesFuture = parkingRepository.getFavorites();
    favoritesStore.addListener(_reloadFavorites);
  }

  @override
  void dispose() {
    favoritesStore.removeListener(_reloadFavorites);
    super.dispose();
  }

  void _reloadFavorites() {
    if (!mounted) return;

    setState(() {
      _favoritesFuture = parkingRepository.getFavorites();
    });
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      color: AppColors.pageBackground,
      child: Column(
        children: [
          const AppTopBar(),
          Expanded(
            child: FutureBuilder<List<ParkingPlace>>(
              future: _favoritesFuture,
              builder: (context, snapshot) {
                if (snapshot.connectionState == ConnectionState.waiting) {
                  return const Center(child: CircularProgressIndicator());
                }

                if (snapshot.hasError) {
                  return ApiErrorState(
                    error: snapshot.error!,
                    onRetry: _reloadFavorites,
                  );
                }

                final favorites = snapshot.data ?? const <ParkingPlace>[];

                if (favorites.isEmpty) {
                  return const Center(
                    child: Text(
                      AppStrings.favoritesEmpty,
                      style: TextStyle(color: AppColors.textSecondary),
                    ),
                  );
                }

                return ListView.separated(
                  padding: const EdgeInsets.fromLTRB(
                    AppSpacing.horizontalPadding,
                    AppSpacing.md,
                    AppSpacing.horizontalPadding,
                    AppSpacing.lg,
                  ),
                  itemCount: favorites.length,
                  separatorBuilder: (_, _) =>
                  const SizedBox(height: AppSpacing.md),
                  itemBuilder: (_, i) {
                    final place = favorites[i];

                    return FavoriteTile(
                      place: place,
                      distanceMeters: const Distance()(
                        locationService.position.value,
                        place.position,
                      ),
                      onTap: () => Navigator.of(context).push(
                        MaterialPageRoute(
                          builder: (_) => ParkingDetailScreen(place: place),
                        ),
                      ),
                      onToggleFavorite: () => favoritesStore.toggle(place.id),
                    );
                  },
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}
