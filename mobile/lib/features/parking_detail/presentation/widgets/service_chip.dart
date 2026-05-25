import 'package:flutter/material.dart';

import '../../../../theme/app_colors.dart';
import '../../../../theme/app_spacing.dart';

/// Chip visual para representar un servicio o atributo del aparcamiento.
class ServiceChip extends StatelessWidget {
  const ServiceChip({super.key, required this.icon});

  final IconData icon;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 40,
      height: 40,
      decoration: BoxDecoration(
        color: AppColors.surface,
        border: Border.all(color: AppColors.border),
        borderRadius: BorderRadius.circular(AppSpacing.radiusSm),
      ),
      alignment: Alignment.center,
      child: Icon(icon, size: 20, color: AppColors.textPrimary),
    );
  }
}