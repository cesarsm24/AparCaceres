import 'package:flutter/material.dart';

import '../../../../shared/constants/app_strings.dart';
import '../../../../theme/app_spacing.dart';
import 'quick_access_card.dart';

class QuickAccessRow extends StatelessWidget {
  const QuickAccessRow({super.key});

  @override
  Widget build(BuildContext context) {
    return const Row(
      children: [
        Expanded(
          child: QuickAccessCard(
            icon: Icons.map_outlined,
            label: AppStrings.quickMap,
          ),
        ),
        SizedBox(width: AppSpacing.md),
        Expanded(
          child: QuickAccessCard(
            icon: Icons.gps_fixed,
            label: AppStrings.quickNearby,
          ),
        ),
        SizedBox(width: AppSpacing.md),
        Expanded(
          child: QuickAccessCard(
            icon: Icons.favorite_border,
            label: AppStrings.quickFavorites,
          ),
        ),
      ],
    );
  }
}
