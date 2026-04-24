import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';

import '../../../shared/widgets/app_top_bar.dart';
import '../../../theme/app_colors.dart';
import '../../../theme/app_spacing.dart';
import '../data/map_mock_data.dart';
import 'widgets/filters_drawer.dart';
import 'widgets/map_controls.dart';
import 'widgets/map_results_sheet.dart';
import 'widgets/parking_map_marker.dart';

class MapScreen extends StatefulWidget {
  const MapScreen({super.key});

  @override
  State<MapScreen> createState() => _MapScreenState();
}

class _MapScreenState extends State<MapScreen> {
  final MapController _mapController = MapController();
  final GlobalKey<ScaffoldState> _scaffoldKey = GlobalKey<ScaffoldState>();

  static const double _minZoom = 10;
  static const double _maxZoom = 18;
  static const double _initialZoom = 15;

  MapFilters _filters = const MapFilters();

  List<ParkingMarker> get _visibleMarkers {
    return kParkingMarkers.where((m) {
      if (m.isPaid && !_filters.paidSelected) return false;
      if (!m.isPaid && !_filters.freeSelected) return false;
      if (m.freeSpots < _filters.minAvailableSpots) return false;
      return true;
    }).toList();
  }

  void _centerOnUser() {
    _mapController.move(kUserLocation, _initialZoom);
  }

  void _zoomIn() {
    final z = (_mapController.camera.zoom + 1).clamp(_minZoom, _maxZoom);
    _mapController.move(_mapController.camera.center, z);
  }

  void _zoomOut() {
    final z = (_mapController.camera.zoom - 1).clamp(_minZoom, _maxZoom);
    _mapController.move(_mapController.camera.center, z);
  }

  @override
  void dispose() {
    _mapController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final markers = _visibleMarkers;
    return Scaffold(
      key: _scaffoldKey,
      backgroundColor: AppColors.pageBackground,
      endDrawer: FiltersDrawer(
        initialFilters: _filters,
        onApply: (f) => setState(() => _filters = f),
      ),
      body: Column(
        children: [
          AppTopBar(
            trailing: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                IconButton(
                  onPressed: () {},
                  icon: const Icon(
                    Icons.search,
                    color: AppColors.textOnPrimary,
                  ),
                ),
                IconButton(
                  onPressed: () => _scaffoldKey.currentState?.openEndDrawer(),
                  icon: const Icon(
                    Icons.tune,
                    color: AppColors.textOnPrimary,
                  ),
                ),
              ],
            ),
          ),
          Expanded(
            child: Stack(
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
                    MarkerLayer(
                      markers: [
                        const Marker(
                          point: kUserLocation,
                          width: 22,
                          height: 22,
                          child: UserLocationMarker(),
                        ),
                        ...markers.map(
                          (m) => Marker(
                            point: m.position,
                            width: 40,
                            height: 48,
                            alignment: Alignment.topCenter,
                            child: ParkingMapMarker(isPaid: m.isPaid),
                          ),
                        ),
                      ],
                    ),
                  ],
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
                Positioned(
                  left: 0,
                  right: 0,
                  bottom: 0,
                  child: MapResultsSheet(
                    resultCount: markers.length,
                    radiusMeters: _filters.radiusMeters,
                    onTap: () {},
                  ),
                ),
                const Positioned(
                  left: AppSpacing.md,
                  bottom: AppSpacing.sm,
                  child: _OsmAttribution(),
                ),
              ],
            ),
          ),
        ],
      ),
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
