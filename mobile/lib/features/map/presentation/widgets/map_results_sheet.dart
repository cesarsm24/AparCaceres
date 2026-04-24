import 'package:flutter/material.dart';

import '../../../../shared/constants/app_strings.dart';
import '../../../../theme/app_colors.dart';
import '../../../../theme/app_spacing.dart';

class MapResultsSheet extends StatelessWidget {
  const MapResultsSheet({
    super.key,
    required this.resultCount,
    required this.radiusMeters,
    this.onTap,
  });

  final int resultCount;
  final int radiusMeters;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final radiusLabel = radiusMeters >= 1000
        ? '${(radiusMeters / 1000).toStringAsFixed(radiusMeters % 1000 == 0 ? 0 : 1)} km'
        : '$radiusMeters m';

    return Material(
      color: AppColors.surface,
      borderRadius: const BorderRadius.vertical(
        top: Radius.circular(AppSpacing.radiusLg),
      ),
      elevation: 8,
      child: InkWell(
        onTap: onTap,
        borderRadius: const BorderRadius.vertical(
          top: Radius.circular(AppSpacing.radiusLg),
        ),
        child: Padding(
          padding: const EdgeInsets.fromLTRB(
            AppSpacing.lg,
            AppSpacing.md,
            AppSpacing.lg,
            AppSpacing.lg,
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Center(
                child: Container(
                  width: 40,
                  height: 4,
                  decoration: BoxDecoration(
                    color: AppColors.border,
                    borderRadius: BorderRadius.circular(AppSpacing.radiusPill),
                  ),
                ),
              ),
              const SizedBox(height: AppSpacing.md),
              Row(
                children: [
                  const _BadgeP(),
                  const SizedBox(width: AppSpacing.md),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          '$resultCount ${AppStrings.mapResultsFound}',
                          style: const TextStyle(
                            fontSize: 16,
                            fontWeight: FontWeight.w700,
                            color: AppColors.textPrimary,
                          ),
                        ),
                        const SizedBox(height: 2),
                        Text(
                          '${AppStrings.mapRadiusPrefix}: $radiusLabel · ${AppStrings.mapFreeAndPaid}',
                          style: const TextStyle(
                            fontSize: 13,
                            color: AppColors.textSecondary,
                          ),
                        ),
                      ],
                    ),
                  ),
                  const Icon(
                    Icons.chevron_right,
                    color: AppColors.textSecondary,
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _BadgeP extends StatelessWidget {
  const _BadgeP();

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 40,
      height: 40,
      decoration: BoxDecoration(
        color: AppColors.primary,
        borderRadius: BorderRadius.circular(AppSpacing.radiusSm),
      ),
      child: const Center(
        child: Text(
          'P',
          style: TextStyle(
            color: AppColors.textOnPrimary,
            fontSize: 18,
            fontWeight: FontWeight.w800,
          ),
        ),
      ),
    );
  }
}
