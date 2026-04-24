import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';

import '../../../shared/widgets/app_top_bar.dart';
import '../../../theme/app_colors.dart';
import '../../../theme/app_spacing.dart';
import '../../parking/data/parking_constants.dart';
import '../../parking/data/parking_repository_provider.dart';
import '../../parking/domain/parking_place.dart';
import '../../parking/presentation/parking_ui.dart';
import '../../parking_detail/presentation/parking_detail_screen.dart';
import '../../parking_results/presentation/parking_results_screen.dart';
import '../../search/presentation/search_screen.dart';
import 'widgets/filters_drawer.dart';
import 'widgets/map_controls.dart';
import 'widgets/map_results_sheet.dart';
import 'widgets/parking_map_marker.dart';

class MapScreen extends StatefulWidget {
  const MapScreen({super.key, this.initialFilters});

  final MapFilters? initialFilters;

  @override
  State<MapScreen> createState() => _MapScreenState();
}

class _MapScreenState extends State<MapScreen> {
  final MapController _mapController = MapController();
  final GlobalKey<ScaffoldState> _scaffoldKey = GlobalKey<ScaffoldState>();

  static const double _minZoom = 10;
  static const double _maxZoom = 18;
  static const double _initialZoom = 15;

  late MapFilters _filters;
  late Future<List<ParkingPlace>> _placesFuture;
  ParkingPlace? _selectedPlace;

  @override
  void initState() {
    super.initState();
    _filters = widget.initialFilters ?? MapFilters();
    _placesFuture = parkingRepository.getNearby(_filters.toQuery());
  }

  void _applyFilters(MapFilters filters) {
    setState(() {
      _filters = filters;
      _selectedPlace = null;
      _placesFuture = parkingRepository.getNearby(_filters.toQuery());
    });
  }

  void _centerOnUser() {
    _mapController.move(kMockUserLocation, _initialZoom);
  }

  void _zoomIn() {
    final z = (_mapController.camera.zoom + 1).clamp(_minZoom, _maxZoom);
    _mapController.move(_mapController.camera.center, z);
  }

  void _zoomOut() {
    final z = (_mapController.camera.zoom - 1).clamp(_minZoom, _maxZoom);
    _mapController.move(_mapController.camera.center, z);
  }

  void _openDetail(ParkingPlace place) {
    Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => ParkingDetailScreen(place: place)),
    );
  }

  @override
  void dispose() {
    _mapController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      key: _scaffoldKey,
      backgroundColor: AppColors.pageBackground,
      endDrawer: FiltersDrawer(
        initialFilters: _filters,
        onApply: _applyFilters,
      ),
      body: Column(
        children: [
          AppTopBar(
            trailing: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                IconButton(
                  onPressed: () => Navigator.of(context).push(
                    MaterialPageRoute(
                      builder: (_) => const SearchScreen(),
                    ),
                  ),
                  icon: const Icon(
                    Icons.search,
                    color: AppColors.textOnPrimary,
                  ),
                ),
                IconButton(
                  onPressed: () => _scaffoldKey.currentState?.openEndDrawer(),
                  icon: const Icon(Icons.tune, color: AppColors.textOnPrimary),
                ),
              ],
            ),
          ),
          Expanded(
            child: FutureBuilder<List<ParkingPlace>>(
              future: _placesFuture,
              builder: (context, snapshot) {
                final places = snapshot.data ?? const <ParkingPlace>[];
                final selected = _selectedPlace;
                return Stack(
                  children: [
                    FlutterMap(
                      mapController: _mapController,
                      options: const MapOptions(
                        initialCenter: kCaceresCenter,
                        initialZoom: _initialZoom,
                        minZoom: _minZoom,
                        maxZoom: _maxZoom,
                        interactionOptions: InteractionOptions(
                          flags: InteractiveFlag.all & ~InteractiveFlag.rotate,
                        ),
                      ),
                      children: [
                        TileLayer(
                          urlTemplate:
                              'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                          userAgentPackageName: 'com.aparcaceres.mobile',
                          maxZoom: 19,
                        ),
                        PolygonLayer(polygons: _buildPolygons(places)),
                        PolylineLayer(polylines: _buildLines(places)),
                        MarkerLayer(markers: _buildMarkers(places)),
                      ],
                    ),
                    Positioned(
                      left: AppSpacing.md,
                      right: 88,
                      top: AppSpacing.md,
                      child: _MapLegend(places: places),
                    ),
                    Positioned(
                      right: AppSpacing.md,
                      top: AppSpacing.md,
                      child: MapControls(
                        onLocate: _centerOnUser,
                        onZoomIn: _zoomIn,
                        onZoomOut: _zoomOut,
                      ),
                    ),
                    if (snapshot.connectionState == ConnectionState.waiting)
                      const Center(child: CircularProgressIndicator()),
                    Positioned(
                      left: 0,
                      right: 0,
                      bottom: 0,
                      child: selected == null
                          ? MapResultsSheet(
                              resultCount: places.length,
                              radiusMeters: _filters.radiusMeters,
                              onTap: () => Navigator.of(context).push(
                                MaterialPageRoute(
                                  builder: (_) => ParkingResultsScreen(
                                    filters: _filters,
                                  ),
                                ),
                              ),
                            )
                          : ParkingPreviewSheet(
                              place: selected,
                              distanceMeters: const Distance()(
                                kMockUserLocation,
                                selected.position,
                              ),
                              onOpenDetail: () => _openDetail(selected),
                              onClose: () =>
                                  setState(() => _selectedPlace = null),
                            ),
                    ),
                    const Positioned(
                      left: AppSpacing.md,
                      bottom: AppSpacing.sm,
                      child: _OsmAttribution(),
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

  List<Polygon> _buildPolygons(List<ParkingPlace> places) {
    return places
        .where(
          (place) =>
              place.geometryType == ParkingGeometryType.polygon &&
              place.polygonRings.isNotEmpty,
        )
        .map(
          (place) => Polygon(
            points: place.polygonRings.first,
            color: place.category.color.withValues(alpha: 0.18),
            borderColor: place.category.color,
            borderStrokeWidth: 2,
          ),
        )
        .toList();
  }

  List<Polyline> _buildLines(List<ParkingPlace> places) {
    return places
        .where(
          (place) =>
              place.geometryType == ParkingGeometryType.lineString &&
              place.linePoints.length >= 2,
        )
        .map(
          (place) => Polyline(
            points: place.linePoints,
            color: place.category.color,
            strokeWidth: 4,
          ),
        )
        .toList();
  }

  List<Marker> _buildMarkers(List<ParkingPlace> places) {
    return [
      const Marker(
        point: kMockUserLocation,
        width: 22,
        height: 22,
        child: UserLocationMarker(),
      ),
      ...places.map(
        (place) => Marker(
          point: place.position,
          width: 46,
          height: 54,
          alignment: Alignment.topCenter,
          child: GestureDetector(
            onTap: () => setState(() => _selectedPlace = place),
            child: ParkingMapMarker(
              category: place.category,
              isSelected: _selectedPlace?.id == place.id,
            ),
          ),
        ),
      ),
    ];
  }
}

class _MapLegend extends StatelessWidget {
  const _MapLegend({required this.places});

  final List<ParkingPlace> places;

  @override
  Widget build(BuildContext context) {
    final categories = places.map((p) => p.category).toSet().take(5).toList();
    if (categories.isEmpty) return const SizedBox.shrink();

    return Material(
      color: AppColors.surface.withValues(alpha: 0.92),
      borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
      child: Padding(
        padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.sm,
          vertical: AppSpacing.xs,
        ),
        child: Wrap(
          spacing: AppSpacing.sm,
          runSpacing: 2,
          children: [
            for (final category in categories) _LegendItem(category: category),
          ],
        ),
      ),
    );
  }
}

class _LegendItem extends StatelessWidget {
  const _LegendItem({required this.category});

  final ParkingCategory category;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 8,
          height: 8,
          decoration: BoxDecoration(
            color: category.color,
            shape: BoxShape.circle,
          ),
        ),
        const SizedBox(width: 4),
        Text(
          category.label,
          style: const TextStyle(
            fontSize: 11,
            fontWeight: FontWeight.w600,
            color: AppColors.textPrimary,
          ),
        ),
      ],
    );
  }
}

class _OsmAttribution extends StatelessWidget {
  const _OsmAttribution();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.sm,
        vertical: 2,
      ),
      decoration: BoxDecoration(
        color: AppColors.surface.withValues(alpha: 0.85),
        borderRadius: BorderRadius.circular(AppSpacing.radiusSm),
      ),
      child: const Text(
        '© OpenStreetMap',
        style: TextStyle(fontSize: 10, color: AppColors.textSecondary),
      ),
    );
  }
}
