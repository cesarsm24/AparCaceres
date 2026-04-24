import 'package:flutter/material.dart';

import '../features/welcome/presentation/welcome_screen.dart';
import '../shared/constants/app_strings.dart';
import '../theme/app_theme.dart';

class AparCaceresApp extends StatelessWidget {
  const AparCaceresApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: AppStrings.appName,
      debugShowCheckedModeBanner: false,
      theme: AppTheme.light,
      home: const WelcomeScreen(),
    );
  }
}
