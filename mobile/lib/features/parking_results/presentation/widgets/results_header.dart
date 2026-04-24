import 'package:flutter/material.dart';

import '../../../../shared/constants/app_strings.dart';
import '../../../../theme/app_colors.dart';
import '../../../../theme/app_spacing.dart';

enum ResultsSortMode { distance, name, spaces }

extension ResultsSortModeLabel on ResultsSortMode {
  String get label {
    return switch (this) {
      ResultsSortMode.distance => AppStrings.sortByDistance,
      ResultsSortMode.name => AppStrings.sortByName,
      ResultsSortMode.spaces => AppStrings.sortBySpaces,
    };
  }
}

class ResultsHeader extends StatelessWidget {
  const ResultsHeader({
    super.key,
    required this.count,
    required this.sort,
    required this.onSortChanged,
  });

  final int count;
  final ResultsSortMode sort;
  final ValueChanged<ResultsSortMode> onSortChanged;

  @override
  Widget build(BuildContext context) {
    final countLabel = count == 1
        ? '$count ${AppStrings.resultsCountOne}'
        : '$count ${AppStrings.resultsCountMany}';

    return Padding(
      padding: const EdgeInsets.fromLTRB(
        AppSpacing.horizontalPadding,
        AppSpacing.md,
        AppSpacing.sm,
        AppSpacing.sm,
      ),
      child: Row(
        children: [
          Expanded(
            child: Text(
              countLabel,
              style: const TextStyle(
                fontSize: 14,
                fontWeight: FontWeight.w600,
                color: AppColors.textPrimary,
              ),
            ),
          ),
          PopupMenuButton<ResultsSortMode>(
            initialValue: sort,
            onSelected: onSortChanged,
            tooltip: AppStrings.resultsSort,
            itemBuilder: (_) => ResultsSortMode.values
                .map(
                  (mode) => PopupMenuItem<ResultsSortMode>(
                    value: mode,
                    child: Text(mode.label),
                  ),
                )
                .toList(),
            child: Padding(
              padding: const EdgeInsets.symmetric(
                horizontal: AppSpacing.sm,
                vertical: AppSpacing.xs,
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: const [
                  Text(
                    AppStrings.resultsSort,
                    style: TextStyle(
                      fontSize: 14,
                      fontWeight: FontWeight.w600,
                      color: AppColors.primary,
                    ),
                  ),
                  Icon(
                    Icons.keyboard_arrow_down,
                    size: 20,
                    color: AppColors.primary,
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
