import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../theme/app_colors.dart';
import '../constants/app_strings.dart';

/// Barra superior común de la aplicación.
///
/// Respeta el área segura del sistema, aplica el estilo de estado coherente
/// con el color primario y permite inyectar acciones laterales opcionales.
class AppTopBar extends StatelessWidget {
  const AppTopBar({
    super.key,
    this.title = AppStrings.appName,
    this.leading,
    this.trailing,
  });

  final String title;
  final Widget? leading;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    final topPadding = MediaQuery.of(context).padding.top;

    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: SystemUiOverlayStyle.light.copyWith(
        statusBarColor: AppColors.primary,
      ),
      child: Container(
        width: double.infinity,
        color: AppColors.primary,
        padding: EdgeInsets.only(top: topPadding),
        child: SizedBox(
          height: 60,
          width: double.infinity,
          child: Stack(
            alignment: Alignment.center,
            children: [
              Text(
                title,
                style: const TextStyle(
                  color: AppColors.textOnPrimary,
                  fontSize: 20,
                  fontWeight: FontWeight.w700,
                ),
              ),
              if (leading != null)
                Align(
                  alignment: Alignment.centerLeft,
                  child: Padding(
                    padding: const EdgeInsets.only(left: 4),
                    child: leading!,
                  ),
                ),
              if (trailing != null)
                Align(
                  alignment: Alignment.centerRight,
                  child: Padding(
                    padding: const EdgeInsets.only(right: 4),
                    child: trailing!,
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}