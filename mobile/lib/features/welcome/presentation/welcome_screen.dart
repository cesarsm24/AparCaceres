import 'package:flutter/material.dart';

import '../../../shared/constants/app_strings.dart';
import '../../../shared/widgets/primary_button.dart';
import '../../../theme/app_spacing.dart';
import '../../shell/presentation/app_shell.dart';
import 'widgets/welcome_branding.dart';
import 'widgets/welcome_subtitle.dart';

class WelcomeScreen extends StatelessWidget {
  const WelcomeScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.symmetric(
            horizontal: AppSpacing.horizontalPadding,
          ),
          child: Column(
            children: [
              const Spacer(flex: 2),
              const WelcomeBranding(),
              const Spacer(flex: 1),
              const WelcomeSubtitle(),
              const Spacer(flex: 2),
              PrimaryButton(
                label: AppStrings.welcomeCta,
                onPressed: () => Navigator.of(context).pushReplacement(
                  MaterialPageRoute(builder: (_) => const AppShell()),
                ),
              ),
              const SizedBox(height: AppSpacing.lg),
            ],
          ),
        ),
      ),
    );
  }
}
