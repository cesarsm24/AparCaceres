import 'package:flutter/material.dart';

import '../../../../shared/constants/app_strings.dart';
import '../../../../shared/widgets/primary_button.dart';
import '../../../../shared/widgets/secondary_button.dart';
import '../../../../theme/app_colors.dart';
import '../../../../theme/app_spacing.dart';
import '../../../parking/domain/parking_place.dart';
import '../../../parking/presentation/parking_ui.dart';
import '../../../parking/presentation/widgets/parking_thumbnail.dart';

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

    return _SheetShell(
      onTap: onTap,
      child: Row(
        children: [
          const _ResultsBadge(),
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
                  '${AppStrings.mapRadiusPrefix}: $radiusLabel · ${AppStrings.mapAllTypes}',
                  style: const TextStyle(
                    fontSize: 13,
                    color: AppColors.textSecondary,
                  ),
                ),
              ],
            ),
          ),
          const Icon(Icons.chevron_right, color: AppColors.textSecondary),
        ],
      ),
    );
  }
}

class ParkingPreviewSheet extends StatelessWidget {
  const ParkingPreviewSheet({
    super.key,
    required this.place,
    required this.distanceMeters,
    required this.onOpenDetail,
    required this.onClose,
    this.onOpenInMaps,
  });

  final ParkingPlace place;
  final double distanceMeters;
  final VoidCallback onOpenDetail;
  final VoidCallback onClose;
  final VoidCallback? onOpenInMaps;

  @override
  Widget build(BuildContext context) {
    final color = place.category.color;
    final spacesLabel = formatSpaces(place.totalSpaces);
    return _SheetShell(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              ParkingThumbnail(place: place, size: 72),
              const SizedBox(width: AppSpacing.md),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      place.displayName,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        fontSize: 16,
                        fontWeight: FontWeight.w700,
                        color: AppColors.textPrimary,
                      ),
                    ),
                    const SizedBox(height: 3),
                    Text(
                      '${formatDistance(distanceMeters)} · ${place.category.label}',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        fontSize: 13,
                        color: AppColors.textSecondary,
                      ),
                    ),
                    if (spacesLabel != null) ...[
                      const SizedBox(height: 6),
                      Row(
                        children: [
                          Icon(place.category.icon, size: 15, color: color),
                          const SizedBox(width: AppSpacing.xs),
                          Expanded(
                            child: Text(
                              spacesLabel,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: TextStyle(
                                fontSize: 12,
                                fontWeight: FontWeight.w700,
                                color: color,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ],
                  ],
                ),
              ),
              IconButton(
                onPressed: onClose,
                icon: const Icon(Icons.close, color: AppColors.textSecondary),
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.md),
          if (onOpenInMaps != null) ...[
            SecondaryButton(
              label: 'Abrir en Google Maps',
              icon: Icons.open_in_new,
              onPressed: onOpenInMaps,
            ),
            const SizedBox(height: AppSpacing.sm),
          ],
          PrimaryButton(
            label: 'Ver detalle',
            icon: Icons.chevron_right,
            onPressed: onOpenDetail,
          ),
        ],
      ),
    );
  }
}

class _SheetShell extends StatelessWidget {
  const _SheetShell({required this.child, this.onTap});

  final Widget child;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
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
              child,
            ],
          ),
        ),
      ),
    );
  }
}

class _ResultsBadge extends StatelessWidget {
  const _ResultsBadge();

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
        child: Icon(
          Icons.list_alt,
          color: AppColors.textOnPrimary,
          size: 22,
        ),
      ),
    );
  }
}
