import 'package:flutter/material.dart';

import '../../../shared/constants/app_strings.dart';
import '../../../theme/app_colors.dart';
import '../../favorites/presentation/favorites_screen.dart';
import '../../home/presentation/home_screen.dart';
import '../../map/presentation/map_screen.dart';
import '../../map/presentation/widgets/filters_drawer.dart';
import '../../routing/data/route_request.dart';
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
  bool _mapInitialFocused = false;

  final GlobalKey<NavigatorState> _homeNav = GlobalKey<NavigatorState>();
  GlobalKey<NavigatorState> _mapNav = GlobalKey<NavigatorState>();
  final GlobalKey<NavigatorState> _favoritesNav = GlobalKey<NavigatorState>();
  final GlobalKey<NavigatorState> _settingsNav = GlobalKey<NavigatorState>();

  List<GlobalKey<NavigatorState>> get _navKeys =>
      [_homeNav, _mapNav, _favoritesNav, _settingsNav];

  @override
  void initState() {
    super.initState();
    routeRequest.addListener(_onRouteRequested);
  }

  @override
  void dispose() {
    routeRequest.removeListener(_onRouteRequested);
    super.dispose();
  }

  void _openMapFromHome(MapFilters filters) {
    setState(() {
      _mapFilters = filters;
      _mapInitialFocused = true;
      _mapRequestVersion++;
      _mapNav = GlobalKey<NavigatorState>();
      _index = 1;
    });
  }

  void _onRouteRequested() {
    if (routeRequest.request == null) return;
    if (_index == 1) return;
    setState(() => _index = 1);
  }

  void _onDestinationSelected(int i) {
    if (i == _index) {
      _navKeys[i].currentState?.popUntil((route) => route.isFirst);
      return;
    }
    setState(() => _index = i);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: IndexedStack(
        index: _index,
        children: [
          _TabNavigator(
            navigatorKey: _homeNav,
            root: HomeScreen(onOpenMap: _openMapFromHome),
          ),
          _TabNavigator(
            key: ValueKey(_mapRequestVersion),
            navigatorKey: _mapNav,
            root: MapScreen(
              initialFilters: _mapFilters,
              initialFocused: _mapInitialFocused,
            ),
          ),
          _TabNavigator(
            navigatorKey: _favoritesNav,
            root: const FavoritesScreen(),
          ),
          _TabNavigator(
            navigatorKey: _settingsNav,
            root: const SettingsScreen(),
          ),
        ],
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        onDestinationSelected: _onDestinationSelected,
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

class _TabNavigator extends StatelessWidget {
  const _TabNavigator({
    super.key,
    required this.navigatorKey,
    required this.root,
  });

  final GlobalKey<NavigatorState> navigatorKey;
  final Widget root;

  @override
  Widget build(BuildContext context) {
    return NavigatorPopHandler(
      onPopWithResult: (_) => navigatorKey.currentState?.maybePop(),
      child: Navigator(
        key: navigatorKey,
        onGenerateRoute: (settings) => MaterialPageRoute(
          settings: settings,
          builder: (_) => root,
        ),
      ),
    );
  }
}
