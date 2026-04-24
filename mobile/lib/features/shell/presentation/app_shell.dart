import 'package:flutter/material.dart';

import '../../../shared/constants/app_strings.dart';
import '../../../theme/app_colors.dart';
import '../../favorites/presentation/favorites_screen.dart';
import '../../home/presentation/home_screen.dart';
import '../../map/presentation/map_screen.dart';
import '../../map/presentation/widgets/filters_drawer.dart';
import '../../settings/presentation/settings_screen.dart';

class AppShell extends StatefulWidget {
  const AppShell({super.key});

  @override
  State<AppShell> createState() => _AppShellState();
}

class _AppShellState extends State<AppShell> {
  int _index = 0;
  int _mapRequestVersion = 0;
  MapFilters _mapFilters = MapFilters();

  void _openMapFromHome(MapFilters filters) {
    setState(() {
      _mapFilters = filters;
      _mapRequestVersion++;
      _index = 1;
    });
  }

  @override
  Widget build(BuildContext context) {
    final tabs = <Widget>[
      HomeScreen(onOpenMap: _openMapFromHome),
      MapScreen(key: ValueKey(_mapRequestVersion), initialFilters: _mapFilters),
      const FavoritesScreen(),
      const SettingsScreen(),
    ];

    return Scaffold(
      body: tabs[_index],
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
