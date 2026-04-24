import 'package:flutter/material.dart';

import '../../../../shared/constants/app_strings.dart';
import '../../../../shared/widgets/primary_button.dart';
import '../../../../shared/widgets/secondary_button.dart';
import '../../../../theme/app_colors.dart';
import '../../../../theme/app_spacing.dart';

class MapFilters {
  const MapFilters({
    this.radiusMeters = 500,
    this.freeSelected = true,
    this.paidSelected = true,
    this.onlyCovered = false,
    this.onlyAccessible = false,
    this.minAvailableSpots = 1,
  });

  final int radiusMeters;
  final bool freeSelected;
  final bool paidSelected;
  final bool onlyCovered;
  final bool onlyAccessible;
  final int minAvailableSpots;

  MapFilters copyWith({
    int? radiusMeters,
    bool? freeSelected,
    bool? paidSelected,
    bool? onlyCovered,
    bool? onlyAccessible,
    int? minAvailableSpots,
  }) {
    return MapFilters(
      radiusMeters: radiusMeters ?? this.radiusMeters,
      freeSelected: freeSelected ?? this.freeSelected,
      paidSelected: paidSelected ?? this.paidSelected,
      onlyCovered: onlyCovered ?? this.onlyCovered,
      onlyAccessible: onlyAccessible ?? this.onlyAccessible,
      minAvailableSpots: minAvailableSpots ?? this.minAvailableSpots,
    );
  }
}

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
    setState(() => _filters = const MapFilters());
  }

  void _apply() {
    widget.onApply(_filters);
    Navigator.of(context).pop();
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
                    onChanged: (v) =>
                        setState(() => _filters = _filters.copyWith(radiusMeters: v)),
                  ),
                  const SizedBox(height: AppSpacing.lg),
                  _TypeSection(
                    freeSelected: _filters.freeSelected,
                    paidSelected: _filters.paidSelected,
                    onFreeChanged: (v) => setState(
                      () => _filters = _filters.copyWith(freeSelected: v),
                    ),
                    onPaidChanged: (v) => setState(
                      () => _filters = _filters.copyWith(paidSelected: v),
                    ),
                  ),
                  const SizedBox(height: AppSpacing.lg),
                  _SwitchSection(
                    title: AppStrings.filtersCovered,
                    hint: AppStrings.filtersCoveredHint,
                    value: _filters.onlyCovered,
                    onChanged: (v) => setState(
                      () => _filters = _filters.copyWith(onlyCovered: v),
                    ),
                  ),
                  const SizedBox(height: AppSpacing.lg),
                  _SwitchSection(
                    title: AppStrings.filtersAccessible,
                    hint: AppStrings.filtersAccessibleHint,
                    value: _filters.onlyAccessible,
                    onChanged: (v) => setState(
                      () => _filters = _filters.copyWith(onlyAccessible: v),
                    ),
                  ),
                  const SizedBox(height: AppSpacing.lg),
                  _AvailableSpotsSection(
                    value: _filters.minAvailableSpots,
                    onChanged: (v) => setState(
                      () => _filters = _filters.copyWith(minAvailableSpots: v),
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

  static const List<int> _presets = [300, 500, 1000];

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const _SectionHeader('1. ${AppStrings.filtersRadius}'),
        Wrap(
          spacing: AppSpacing.sm,
          children: _presets
              .map(
                (m) => _RadiusChip(
                  label: m >= 1000 ? '${m ~/ 1000} km' : '$m m',
                  selected: value == m,
                  onTap: () => onChanged(m),
                ),
              )
              .toList(),
        ),
        const SizedBox(height: AppSpacing.sm),
        Slider(
          min: 100,
          max: 2000,
          divisions: 19,
          value: value.toDouble(),
          label: value >= 1000 ? '${(value / 1000).toStringAsFixed(1)} km' : '$value m',
          activeColor: AppColors.primary,
          onChanged: (v) => onChanged(v.round()),
        ),
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: const [
            Text(
              '100 m',
              style: TextStyle(fontSize: 12, color: AppColors.textSecondary),
            ),
            Text(
              '2 km',
              style: TextStyle(fontSize: 12, color: AppColors.textSecondary),
            ),
          ],
        ),
      ],
    );
  }
}

class _RadiusChip extends StatelessWidget {
  const _RadiusChip({
    required this.label,
    required this.selected,
    required this.onTap,
  });

  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return ChoiceChip(
      label: Text(label),
      selected: selected,
      showCheckmark: false,
      onSelected: (_) => onTap(),
      selectedColor: AppColors.primary,
      backgroundColor: AppColors.surfaceMuted,
      labelStyle: TextStyle(
        color: selected ? AppColors.textOnPrimary : AppColors.textPrimary,
        fontWeight: FontWeight.w600,
      ),
      side: BorderSide(
        color: selected ? AppColors.primary : AppColors.border,
      ),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(AppSpacing.radiusPill),
      ),
    );
  }
}

class _TypeSection extends StatelessWidget {
  const _TypeSection({
    required this.freeSelected,
    required this.paidSelected,
    required this.onFreeChanged,
    required this.onPaidChanged,
  });

  final bool freeSelected;
  final bool paidSelected;
  final ValueChanged<bool> onFreeChanged;
  final ValueChanged<bool> onPaidChanged;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const _SectionHeader('2. ${AppStrings.filtersType}'),
        Row(
          children: [
            Expanded(
              child: _TypeButton(
                label: AppStrings.filtersTypeFree,
                selected: freeSelected,
                onTap: () => onFreeChanged(!freeSelected),
              ),
            ),
            const SizedBox(width: AppSpacing.sm),
            Expanded(
              child: _TypeButton(
                label: AppStrings.filtersTypePaid,
                selected: paidSelected,
                onTap: () => onPaidChanged(!paidSelected),
              ),
            ),
          ],
        ),
      ],
    );
  }
}

class _TypeButton extends StatelessWidget {
  const _TypeButton({
    required this.label,
    required this.selected,
    required this.onTap,
  });

  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: selected ? AppColors.primary : AppColors.surface,
      borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
        child: Container(
          height: 48,
          alignment: Alignment.center,
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
            border: Border.all(
              color: selected ? AppColors.primary : AppColors.border,
              width: 1.4,
            ),
          ),
          child: Text(
            label,
            style: TextStyle(
              color: selected ? AppColors.textOnPrimary : AppColors.textPrimary,
              fontSize: 15,
              fontWeight: FontWeight.w600,
            ),
          ),
        ),
      ),
    );
  }
}

class _SwitchSection extends StatelessWidget {
  const _SwitchSection({
    required this.title,
    required this.hint,
    required this.value,
    required this.onChanged,
  });

  final String title;
  final String hint;
  final bool value;
  final ValueChanged<bool> onChanged;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _SectionHeader(title),
        Row(
          children: [
            Expanded(
              child: Text(
                hint,
                style: const TextStyle(
                  fontSize: 14,
                  color: AppColors.textSecondary,
                ),
              ),
            ),
            Switch(
              value: value,
              onChanged: onChanged,
              activeThumbColor: AppColors.primary,
            ),
          ],
        ),
      ],
    );
  }
}

class _AvailableSpotsSection extends StatelessWidget {
  const _AvailableSpotsSection({required this.value, required this.onChanged});

  final int value;
  final ValueChanged<int> onChanged;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          children: [
            const Expanded(
              child: _SectionHeader('5. ${AppStrings.filtersAvailable}'),
            ),
            Text(
              '$value+',
              style: const TextStyle(
                fontSize: 15,
                fontWeight: FontWeight.w700,
                color: AppColors.primary,
              ),
            ),
          ],
        ),
        Slider(
          min: 1,
          max: 10,
          divisions: 9,
          value: value.toDouble(),
          label: '$value+',
          activeColor: AppColors.primary,
          onChanged: (v) => onChanged(v.round()),
        ),
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: const [
            Text(
              '1+',
              style: TextStyle(fontSize: 12, color: AppColors.textSecondary),
            ),
            Text(
              '10+',
              style: TextStyle(fontSize: 12, color: AppColors.textSecondary),
            ),
          ],
        ),
      ],
    );
  }
}
