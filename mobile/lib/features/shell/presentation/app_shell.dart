import 'package:flutter/material.dart';

import '../../../shared/constants/app_strings.dart';
import '../../../theme/app_colors.dart';
import '../../home/presentation/home_screen.dart';
import '../../settings/presentation/settings_screen.dart';
import 'widgets/placeholder_tab.dart';

class AppShell extends StatefulWidget {
  const AppShell({super.key});

  @override
  State<AppShell> createState() => _AppShellState();
}

class _AppShellState extends State<AppShell> {
  int _index = 0;

  static const _tabs = <Widget>[
    HomeScreen(),
    PlaceholderTab(label: AppStrings.navMap, icon: Icons.map_outlined),
    PlaceholderTab(
      label: AppStrings.navFavorites,
      icon: Icons.favorite_border,
    ),
    SettingsScreen(),
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: _tabs[_index],
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        onDestinationSelected: (i) => setState(() => _index = i),
        backgroundColor: AppColors.surface,
        indicatorColor: AppColors.surfaceMuted,
        labelBehavior: NavigationDestinationLabelBehavior.alwaysShow,
        destinations: const [
          NavigationDestination(
            icon: Icon(Icons.home_outlined),
            selectedIcon: Icon(Icons.home, color: AppColors.primary),
            label: AppStrings.navHome,
          ),
          NavigationDestination(
            icon: Icon(Icons.map_outlined),
            selectedIcon: Icon(Icons.map, color: AppColors.primary),
            label: AppStrings.navMap,
          ),
          NavigationDestination(
            icon: Icon(Icons.favorite_border),
            selectedIcon: Icon(Icons.favorite, color: AppColors.primary),
            label: AppStrings.navFavorites,
          ),
          NavigationDestination(
            icon: Icon(Icons.settings_outlined),
            selectedIcon: Icon(Icons.settings, color: AppColors.primary),
            label: AppStrings.navSettings,
          ),
        ],
      ),
    );
  }
}
