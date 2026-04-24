import 'package:flutter/material.dart';

import '../../../../shared/constants/app_assets.dart';

class WelcomeBranding extends StatelessWidget {
  const WelcomeBranding({super.key, this.size = 300});

  final double size;

  @override
  Widget build(BuildContext context) {
    return Image.asset(
      AppAssets.logo,
      width: size,
      height: size,
      fit: BoxFit.contain,
    );
  }
}
