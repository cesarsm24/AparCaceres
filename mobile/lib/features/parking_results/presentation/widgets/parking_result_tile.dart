import 'package:flutter/material.dart';

import '../../../../shared/widgets/app_card.dart';
import '../../../../theme/app_colors.dart';
import '../../../../theme/app_spacing.dart';
import '../../../parking/domain/parking_place.dart';
import '../../../parking/presentation/parking_ui.dart';
import '../../../parking/presentation/widgets/parking_thumbnail.dart';
import '../../../parking/presentation/widgets/regulation_badge.dart';

class ParkingResultTile extends StatelessWidget {
  const ParkingResultTile({
    super.key,
    required this.place,
    required this.distanceMeters,
    this.onTap,
  });

  final ParkingPlace place;
  final double distanceMeters;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final spacesLabel = formatSpaces(place.totalSpaces);
    final subtitle = [
      formatDistance(distanceMeters),
      place.category.label,
    ].join('  ·  ');

    return AppCard(
      onTap: onTap,
      padding: const EdgeInsets.all(AppSpacing.sm),
      child: Row(
        children: [
          ParkingThumbnail(place: place),
          const SizedBox(width: AppSpacing.md),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(
                      child: Text(
                        place.displayName,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          fontSize: 15,
                          fontWeight: FontWeight.w700,
                          color: AppColors.textPrimary,
                        ),
                      ),
                    ),
                    const SizedBox(width: AppSpacing.sm),
                    RegulationBadge(regulation: place.regulation),
                  ],
                ),
                const SizedBox(height: 4),
                Text(
                  subtitle,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    fontSize: 13,
                    color: AppColors.textSecondary,
                  ),
                ),
                if (spacesLabel != null) ...[
                  const SizedBox(height: 4),
                  Text(
                    spacesLabel,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                      color: place.category.color,
                    ),
                  ),
                ],
              ],
            ),
          ),
          const SizedBox(width: AppSpacing.sm),
          const Icon(Icons.chevron_right, color: AppColors.textSecondary),
        ],
      ),
    );
  }
}
