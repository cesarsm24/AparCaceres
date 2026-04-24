import 'package:flutter/material.dart';

import '../../../../shared/constants/app_strings.dart';
import '../../../../shared/widgets/app_card.dart';
import '../../../../theme/app_colors.dart';
import '../../../../theme/app_spacing.dart';
import '../../../parking/domain/parking_place.dart';
import '../../../parking/presentation/parking_ui.dart';

class NearbySummaryCard extends StatelessWidget {
  const NearbySummaryCard({
    super.key,
    required this.places,
    required this.radiusMeters,
    this.onTap,
  });

  final List<ParkingPlace> places;
  final int radiusMeters;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final totalSpaces = places.fold<int>(
      0,
      (sum, place) => sum + (place.totalSpaces ?? 0),
    );
    final accent = places.isEmpty
        ? AppColors.primary
        : places.first.category.color;

    return AppCard(
      onTap: onTap,
      padding: const EdgeInsets.all(AppSpacing.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            AppStrings.sectionNearby,
            style: TextStyle(
              fontSize: 16,
              fontWeight: FontWeight.w700,
              color: AppColors.textPrimary,
            ),
          ),
          const SizedBox(height: AppSpacing.xs),
          Text(
            'Radio: $radiusMeters m',
            style: const TextStyle(
              fontSize: 13,
              color: AppColors.textSecondary,
            ),
          ),
          const SizedBox(height: AppSpacing.md),
          Row(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '${places.length}',
                      style: const TextStyle(
                        fontSize: 40,
                        fontWeight: FontWeight.w700,
                        color: AppColors.textPrimary,
                        height: 1.0,
                      ),
                    ),
                    const SizedBox(height: AppSpacing.xs),
                    const Text(
                      'resultados cerca de ti',
                      style: TextStyle(
                        fontSize: 14,
                        color: AppColors.textSecondary,
                        height: 1.3,
                      ),
                    ),
                  ],
                ),
              ),
              _MapShortcutIcon(color: accent),
            ],
          ),
          if (totalSpaces > 0) ...[
            const SizedBox(height: AppSpacing.sm),
            Row(
              children: [
                Icon(Icons.local_parking_outlined, size: 16, color: accent),
                const SizedBox(width: AppSpacing.xs),
                Expanded(
                  child: Text(
                    formatSpaces(totalSpaces)!,
                    style: TextStyle(
                      fontSize: 13,
                      fontWeight: FontWeight.w600,
                      color: accent,
                    ),
                  ),
                ),
                const Icon(Icons.chevron_right, color: AppColors.textSecondary),
              ],
            ),
          ] else
            const Align(
              alignment: Alignment.centerRight,
              child: Icon(Icons.chevron_right, color: AppColors.textSecondary),
            ),
        ],
      ),
    );
  }
}

class _MapShortcutIcon extends StatelessWidget {
  const _MapShortcutIcon({required this.color});

  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 64,
      height: 64,
      decoration: BoxDecoration(
        color: AppColors.surfaceMuted,
        borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
        border: Border.all(color: AppColors.border),
      ),
      child: Stack(
        alignment: Alignment.center,
        children: [
          Icon(Icons.map_outlined, color: color, size: 30),
          Positioned(
            right: 8,
            bottom: 8,
            child: Container(
              width: 18,
              height: 18,
              decoration: const BoxDecoration(
                color: AppColors.surface,
                shape: BoxShape.circle,
              ),
              child: const Icon(
                Icons.arrow_forward,
                size: 12,
                color: AppColors.textSecondary,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
