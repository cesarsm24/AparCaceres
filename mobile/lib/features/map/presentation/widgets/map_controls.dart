import 'package:flutter/material.dart';

import '../../../../theme/app_colors.dart';
import '../../../../theme/app_spacing.dart';

class MapControls extends StatelessWidget {
  const MapControls({
    super.key,
    required this.onLocate,
    required this.onZoomIn,
    required this.onZoomOut,
  });

  final VoidCallback onLocate;
  final VoidCallback onZoomIn;
  final VoidCallback onZoomOut;

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        _ControlButton(icon: Icons.gps_fixed, onPressed: onLocate),
        const SizedBox(height: AppSpacing.md),
        _ControlGroup(
          children: [
            _ControlButton(
              icon: Icons.add,
              onPressed: onZoomIn,
              rounded: false,
            ),
            const Divider(height: 1, color: AppColors.border),
            _ControlButton(
              icon: Icons.remove,
              onPressed: onZoomOut,
              rounded: false,
            ),
          ],
        ),
      ],
    );
  }
}

class _ControlGroup extends StatelessWidget {
  const _ControlGroup({required this.children});

  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
        boxShadow: const [
          BoxShadow(
            color: Color(0x22000000),
            blurRadius: 6,
            offset: Offset(0, 2),
          ),
        ],
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
        child: Column(mainAxisSize: MainAxisSize.min, children: children),
      ),
    );
  }
}

class _ControlButton extends StatelessWidget {
  const _ControlButton({
    required this.icon,
    required this.onPressed,
    this.rounded = true,
  });

  final IconData icon;
  final VoidCallback onPressed;
  final bool rounded;

  @override
  Widget build(BuildContext context) {
    final button = Material(
      color: AppColors.surface,
      child: InkWell(
        onTap: onPressed,
        child: SizedBox(
          width: 44,
          height: 44,
          child: Icon(icon, color: AppColors.textPrimary, size: 22),
        ),
      ),
    );

    if (!rounded) return button;

    return Container(
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
        boxShadow: const [
          BoxShadow(
            color: Color(0x22000000),
            blurRadius: 6,
            offset: Offset(0, 2),
          ),
        ],
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
        child: button,
      ),
    );
  }
}
