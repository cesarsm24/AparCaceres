import 'package:flutter/material.dart';

import '../../../shared/constants/app_strings.dart';
import '../../../shared/widgets/app_top_bar.dart';
import '../../../theme/app_colors.dart';
import '../../../theme/app_spacing.dart';
import '../../parking_detail/data/parking_detail_mock_data.dart';
import '../../parking_detail/presentation/parking_detail_screen.dart';
import '../data/favorites_mock_data.dart';
import 'widgets/favorite_tile.dart';

class FavoritesScreen extends StatelessWidget {
  const FavoritesScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Container(
      color: AppColors.pageBackground,
      child: Column(
        children: [
          AppTopBar(
            trailing: TextButton(
              onPressed: () {},
              child: const Text(
                AppStrings.favoritesEdit,
                style: TextStyle(
                  color: AppColors.textOnPrimary,
                  fontSize: 15,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
          ),
          Expanded(
            child: ListView.separated(
              padding: const EdgeInsets.fromLTRB(
                AppSpacing.horizontalPadding,
                AppSpacing.md,
                AppSpacing.horizontalPadding,
                AppSpacing.lg,
              ),
              itemCount: kFavorites.length,
              separatorBuilder: (_, _) =>
                  const SizedBox(height: AppSpacing.md),
              itemBuilder: (_, i) => FavoriteTile(
                favorite: kFavorites[i],
                onTap: () => Navigator.of(context).push(
                  MaterialPageRoute(
                    builder: (_) => const ParkingDetailScreen(
                      detail: kParkingDetailSample,
                    ),
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
