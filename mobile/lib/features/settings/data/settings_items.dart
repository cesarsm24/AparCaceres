import 'package:flutter/material.dart';

import '../../../shared/constants/app_strings.dart';

/// Elemento estático de la pantalla de ajustes.
class SettingItem {
  const SettingItem({required this.icon, required this.label, this.value});

  final IconData icon;
  final String label;
  final String? value;
}

/// Ajustes visibles en la pantalla de configuración.
const List<SettingItem> kSettings = [
  SettingItem(
    icon: Icons.wb_sunny_outlined,
    label: AppStrings.settingTheme,
    value: AppStrings.settingThemeValue,
  ),
  SettingItem(
    icon: Icons.location_on_outlined,
    label: AppStrings.settingLocation,
    value: AppStrings.settingLocationValue,
  ),
  SettingItem(
    icon: Icons.language,
    label: AppStrings.settingLanguage,
    value: AppStrings.settingLanguageValue,
  ),
  SettingItem(
    icon: Icons.notifications_none,
    label: AppStrings.settingNotifications,
  ),
  SettingItem(
    icon: Icons.straighten,
    label: AppStrings.settingDistance,
    value: AppStrings.settingDistanceValue,
  ),
  SettingItem(
    icon: Icons.help_outline,
    label: AppStrings.settingHelp,
  ),
  SettingItem(
    icon: Icons.info_outline,
    label: AppStrings.settingAbout,
    value: AppStrings.settingAboutValue,
  ),
];