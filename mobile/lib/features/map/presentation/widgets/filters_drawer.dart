import 'package:flutter/material.dart';
import 'package:latlong2/latlong.dart';

import '../../../../shared/constants/app_strings.dart';
import '../../../../shared/widgets/primary_button.dart';
import '../../../../shared/widgets/secondary_button.dart';
import '../../../../theme/app_colors.dart';
import '../../../../theme/app_spacing.dart';
import '../../../location/data/location_service.dart';
import '../../../parking/domain/parking_place.dart';
import '../../../parking/domain/parking_query.dart';
import '../../../parking/presentation/parking_ui.dart';

/// Estado de filtros aplicado a la vista de mapa.
///
/// Mantiene los criterios seleccionados por el usuario y genera la consulta de
/// aparcamientos usando el centro explícito o, en su defecto, la posición activa.
class MapFilters {
  MapFilters({
    this.radiusMeters = 1000,
    Set<ParkingVehicleType>? vehicleTypes,
    Set<ParkingCategory>? categories,
    Set<ParkingRegulation>? regulations,
    this.minSpaces = 0,
    this.center,
    this.centerLabel,
  }) : vehicleTypes = vehicleTypes ?? ParkingVehicleType.values.toSet(),
        categories = categories ?? ParkingCategory.values.toSet(),
        regulations = regulations ?? ParkingRegulation.values.toSet();

  final int radiusMeters;
  final Set<ParkingVehicleType> vehicleTypes;
  final Set<ParkingCategory> categories;
  final Set<ParkingRegulation> regulations;
  final int minSpaces;
  final LatLng? center;
  final String? centerLabel;

  ParkingQuery toQuery() {
    return ParkingQuery(
      center: center ?? locationService.position.value,
      radiusMeters: radiusMeters,
      vehicleTypes: vehicleTypes,
      categories: categories,
      regulations: regulations,
      minSpaces: minSpaces,
    );
  }

  MapFilters copyWith({
    int? radiusMeters,
    Set<ParkingVehicleType>? vehicleTypes,
    Set<ParkingCategory>? categories,
    Set<ParkingRegulation>? regulations,
    int? minSpaces,
    LatLng? center,
    String? centerLabel,
  }) {
    return MapFilters(
      radiusMeters: radiusMeters ?? this.radiusMeters,
      vehicleTypes: vehicleTypes ?? this.vehicleTypes,
      categories: categories ?? this.categories,
      regulations: regulations ?? this.regulations,
      minSpaces: minSpaces ?? this.minSpaces,
      center: center ?? this.center,
      centerLabel: centerLabel ?? this.centerLabel,
    );
  }

  static MapFilters forVehicle(ParkingVehicleType vehicleType) {
    return MapFilters(vehicleTypes: {vehicleType});
  }

  static MapFilters forAccessible() {
    return MapFilters(
      vehicleTypes: {ParkingVehicleType.car},
      categories: {ParkingCategory.accessible},
      regulations: {ParkingRegulation.reserved},
    );
  }

  static MapFilters atLocation(LatLng center, {String? label}) {
    return MapFilters(center: center, centerLabel: label);
  }

  MapFilters withoutCenter() {
    return MapFilters(
      radiusMeters: radiusMeters,
      vehicleTypes: vehicleTypes,
      categories: categories,
      regulations: regulations,
      minSpaces: minSpaces,
    );
  }
}

/// Drawer lateral para edición de filtros del mapa.
///
/// Trabaja sobre una copia local de los filtros iniciales y solo comunica el
/// estado definitivo cuando se pulsa la acción de aplicar.
class FiltersDrawer extends StatefulWidget {
  const FiltersDrawer({
    super.key,
    required this.initialFilters,
    required this.onApply,
  });

  final MapFilters initialFilters;
  final ValueChanged<MapFilters> onApply;

  @override
  State<FiltersDrawer> createState() => _FiltersDrawerState();
}

class _FiltersDrawerState extends State<FiltersDrawer> {
  late MapFilters _filters;

  @override
  void initState() {
    super.initState();
    _filters = widget.initialFilters;
  }

  void _reset() {
    setState(() => _filters = MapFilters());
  }

  void _apply() {
    widget.onApply(_filters);
    Navigator.of(context).pop();
  }

  void _toggleVehicle(ParkingVehicleType value) {
    final next = Set<ParkingVehicleType>.of(_filters.vehicleTypes);
    next.contains(value) ? next.remove(value) : next.add(value);

    setState(() => _filters = _filters.copyWith(vehicleTypes: next));
  }

  void _toggleCategory(ParkingCategory value) {
    final next = Set<ParkingCategory>.of(_filters.categories);
    next.contains(value) ? next.remove(value) : next.add(value);

    setState(() => _filters = _filters.copyWith(categories: next));
  }

  void _toggleRegulation(ParkingRegulation value) {
    final next = Set<ParkingRegulation>.of(_filters.regulations);
    next.contains(value) ? next.remove(value) : next.add(value);

    setState(() => _filters = _filters.copyWith(regulations: next));
  }

  @override
  Widget build(BuildContext context) {
    return Drawer(
      backgroundColor: AppColors.surface,
      child: SafeArea(
        child: Column(
          children: [
            _DrawerHeader(onClose: () => Navigator.of(context).pop()),
            Expanded(
              child: ListView(
                padding: const EdgeInsets.symmetric(
                  horizontal: AppSpacing.lg,
                  vertical: AppSpacing.md,
                ),
                children: [
                  _RadiusSection(
                    value: _filters.radiusMeters,
                    onChanged: (value) => setState(
                          () => _filters = _filters.copyWith(radiusMeters: value),
                    ),
                  ),
                  const SizedBox(height: AppSpacing.lg),
                  _MultiChipSection<ParkingVehicleType>(
                    title: AppStrings.filtersVehicle,
                    values: ParkingVehicleType.values,
                    selected: _filters.vehicleTypes,
                    labelOf: (value) => value.label,
                    iconOf: (value) => value.icon,
                    colorOf: (_) => AppColors.primary,
                    onToggle: _toggleVehicle,
                  ),
                  const SizedBox(height: AppSpacing.lg),
                  _MultiChipSection<ParkingCategory>(
                    title: AppStrings.filtersCategory,
                    values: ParkingCategory.values,
                    selected: _filters.categories,
                    labelOf: (value) => value.label,
                    iconOf: (value) => value.icon,
                    colorOf: (value) => value.color,
                    onToggle: _toggleCategory,
                  ),
                  const SizedBox(height: AppSpacing.lg),
                  _MultiChipSection<ParkingRegulation>(
                    title: AppStrings.filtersRegulation,
                    values: ParkingRegulation.values,
                    selected: _filters.regulations,
                    labelOf: (value) => value.label,
                    iconOf: (_) => Icons.label_outline,
                    colorOf: (value) => value.color,
                    onToggle: _toggleRegulation,
                  ),
                  const SizedBox(height: AppSpacing.lg),
                  _SpacesSection(
                    value: _filters.minSpaces,
                    onChanged: (value) => setState(
                          () => _filters = _filters.copyWith(minSpaces: value),
                    ),
                  ),
                ],
              ),
            ),
            _DrawerFooter(onReset: _reset, onApply: _apply),
          ],
        ),
      ),
    );
  }
}

class _DrawerHeader extends StatelessWidget {
  const _DrawerHeader({required this.onClose});

  final VoidCallback onClose;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(
        AppSpacing.lg,
        AppSpacing.md,
        AppSpacing.sm,
        AppSpacing.md,
      ),
      child: Row(
        children: [
          const Expanded(
            child: Text(
              AppStrings.filtersTitle,
              style: TextStyle(
                fontSize: 22,
                fontWeight: FontWeight.w700,
                color: AppColors.textPrimary,
              ),
            ),
          ),
          IconButton(
            onPressed: onClose,
            icon: const Icon(Icons.close, color: AppColors.textPrimary),
          ),
        ],
      ),
    );
  }
}

class _DrawerFooter extends StatelessWidget {
  const _DrawerFooter({required this.onReset, required this.onApply});

  final VoidCallback onReset;
  final VoidCallback onApply;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.fromLTRB(
        AppSpacing.lg,
        AppSpacing.md,
        AppSpacing.lg,
        AppSpacing.lg,
      ),
      decoration: const BoxDecoration(
        color: AppColors.surface,
        border: Border(top: BorderSide(color: AppColors.border)),
      ),
      child: Row(
        children: [
          Expanded(
            child: SecondaryButton(
              label: AppStrings.filtersClear,
              onPressed: onReset,
            ),
          ),
          const SizedBox(width: AppSpacing.md),
          Expanded(
            child: PrimaryButton(
              label: AppStrings.filtersApply,
              onPressed: onApply,
            ),
          ),
        ],
      ),
    );
  }
}

class _SectionHeader extends StatelessWidget {
  const _SectionHeader(this.title);

  final String title;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.sm + 4),
      child: Text(
        title,
        style: const TextStyle(
          fontSize: 16,
          fontWeight: FontWeight.w700,
          color: AppColors.textPrimary,
        ),
      ),
    );
  }
}

class _RadiusSection extends StatelessWidget {
  const _RadiusSection({required this.value, required this.onChanged});

  final int value;
  final ValueChanged<int> onChanged;

  static const List<int> _presets = [500, 1000, 2000];

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const _SectionHeader(AppStrings.filtersRadius),
        Wrap(
          spacing: AppSpacing.sm,
          children: _presets
              .map(
                (meters) => _FilterChip(
              label: meters >= 1000 ? '${meters ~/ 1000} km' : '$meters m',
              selected: value == meters,
              color: AppColors.primary,
              onTap: () => onChanged(meters),
            ),
          )
              .toList(),
        ),
        const SizedBox(height: AppSpacing.sm),
        Slider(
          min: 100,
          max: 3000,
          divisions: 29,
          value: value.toDouble(),
          label: value >= 1000
              ? '${(value / 1000).toStringAsFixed(1)} km'
              : '$value m',
          activeColor: AppColors.primary,
          onChanged: (value) => onChanged(value.round()),
        ),
      ],
    );
  }
}

class _MultiChipSection<T> extends StatelessWidget {
  const _MultiChipSection({
    required this.title,
    required this.values,
    required this.selected,
    required this.labelOf,
    required this.iconOf,
    required this.colorOf,
    required this.onToggle,
  });

  final String title;
  final List<T> values;
  final Set<T> selected;
  final String Function(T value) labelOf;
  final IconData Function(T value) iconOf;
  final Color Function(T value) colorOf;
  final ValueChanged<T> onToggle;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _SectionHeader(title),
        Wrap(
          spacing: AppSpacing.sm,
          runSpacing: AppSpacing.xs,
          children: values
              .map(
                (value) => _FilterChip(
              label: labelOf(value),
              icon: iconOf(value),
              selected: selected.contains(value),
              color: colorOf(value),
              onTap: () => onToggle(value),
            ),
          )
              .toList(),
        ),
      ],
    );
  }
}

class _FilterChip extends StatelessWidget {
  const _FilterChip({
    required this.label,
    required this.selected,
    required this.color,
    required this.onTap,
    this.icon,
  });

  final String label;
  final bool selected;
  final Color color;
  final VoidCallback onTap;
  final IconData? icon;

  @override
  Widget build(BuildContext context) {
    return ChoiceChip(
      avatar: icon == null
          ? null
          : Icon(
        icon,
        size: 16,
        color: selected ? AppColors.textOnPrimary : color,
      ),
      label: Text(label),
      selected: selected,
      showCheckmark: false,
      onSelected: (_) => onTap(),
      selectedColor: color,
      backgroundColor: AppColors.surfaceMuted,
      labelStyle: TextStyle(
        color: selected ? AppColors.textOnPrimary : AppColors.textPrimary,
        fontWeight: FontWeight.w600,
      ),
      side: BorderSide(color: selected ? color : AppColors.border),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(AppSpacing.radiusPill),
      ),
    );
  }
}

class _SpacesSection extends StatelessWidget {
  const _SpacesSection({required this.value, required this.onChanged});

  final int value;
  final ValueChanged<int> onChanged;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          children: [
            const Expanded(child: _SectionHeader(AppStrings.filtersSpaces)),
            Text(
              value == 0 ? 'Todas' : '$value+',
              style: const TextStyle(
                fontSize: 15,
                fontWeight: FontWeight.w700,
                color: AppColors.primary,
              ),
            ),
          ],
        ),
        Slider(
          min: 0,
          max: 20,
          divisions: 20,
          value: value.toDouble(),
          label: value == 0 ? 'Todas' : '$value+',
          activeColor: AppColors.primary,
          onChanged: (value) => onChanged(value.round()),
        ),
      ],
    );
  }
}