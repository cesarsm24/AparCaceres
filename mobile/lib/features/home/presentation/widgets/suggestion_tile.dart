import 'package:flutter/material.dart';

import '../../../../shared/widgets/app_card.dart';
import '../../../../theme/app_colors.dart';
import '../../../../theme/app_spacing.dart';
import '../../../parking/domain/parking_place.dart';
import '../../../parking/presentation/parking_ui.dart';
import '../../../parking/presentation/widgets/parking_thumbnail.dart';

class SuggestionTile extends StatelessWidget {
  const SuggestionTile({
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
    final color = place.category.color;
    final spacesLabel = formatSpaces(place.totalSpaces);
    return AppCard(
      onTap: onTap,
      padding: const EdgeInsets.all(AppSpacing.sm),
      child: Row(
        children: [
          ParkingThumbnail(place: place, size: 64),
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
                    fontSize: 15,
                    fontWeight: FontWeight.w700,
                    color: AppColors.textPrimary,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  '${formatDistance(distanceMeters)}  ·  ${place.category.label}',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    fontSize: 13,
                    color: AppColors.textSecondary,
                  ),
                ),
                if (spacesLabel != null) ...[
                  const SizedBox(height: 4),
                  Row(
                    children: [
                      Icon(place.vehicleType.icon, size: 14, color: color),
                      const SizedBox(width: AppSpacing.xs),
                      Expanded(
                        child: Text(
                          spacesLabel,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            fontSize: 12,
                            fontWeight: FontWeight.w600,
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
          const Icon(Icons.chevron_right, color: AppColors.textSecondary),
        ],
      ),
    );
  }
}
