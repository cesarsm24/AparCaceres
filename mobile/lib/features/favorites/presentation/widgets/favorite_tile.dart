import 'package:flutter/material.dart';

import '../../../../shared/widgets/app_card.dart';
import '../../../../theme/app_colors.dart';
import '../../../../theme/app_spacing.dart';
import '../../data/favorites_mock_data.dart';

class FavoriteTile extends StatelessWidget {
  const FavoriteTile({
    super.key,
    required this.favorite,
    this.onTap,
    this.onToggleFavorite,
  });

  final FavoriteParking favorite;
  final VoidCallback? onTap;
  final VoidCallback? onToggleFavorite;

  @override
  Widget build(BuildContext context) {
    return AppCard(
      onTap: onTap,
      padding: const EdgeInsets.all(AppSpacing.sm),
      child: Row(
        children: [
          _Thumbnail(icon: favorite.thumbnailIcon),
          const SizedBox(width: AppSpacing.md),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  favorite.name,
                  style: const TextStyle(
                    fontSize: 15,
                    fontWeight: FontWeight.w700,
                    color: AppColors.textPrimary,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  '${favorite.distance}  ·  ${favorite.priceLabel}',
                  style: const TextStyle(
                    fontSize: 13,
                    color: AppColors.textSecondary,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  '${favorite.freeSpots} plazas libres',
                  style: const TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                    color: AppColors.success,
                  ),
                ),
              ],
            ),
          ),
          IconButton(
            onPressed: onToggleFavorite,
            icon: const Icon(Icons.favorite, color: AppColors.primary),
          ),
        ],
      ),
    );
  }
}

class _Thumbnail extends StatelessWidget {
  const _Thumbnail({required this.icon});

  final IconData icon;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 72,
      height: 72,
      decoration: BoxDecoration(
        color: AppColors.surfaceMuted,
        borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
      ),
      child: Icon(icon, color: AppColors.accent, size: 32),
    );
  }
}
