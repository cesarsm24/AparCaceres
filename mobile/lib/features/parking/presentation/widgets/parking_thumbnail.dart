import 'package:flutter/material.dart';

import '../../../../theme/app_colors.dart';
import '../../../../theme/app_spacing.dart';
import '../../domain/parking_place.dart';
import '../parking_ui.dart';

class ParkingThumbnail extends StatelessWidget {
  const ParkingThumbnail({
    super.key,
    required this.place,
    this.size = 72,
    this.borderRadius = AppSpacing.radiusMd,
  });

  final ParkingPlace place;
  final double size;
  final double borderRadius;

  @override
  Widget build(BuildContext context) {
    final imageUrl = place.imageUrl;
    return ClipRRect(
      borderRadius: BorderRadius.circular(borderRadius),
      child: Container(
        width: size,
        height: size,
        color: AppColors.surfaceMuted,
        child: imageUrl == null || imageUrl.isEmpty
            ? _Placeholder(place: place)
            : Image.network(
                imageUrl,
                fit: BoxFit.cover,
                errorBuilder: (_, _, _) => _Placeholder(place: place),
              ),
      ),
    );
  }
}

class _Placeholder extends StatelessWidget {
  const _Placeholder({required this.place});

  final ParkingPlace place;

  @override
  Widget build(BuildContext context) {
    return Icon(place.category.icon, color: place.category.color, size: 32);
  }
}
