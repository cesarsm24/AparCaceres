import 'package:flutter/material.dart';

import '../../../../shared/constants/app_strings.dart';
import '../../../../shared/widgets/app_card.dart';
import '../../../../theme/app_colors.dart';
import '../../../../theme/app_spacing.dart';

/// Acciones de selección de ubicación en la pantalla principal.
///
/// Permite usar la posición actual o abrir el selector para buscar otro punto
/// de referencia dentro de Cáceres.
class LocationActions extends StatelessWidget {
  const LocationActions({
    super.key,
    required this.onUseCurrent,
    required this.onPickLocation,
  });

  final VoidCallback onUseCurrent;
  final VoidCallback onPickLocation;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        _ActionCard(
          icon: Icons.my_location,
          title: AppStrings.homeUseMyLocation,
          caption: AppStrings.homeUseMyLocationCaption,
          onTap: onUseCurrent,
        ),
        const SizedBox(height: AppSpacing.md),
        _ActionCard(
          icon: Icons.place_outlined,
          title: AppStrings.homeSetLocation,
          caption: AppStrings.homeSetLocationCaption,
          onTap: onPickLocation,
        ),
      ],
    );
  }
}

class _ActionCard extends StatelessWidget {
  const _ActionCard({
    required this.icon,
    required this.title,
    required this.caption,
    required this.onTap,
  });

  final IconData icon;
  final String title;
  final String caption;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return AppCard(
      onTap: onTap,
      padding: const EdgeInsets.all(AppSpacing.md),
      child: Row(
        children: [
          Container(
            width: 44,
            height: 44,
            decoration: BoxDecoration(
              color: AppColors.surfaceMuted,
              borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
            ),
            child: Icon(icon, color: AppColors.primary, size: 22),
          ),
          const SizedBox(width: AppSpacing.md),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
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
                  caption,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    fontSize: 12,
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