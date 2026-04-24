import 'package:flutter/material.dart';

import '../../../shared/constants/app_strings.dart';
import '../../../shared/widgets/app_top_bar.dart';
import '../../../shared/widgets/section_title.dart';
import '../../../theme/app_colors.dart';
import '../../../theme/app_spacing.dart';
import '../data/home_mock_data.dart';
import 'widgets/home_search_bar.dart';
import 'widgets/nearby_summary_card.dart';
import 'widgets/quick_access_row.dart';
import 'widgets/suggestion_tile.dart';

class HomeScreen extends StatelessWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Container(
      color: AppColors.pageBackground,
      child: Column(
        children: [
          AppTopBar(
            trailing: IconButton(
              onPressed: () {},
              icon: const Icon(
                Icons.notifications_none_rounded,
                color: AppColors.textOnPrimary,
              ),
            ),
          ),
          Expanded(
            child: ListView(
              padding: const EdgeInsets.fromLTRB(
                AppSpacing.horizontalPadding,
                AppSpacing.md,
                AppSpacing.horizontalPadding,
                AppSpacing.lg,
              ),
              children: [
                const HomeSearchBar(),
                const SizedBox(height: AppSpacing.lg),
                const SectionTitle(AppStrings.sectionQuickAccess),
                const SizedBox(height: AppSpacing.md),
                const QuickAccessRow(),
                const SizedBox(height: AppSpacing.lg),
                const NearbySummaryCard(summary: kNearbySummary),
                const SizedBox(height: AppSpacing.lg),
                const SectionTitle(AppStrings.sectionSuggestions),
                const SizedBox(height: AppSpacing.md),
                ...kSuggestions.map(
                  (s) => Padding(
                    padding: const EdgeInsets.only(bottom: AppSpacing.md),
                    child: SuggestionTile(suggestion: s),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
