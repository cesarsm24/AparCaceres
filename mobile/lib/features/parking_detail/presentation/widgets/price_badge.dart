import 'package:flutter/material.dart';

import '../../../../theme/app_colors.dart';
import '../../../../theme/app_spacing.dart';

class PriceBadge extends StatelessWidget {
  const PriceBadge({super.key, required this.label, required this.isPaid});

  final String label;
  final bool isPaid;

  @override
  Widget build(BuildContext context) {
    final color = isPaid ? AppColors.primary : AppColors.success;
    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.md,
        vertical: 6,
      ),
      decoration: BoxDecoration(
        color: color,
        borderRadius: BorderRadius.circular(AppSpacing.radiusPill),
      ),
      child: Text(
        label,
        style: const TextStyle(
          color: AppColors.textOnPrimary,
          fontSize: 13,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }
}
