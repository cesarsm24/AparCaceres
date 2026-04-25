import 'package:flutter/material.dart';

import '../../../shared/constants/app_strings.dart';
import '../../../shared/widgets/primary_button.dart';
import '../../../theme/app_spacing.dart';
import '../../location/data/location_service.dart';
import '../../shell/presentation/app_shell.dart';
import 'widgets/welcome_branding.dart';
import 'widgets/welcome_subtitle.dart';

class WelcomeScreen extends StatefulWidget {
  const WelcomeScreen({super.key});

  @override
  State<WelcomeScreen> createState() => _WelcomeScreenState();
}

class _WelcomeScreenState extends State<WelcomeScreen> {
  bool _starting = false;

  Future<void> _start() async {
    if (_starting) return;
    setState(() => _starting = true);
    await locationService.ensurePosition();
    if (!mounted) return;
    Navigator.of(context).pushReplacement(
      MaterialPageRoute(builder: (_) => const AppShell()),
    );
  }

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
                onPressed: _starting ? null : _start,
              ),
              const SizedBox(height: AppSpacing.lg),
            ],
          ),
        ),
      ),
    );
  }
}
