import 'package:flutter/material.dart';

import '../../../../shared/constants/app_strings.dart';
import '../../../../theme/app_text_styles.dart';

/// Subtítulo de la pantalla de bienvenida.
class WelcomeSubtitle extends StatelessWidget {
  const WelcomeSubtitle({super.key});

  @override
  Widget build(BuildContext context) {
    return const Text(
      AppStrings.welcomeSubtitle,
      textAlign: TextAlign.center,
      style: AppTextStyles.subtitle,
    );
  }
}