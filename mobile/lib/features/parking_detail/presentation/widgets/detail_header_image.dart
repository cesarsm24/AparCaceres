import 'package:flutter/material.dart';

import '../../../../theme/app_colors.dart';
import '../../../parking/domain/parking_place.dart';
import '../../../parking/presentation/parking_ui.dart';

class DetailHeaderImage extends StatelessWidget {
  const DetailHeaderImage({super.key, required this.place});

  final ParkingPlace place;

  @override
  Widget build(BuildContext context) {
    final imageUrl = place.imageUrl;
    return Container(
      height: 220,
      width: double.infinity,
      color: AppColors.surfaceMuted,
      alignment: Alignment.center,
      child: imageUrl == null || imageUrl.isEmpty
          ? Icon(place.category.icon, size: 72, color: place.category.color)
          : Image.network(
              imageUrl,
              width: double.infinity,
              height: 220,
              fit: BoxFit.cover,
              errorBuilder: (_, _, _) => Icon(
                place.category.icon,
                size: 72,
                color: place.category.color,
              ),
            ),
    );
  }
}
