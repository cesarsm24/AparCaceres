import 'package:flutter/material.dart';

import '../../../shared/constants/app_strings.dart';
import '../../../shared/widgets/app_top_bar.dart';
import '../../../shared/widgets/primary_button.dart';
import '../../../shared/widgets/secondary_button.dart';
import '../../../theme/app_colors.dart';
import '../../../theme/app_spacing.dart';
import '../../parking/domain/parking_place.dart';
import '../../parking/presentation/parking_ui.dart';
import '../../parking/presentation/widgets/regulation_badge.dart';
import 'widgets/detail_header_image.dart';
import 'widgets/detail_info_row.dart';

class ParkingDetailScreen extends StatelessWidget {
  const ParkingDetailScreen({super.key, required this.place});

  final ParkingPlace place;

  @override
  Widget build(BuildContext context) {
    final street = _joinParts([place.streetType, place.streetName]);
    final area = [place.neighborhood, place.district]
        .where((part) => part != null && part.trim().isNotEmpty)
        .cast<String>()
        .join(' · ');
    final location = street ?? (area.isEmpty ? null : area);
    final spacesLabel = formatSpaces(place.totalSpaces);

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
                DetailHeaderImage(place: place),
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
                        place.displayName,
                        style: const TextStyle(
                          fontSize: 20,
                          fontWeight: FontWeight.w700,
                          color: AppColors.textPrimary,
                        ),
                      ),
                      if (location != null) ...[
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
                                location,
                                style: const TextStyle(
                                  fontSize: 13,
                                  color: AppColors.textSecondary,
                                ),
                              ),
                            ),
                          ],
                        ),
                      ],
                      const SizedBox(height: AppSpacing.md),
                      DetailInfoRow(
                        label: AppStrings.detailType,
                        value: _ValueText(place.category.label),
                      ),
                      DetailInfoRow(
                        label: AppStrings.detailRegulation,
                        value: RegulationBadge(regulation: place.regulation),
                      ),
                      if (spacesLabel != null)
                        DetailInfoRow(
                          label: AppStrings.detailSpaces,
                          value: _ValueText(spacesLabel),
                        ),
                      if (street != null)
                        DetailInfoRow(
                          label: AppStrings.detailStreet,
                          value: _ValueText(street),
                        ),
                      if (area.isNotEmpty)
                        DetailInfoRow(
                          label: AppStrings.detailArea,
                          value: _ValueText(area),
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

String? _joinParts(List<String?> parts) {
  final clean = parts
      .where((part) => part != null && part.trim().isNotEmpty)
      .cast<String>()
      .toList();
  if (clean.isEmpty) return null;
  return clean.join(' ');
}

class _ValueText extends StatelessWidget {
  const _ValueText(this.text);

  final String text;

  @override
  Widget build(BuildContext context) {
    return Text(
      text,
      textAlign: TextAlign.right,
      style: const TextStyle(
        fontSize: 14,
        fontWeight: FontWeight.w600,
        color: AppColors.textPrimary,
      ),
    );
  }
}
