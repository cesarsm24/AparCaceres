import 'package:flutter/material.dart';

import '../../../../theme/app_colors.dart';

class DetailHeaderImage extends StatelessWidget {
  const DetailHeaderImage({super.key, required this.icon});

  final IconData icon;

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 220,
      width: double.infinity,
      color: AppColors.surfaceMuted,
      alignment: Alignment.center,
      child: Icon(icon, size: 72, color: AppColors.accent),
    );
  }
}
