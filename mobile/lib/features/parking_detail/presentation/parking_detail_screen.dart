import 'package:flutter/material.dart';

import '../../../shared/constants/app_strings.dart';
import '../../../shared/widgets/app_top_bar.dart';
import '../../../shared/widgets/primary_button.dart';
import '../../../shared/widgets/secondary_button.dart';
import '../../../theme/app_colors.dart';
import '../../../theme/app_spacing.dart';
import '../data/parking_detail_mock_data.dart';
import 'widgets/detail_header_image.dart';
import 'widgets/detail_info_row.dart';
import 'widgets/price_badge.dart';
import 'widgets/service_chip.dart';

class ParkingDetailScreen extends StatelessWidget {
  const ParkingDetailScreen({super.key, required this.detail});

  final ParkingDetail detail;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      body: Column(
        children: [
          AppTopBar(
            leading: IconButton(
              onPressed: () => Navigator.of(context).maybePop(),
              icon: const Icon(
                Icons.chevron_left,
                color: AppColors.textOnPrimary,
                size: 28,
              ),
            ),
            trailing: IconButton(
              onPressed: () {},
              icon: const Icon(
                Icons.favorite_border,
                color: AppColors.textOnPrimary,
              ),
            ),
          ),
          Expanded(
            child: ListView(
              padding: EdgeInsets.zero,
              children: [
                DetailHeaderImage(icon: detail.headerIcon),
                Padding(
                  padding: const EdgeInsets.fromLTRB(
                    AppSpacing.horizontalPadding,
                    AppSpacing.md,
                    AppSpacing.horizontalPadding,
                    AppSpacing.lg,
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        detail.name,
                        style: const TextStyle(
                          fontSize: 20,
                          fontWeight: FontWeight.w700,
                          color: AppColors.textPrimary,
                        ),
                      ),
                      const SizedBox(height: AppSpacing.xs),
                      Row(
                        children: [
                          const Icon(
                            Icons.location_on_outlined,
                            size: 16,
                            color: AppColors.textSecondary,
                          ),
                          const SizedBox(width: AppSpacing.xs),
                          Expanded(
                            child: Text(
                              detail.address,
                              style: const TextStyle(
                                fontSize: 13,
                                color: AppColors.textSecondary,
                              ),
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: AppSpacing.md),
                      DetailInfoRow(
                        label: AppStrings.detailType,
                        value: PriceBadge(
                          label: detail.type,
                          isPaid: detail.isPaid,
                        ),
                      ),
                      DetailInfoRow(
                        label: AppStrings.detailSchedule,
                        value: Text(
                          detail.schedule,
                          style: const TextStyle(
                            fontSize: 14,
                            fontWeight: FontWeight.w600,
                            color: AppColors.textPrimary,
                          ),
                        ),
                      ),
                      DetailInfoRow(
                        label: AppStrings.detailRate,
                        value: Text(
                          detail.rate,
                          textAlign: TextAlign.right,
                          style: const TextStyle(
                            fontSize: 14,
                            fontWeight: FontWeight.w600,
                            color: AppColors.textPrimary,
                          ),
                        ),
                      ),
                      DetailInfoRow(
                        label: AppStrings.detailFreeSpots,
                        value: Text(
                          '${detail.freeSpots} / ${detail.totalSpots}',
                          style: const TextStyle(
                            fontSize: 14,
                            fontWeight: FontWeight.w700,
                            color: AppColors.success,
                          ),
                        ),
                      ),
                      DetailInfoRow(
                        label: AppStrings.detailServices,
                        value: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            for (final s in detail.services) ...[
                              ServiceChip(icon: s),
                              const SizedBox(width: AppSpacing.xs),
                            ],
                          ],
                        ),
                      ),
                      const SizedBox(height: AppSpacing.lg),
                      Row(
                        children: [
                          Expanded(
                            child: SecondaryButton(
                              label: AppStrings.detailNavigate,
                              icon: Icons.send_outlined,
                              onPressed: () {},
                            ),
                          ),
                          const SizedBox(width: AppSpacing.md),
                          Expanded(
                            child: PrimaryButton(
                              label: AppStrings.detailSave,
                              icon: Icons.favorite,
                              onPressed: () {},
                            ),
                          ),
                        ],
                      ),
                    ],
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
