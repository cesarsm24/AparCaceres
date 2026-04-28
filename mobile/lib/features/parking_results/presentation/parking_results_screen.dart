import 'package:flutter/material.dart';
import 'package:latlong2/latlong.dart';

import '../../../shared/constants/app_strings.dart';
import '../../../shared/widgets/api_error_state.dart';
import '../../../shared/widgets/app_top_bar.dart';
import '../../../theme/app_colors.dart';
import '../../../theme/app_spacing.dart';
import '../../location/data/location_service.dart';
import '../../map/presentation/widgets/filters_drawer.dart';
import '../../parking/data/parking_repository_provider.dart';
import '../../parking/domain/parking_place.dart';
import '../../parking_detail/presentation/parking_detail_screen.dart';
import 'widgets/parking_result_tile.dart';
import 'widgets/results_header.dart';

/// Pantalla de listado de resultados para los filtros activos del mapa.
///
/// Permite revisar todos los aparcamientos encontrados, cambiar el criterio de
/// ordenación y abrir el detalle de cualquier elemento.
class ParkingResultsScreen extends StatefulWidget {
  const ParkingResultsScreen({super.key, required this.filters});

  final MapFilters filters;

  @override
  State<ParkingResultsScreen> createState() => _ParkingResultsScreenState();
}

class _ParkingResultsScreenState extends State<ParkingResultsScreen> {
  late Future<List<ParkingPlace>> _placesFuture;
  ResultsSortMode _sort = ResultsSortMode.distance;

  @override
  void initState() {
    super.initState();
    _placesFuture = parkingRepository.getNearby(widget.filters.toQuery());
  }

  List<ParkingPlace> _sortPlaces(List<ParkingPlace> places) {
    switch (_sort) {
      case ResultsSortMode.distance:
        return places;

      case ResultsSortMode.name:
        final sorted = [...places]
          ..sort(
                (a, b) => a.displayName.toLowerCase().compareTo(
              b.displayName.toLowerCase(),
            ),
          );
        return sorted;

      case ResultsSortMode.spaces:
        final sorted = [...places]
          ..sort((a, b) {
            final aSpaces = a.totalSpaces ?? -1;
            final bSpaces = b.totalSpaces ?? -1;
            return bSpaces.compareTo(aSpaces);
          });
        return sorted;
    }
  }

  Future<List<ParkingPlace>> _reloadPlaces() {
    return parkingRepository.getNearby(widget.filters.toQuery());
  }

  @override
  Widget build(BuildContext context) {
    final origin = widget.filters.center ?? locationService.position.value;

    return Scaffold(
      backgroundColor: AppColors.pageBackground,
      body: Column(
        children: [
          AppTopBar(
            leading: IconButton(
              onPressed: () => Navigator.of(context).maybePop(),
              icon: const Icon(
                Icons.chevron_left,
                color: AppColors.textOnPrimary,
                size: 28,
              ),
            ),
          ),
          Expanded(
            child: FutureBuilder<List<ParkingPlace>>(
              future: _placesFuture,
              builder: (context, snapshot) {
                if (snapshot.connectionState == ConnectionState.waiting) {
                  return const Center(child: CircularProgressIndicator());
                }

                if (snapshot.hasError) {
                  return ApiErrorState(
                    error: snapshot.error!,
                    onRetry: () => setState(
                          () => _placesFuture = _reloadPlaces(),
                    ),
                  );
                }

                final places = _sortPlaces(
                  snapshot.data ?? const <ParkingPlace>[],
                );

                return Column(
                  children: [
                    ResultsHeader(
                      count: places.length,
                      sort: _sort,
                      onSortChanged: (mode) => setState(() => _sort = mode),
                    ),
                    Expanded(
                      child: places.isEmpty
                          ? const _EmptyState()
                          : ListView.separated(
                        padding: const EdgeInsets.fromLTRB(
                          AppSpacing.horizontalPadding,
                          AppSpacing.xs,
                          AppSpacing.horizontalPadding,
                          AppSpacing.lg,
                        ),
                        itemCount: places.length,
                        separatorBuilder: (_, _) =>
                        const SizedBox(height: AppSpacing.md),
                        itemBuilder: (_, i) {
                          final place = places[i];
                          final distanceMeters = const Distance()(
                            origin,
                            place.position,
                          );

                          return ParkingResultTile(
                            place: place,
                            distanceMeters: distanceMeters,
                            onTap: () => Navigator.of(context).push(
                              MaterialPageRoute(
                                builder: (_) =>
                                    ParkingDetailScreen(place: place),
                              ),
                            ),
                          );
                        },
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

class _EmptyState extends StatelessWidget {
  const _EmptyState();

  @override
  Widget build(BuildContext context) {
    return const Padding(
      padding: EdgeInsets.all(AppSpacing.xl),
      child: Center(
        child: Text(
          AppStrings.resultsEmpty,
          textAlign: TextAlign.center,
          style: TextStyle(color: AppColors.textSecondary, fontSize: 14),
        ),
      ),
    );
  }
}