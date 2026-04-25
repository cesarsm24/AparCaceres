import 'package:flutter/material.dart';
import 'package:latlong2/latlong.dart';

import '../../../shared/constants/app_strings.dart';
import '../../../shared/widgets/app_top_bar.dart';
import '../../../shared/widgets/section_title.dart';
import '../../../theme/app_colors.dart';
import '../../../theme/app_spacing.dart';
import '../../location_picker/domain/place_suggestion.dart';
import '../../location_picker/presentation/location_picker_screen.dart';
import '../../map/presentation/widgets/filters_drawer.dart';
import '../../parking/data/parking_constants.dart';
import '../../parking/data/parking_repository_provider.dart';
import '../../parking/domain/parking_place.dart';
import '../../parking/domain/parking_query.dart';
import '../../parking_detail/presentation/parking_detail_screen.dart';
import '../../search/presentation/search_screen.dart';
import 'widgets/home_search_bar.dart';
import 'widgets/location_actions.dart';
import 'widgets/quick_access_row.dart';
import 'widgets/suggestion_tile.dart';

class HomeScreen extends StatelessWidget {
  const HomeScreen({super.key, required this.onOpenMap});

  final ValueChanged<MapFilters> onOpenMap;

  static const int _radiusMeters = 1000;

  Future<void> _pickLocation(BuildContext context) async {
    final suggestion = await Navigator.of(context).push<PlaceSuggestion>(
      MaterialPageRoute(builder: (_) => const LocationPickerScreen()),
    );
    if (suggestion == null) return;
    onOpenMap(
      MapFilters.atLocation(suggestion.position, label: suggestion.shortName),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      color: AppColors.pageBackground,
      child: Column(
        children: [
          AppTopBar(
            trailing: IconButton(
              onPressed: () {},
              icon: const Icon(
                Icons.notifications_none_rounded,
                color: AppColors.textOnPrimary,
              ),
            ),
          ),
          Expanded(
            child: FutureBuilder<List<ParkingPlace>>(
              future: parkingRepository.getNearby(
                const ParkingQuery(
                  center: kMockUserLocation,
                  radiusMeters: _radiusMeters,
                ),
              ),
              builder: (context, snapshot) {
                final places = snapshot.data ?? const <ParkingPlace>[];
                final suggestions = places.take(4).toList();
                return ListView(
                  padding: const EdgeInsets.fromLTRB(
                    AppSpacing.horizontalPadding,
                    AppSpacing.md,
                    AppSpacing.horizontalPadding,
                    AppSpacing.lg,
                  ),
                  children: [
                    HomeSearchBar(
                      onTap: () => Navigator.of(context).push(
                        MaterialPageRoute(
                          builder: (_) => const SearchScreen(),
                        ),
                      ),
                    ),
                    const SizedBox(height: AppSpacing.lg),
                    const SectionTitle(AppStrings.sectionQuickAccess),
                    const SizedBox(height: AppSpacing.md),
                    QuickAccessRow(
                      onVehicleSelected: (vehicleType) =>
                          onOpenMap(MapFilters.forVehicle(vehicleType)),
                      onAccessibleSelected: () =>
                          onOpenMap(MapFilters.forAccessible()),
                    ),
                    const SizedBox(height: AppSpacing.lg),
                    LocationActions(
                      onUseCurrent: () => onOpenMap(MapFilters()),
                      onPickLocation: () => _pickLocation(context),
                    ),
                    const SizedBox(height: AppSpacing.lg),
                    const SectionTitle(AppStrings.sectionSuggestions),
                    const SizedBox(height: AppSpacing.md),
                    if (snapshot.connectionState == ConnectionState.waiting)
                      const _LoadingState()
                    else if (suggestions.isEmpty)
                      const _EmptyState()
                    else
                      ...suggestions.map(
                        (place) => Padding(
                          padding: const EdgeInsets.only(bottom: AppSpacing.md),
                          child: SuggestionTile(
                            place: place,
                            distanceMeters: const Distance()(
                              kMockUserLocation,
                              place.position,
                            ),
                            onTap: () => Navigator.of(context).push(
                              MaterialPageRoute(
                                builder: (_) =>
                                    ParkingDetailScreen(place: place),
                              ),
                            ),
                          ),
                        ),
                      ),
                  ],
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}

class _LoadingState extends StatelessWidget {
  const _LoadingState();

  @override
  Widget build(BuildContext context) {
    return const Padding(
      padding: EdgeInsets.symmetric(vertical: AppSpacing.lg),
      child: Center(child: CircularProgressIndicator()),
    );
  }
}

class _EmptyState extends StatelessWidget {
  const _EmptyState();

  @override
  Widget build(BuildContext context) {
    return const Padding(
      padding: EdgeInsets.symmetric(vertical: AppSpacing.lg),
      child: Text(
        'No hay resultados cerca con los datos actuales.',
        style: TextStyle(color: AppColors.textSecondary),
      ),
    );
  }
}
