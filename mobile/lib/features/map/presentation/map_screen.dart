import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../../shared/widgets/app_top_bar.dart';
import '../../../theme/app_colors.dart';
import '../../../theme/app_spacing.dart';
import '../../location_picker/domain/place_suggestion.dart';
import '../../location_picker/presentation/location_picker_screen.dart';
import '../../parking/data/parking_constants.dart';
import '../../parking/data/parking_repository_provider.dart';
import '../../parking/domain/parking_place.dart';
import '../../parking/presentation/parking_ui.dart';
import '../../parking_detail/presentation/parking_detail_screen.dart';
import '../../parking_results/presentation/parking_results_screen.dart';
import '../../routing/data/osrm_client.dart';
import '../../routing/data/route_helpers.dart';
import '../../routing/data/route_request.dart';
import '../../routing/domain/route_path.dart';
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
  late final OsrmClient _osrm = OsrmClient();

  static const double _minZoom = 10;
  static const double _maxZoom = 18;
  static const double _initialZoom = 15;
  static const double _focusedZoom = 16;

  late MapFilters _filters;
  late Future<List<ParkingPlace>> _placesFuture;
  ParkingPlace? _selectedPlace;
  RoutePath? _route;
  LatLng? _routeOrigin;
  bool _loadingRoute = false;

  LatLng get _activeCenter => _filters.center ?? kMockUserLocation;

  @override
  void initState() {
    super.initState();
    _filters = widget.initialFilters ?? MapFilters();
    _placesFuture = parkingRepository.getNearby(_filters.toQuery());
    routeRequest.addListener(_onRouteRequested);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (routeRequest.request != null && mounted) _onRouteRequested();
    });
  }

  @override
  void dispose() {
    routeRequest.removeListener(_onRouteRequested);
    _mapController.dispose();
    _osrm.close();
    super.dispose();
  }

  void _onRouteRequested() {
    final place = routeRequest.request;
    if (place == null) return;
    routeRequest.consume();
    final origin = _activeCenter;
    setState(() {
      _selectedPlace = place;
      _route = null;
      _routeOrigin = origin;
      _loadingRoute = true;
    });
    _mapController.move(place.position, _focusedZoom);
    _fetchRoute(osrmProfileFor(place.category), origin, place.position);
  }

  Future<void> _fetchRoute(
    String profile,
    LatLng origin,
    LatLng destination,
  ) async {
    try {
      final route = await _osrm.route(profile, origin, destination);
      if (!mounted) return;
      setState(() {
        _route = route;
        _loadingRoute = false;
      });
      final fullPath = <LatLng>[origin, ...route.coordinates, destination];
      _mapController.fitCamera(
        CameraFit.bounds(
          bounds: LatLngBounds.fromPoints(fullPath),
          padding: const EdgeInsets.fromLTRB(48, 110, 48, 220),
        ),
      );
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _route = null;
        _routeOrigin = null;
        _loadingRoute = false;
      });
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('No se pudo calcular la ruta.')),
      );
    }
  }

  Future<void> _launchGoogleMaps() async {
    final origin = _routeOrigin;
    final destination = _selectedPlace;
    if (origin == null || destination == null) return;
    final uri = Uri.parse(
      'https://www.google.com/maps/dir/?api=1'
      '&origin=${origin.latitude},${origin.longitude}'
      '&destination=${destination.latitude},${destination.longitude}'
      '&travelmode=${googleTravelModeFor(destination.category)}',
    );
    final ok = await launchUrl(uri, mode: LaunchMode.externalApplication);
    if (!ok && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('No se pudo abrir Google Maps.')),
      );
    }
  }

  void _applyFilters(MapFilters filters) {
    setState(() {
      _filters = filters;
      _selectedPlace = null;
      _route = null;
      _routeOrigin = null;
      _placesFuture = parkingRepository.getNearby(_filters.toQuery());
    });
  }

  Future<void> _pickLocation() async {
    final suggestion = await Navigator.of(context).push<PlaceSuggestion>(
      MaterialPageRoute(builder: (_) => const LocationPickerScreen()),
    );
    if (suggestion == null || !mounted) return;
    setState(() {
      _filters = _filters.copyWith(
        center: suggestion.position,
        centerLabel: suggestion.shortName,
      );
      _selectedPlace = null;
      _route = null;
      _routeOrigin = null;
      _placesFuture = parkingRepository.getNearby(_filters.toQuery());
    });
    _mapController.move(suggestion.position, _focusedZoom);
  }

  void _centerOnUser() {
    setState(() {
      _filters = _filters.withoutCenter();
      _selectedPlace = null;
      _route = null;
      _routeOrigin = null;
      _placesFuture = parkingRepository.getNearby(_filters.toQuery());
    });
    _mapController.move(kMockUserLocation, _focusedZoom);
  }

  void _zoomIn() {
    final z = (_mapController.camera.zoom + 1).clamp(_minZoom, _maxZoom);
    _mapController.move(_mapController.camera.center, z);
  }

  void _zoomOut() {
    final z = (_mapController.camera.zoom - 1).clamp(_minZoom, _maxZoom);
    _mapController.move(_mapController.camera.center, z);
  }

  void _selectPlace(ParkingPlace place) {
    setState(() {
      _selectedPlace = place;
      _route = null;
      _routeOrigin = null;
    });
  }

  void _clearSelection() {
    setState(() {
      _selectedPlace = null;
      _route = null;
      _routeOrigin = null;
    });
  }

  void _openDetail(ParkingPlace place) {
    Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => ParkingDetailScreen(place: place)),
    );
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
                  onPressed: _pickLocation,
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
                final activeCenter = _activeCenter;
                return Stack(
                  children: [
                    FlutterMap(
                      mapController: _mapController,
                      options: MapOptions(
                        initialCenter: _filters.center ?? kCaceresCenter,
                        initialZoom: _initialZoom,
                        minZoom: _minZoom,
                        maxZoom: _maxZoom,
                        interactionOptions: const InteractionOptions(
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
                        if (_route != null &&
                            _routeOrigin != null &&
                            selected != null)
                          PolylineLayer(
                            polylines: [
                              Polyline(
                                points: <LatLng>[
                                  _routeOrigin!,
                                  ..._route!.coordinates,
                                  selected.position,
                                ],
                                color: AppColors.primary,
                                strokeWidth: 5,
                                borderColor: Colors.white,
                                borderStrokeWidth: 1.5,
                              ),
                            ],
                          ),
                        MarkerLayer(markers: _buildMarkers(places)),
                      ],
                    ),
                    Positioned(
                      left: AppSpacing.md,
                      right: 88,
                      top: AppSpacing.md,
                      child: _MapLegend(
                        places: places,
                        centerLabel: _filters.centerLabel,
                      ),
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
                    if (_loadingRoute && selected != null)
                      Positioned(
                        top: AppSpacing.md,
                        left: 0,
                        right: 0,
                        child: Center(
                          child: _RouteLoadingPill(
                            label:
                                'Calculando ruta '
                                '${routingLabelFor(selected.category)}…',
                          ),
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
                                activeCenter,
                                selected.position,
                              ),
                              onOpenDetail: () => _openDetail(selected),
                              onClose: _clearSelection,
                              onOpenInMaps: _route == null
                                  ? null
                                  : _launchGoogleMaps,
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
    final markers = <Marker>[];
    final pickedCenter = _filters.center;

    if (pickedCenter == null) {
      markers.add(
        const Marker(
          point: kMockUserLocation,
          width: 22,
          height: 22,
          child: UserLocationMarker(),
        ),
      );
    } else {
      markers.add(
        Marker(
          point: pickedCenter,
          width: 36,
          height: 44,
          alignment: Alignment.topCenter,
          child: const DestinationPinMarker(),
        ),
      );
    }

    final placeIds = <String>{};
    for (final place in places) {
      placeIds.add(place.id);
      markers.add(
        Marker(
          point: place.position,
          width: 46,
          height: 54,
          alignment: Alignment.topCenter,
          child: GestureDetector(
            onTap: () => _selectPlace(place),
            child: ParkingMapMarker(
              category: place.category,
              isSelected: _selectedPlace?.id == place.id,
            ),
          ),
        ),
      );
    }

    final selected = _selectedPlace;
    if (selected != null && !placeIds.contains(selected.id)) {
      markers.add(
        Marker(
          point: selected.position,
          width: 46,
          height: 54,
          alignment: Alignment.topCenter,
          child: GestureDetector(
            onTap: () => _selectPlace(selected),
            child: ParkingMapMarker(
              category: selected.category,
              isSelected: true,
            ),
          ),
        ),
      );
    }

    return markers;
  }
}

class _RouteLoadingPill extends StatelessWidget {
  const _RouteLoadingPill({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: AppColors.surface.withValues(alpha: 0.95),
      borderRadius: BorderRadius.circular(AppSpacing.radiusPill),
      child: Padding(
        padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.md,
          vertical: 6,
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            const SizedBox(
              width: 14,
              height: 14,
              child: CircularProgressIndicator(strokeWidth: 2),
            ),
            const SizedBox(width: AppSpacing.sm),
            Text(
              label,
              style: const TextStyle(
                fontSize: 12,
                fontWeight: FontWeight.w600,
                color: AppColors.textPrimary,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _MapLegend extends StatelessWidget {
  const _MapLegend({required this.places, this.centerLabel});

  final List<ParkingPlace> places;
  final String? centerLabel;

  @override
  Widget build(BuildContext context) {
    final categories = places.map((p) => p.category).toSet().take(5).toList();
    if (categories.isEmpty && centerLabel == null) {
      return const SizedBox.shrink();
    }

    return Material(
      color: AppColors.surface.withValues(alpha: 0.92),
      borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
      child: Padding(
        padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.sm,
          vertical: AppSpacing.xs,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (centerLabel != null)
              Padding(
                padding: const EdgeInsets.only(bottom: 2),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Icon(
                      Icons.place,
                      size: 12,
                      color: AppColors.primary,
                    ),
                    const SizedBox(width: 3),
                    Flexible(
                      child: Text(
                        centerLabel!,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          fontSize: 11,
                          fontWeight: FontWeight.w700,
                          color: AppColors.textPrimary,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            if (categories.isNotEmpty)
              Wrap(
                spacing: AppSpacing.sm,
                runSpacing: 2,
                children: [
                  for (final category in categories)
                    _LegendItem(category: category),
                ],
              ),
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
