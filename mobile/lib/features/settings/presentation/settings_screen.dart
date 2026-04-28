import 'package:flutter/material.dart';

import '../../../shared/widgets/app_top_bar.dart';
import '../../../theme/app_colors.dart';
import '../../../theme/app_spacing.dart';
import '../data/settings_items.dart';
import 'widgets/settings_tile.dart';

class SettingsScreen extends StatelessWidget {
  const SettingsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Container(
      color: AppColors.pageBackground,
      child: Column(
        children: [
          const AppTopBar(),
          Expanded(
            child: ListView.separated(
              padding: const EdgeInsets.fromLTRB(
                AppSpacing.horizontalPadding,
                AppSpacing.md,
                AppSpacing.horizontalPadding,
                AppSpacing.lg,
              ),
              itemCount: kSettings.length,
              separatorBuilder: (_, _) =>
                  const SizedBox(height: AppSpacing.sm),
              itemBuilder: (_, i) => SettingsTile(item: kSettings[i]),
            ),
          ),
        ],
      ),
    );
  }
}
