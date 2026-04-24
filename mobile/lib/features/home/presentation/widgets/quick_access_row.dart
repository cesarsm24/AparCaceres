import 'package:flutter/material.dart';

import '../../../../shared/constants/app_strings.dart';
import '../../../../theme/app_spacing.dart';
import '../../../parking/domain/parking_place.dart';
import 'quick_access_card.dart';

class QuickAccessRow extends StatelessWidget {
  const QuickAccessRow({
    super.key,
    required this.onVehicleSelected,
    required this.onAccessibleSelected,
  });

  final ValueChanged<ParkingVehicleType> onVehicleSelected;
  final VoidCallback onAccessibleSelected;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: QuickAccessCard(
            icon: Icons.directions_car_outlined,
            label: AppStrings.quickCar,
            onTap: () => onVehicleSelected(ParkingVehicleType.car),
          ),
        ),
        const SizedBox(width: AppSpacing.md),
        Expanded(
          child: QuickAccessCard(
            icon: Icons.two_wheeler,
            label: AppStrings.quickMotorbike,
            onTap: () => onVehicleSelected(ParkingVehicleType.motorbike),
          ),
        ),
        const SizedBox(width: AppSpacing.md),
        Expanded(
          child: QuickAccessCard(
            icon: Icons.pedal_bike,
            label: AppStrings.quickBike,
            onTap: () => onVehicleSelected(ParkingVehicleType.bike),
          ),
        ),
        const SizedBox(width: AppSpacing.md),
        Expanded(
          child: QuickAccessCard(
            icon: Icons.accessible,
            label: AppStrings.quickAccessible,
            onTap: onAccessibleSelected,
          ),
        ),
      ],
    );
  }
}
