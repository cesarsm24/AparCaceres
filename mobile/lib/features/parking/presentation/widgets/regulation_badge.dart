import 'package:flutter/material.dart';

import '../../../../theme/app_colors.dart';
import '../../../../theme/app_spacing.dart';
import '../../domain/parking_place.dart';
import '../parking_ui.dart';

class RegulationBadge extends StatelessWidget {
  const RegulationBadge({super.key, required this.regulation});

  final ParkingRegulation regulation;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.md,
        vertical: 6,
      ),
      decoration: BoxDecoration(
        color: regulation.color,
        borderRadius: BorderRadius.circular(AppSpacing.radiusPill),
      ),
      child: Text(
        regulation.label,
        style: const TextStyle(
          color: AppColors.textOnPrimary,
          fontSize: 13,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }
}
