import 'package:flutter/material.dart';

import '../../core/network/api_exceptions.dart';
import '../../theme/app_colors.dart';
import '../../theme/app_spacing.dart';
import 'secondary_button.dart';

/// Pantalla compacta de fallo cuando una llamada al backend revienta. Mapea
/// la jerarquía de [ApiException] a copy en español:
///   - [ApiTimeoutException] / [ApiUnavailableException]: el problema es la
///     red o el servidor; el usuario solo puede reintentar.
///   - Resto de [ApiException]: lo más probable es un 4xx que no debería
///     ocurrir desde la app, pero mostramos el detalle para no esconder bugs.
///   - Otros (no [ApiException]): mensaje genérico para no filtrar el
///     `toString()` de excepciones que la UI no entiende.
///
/// Se diseña pequeño a propósito (icono + dos líneas + botón) para que encaje
/// como un `Center` dentro de cualquier área de contenido.
class ApiErrorState extends StatelessWidget {
  const ApiErrorState({super.key, required this.error, required this.onRetry});

  final Object error;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final copy = _copyFor(error);
    return Padding(
      padding: const EdgeInsets.all(AppSpacing.xl),
      child: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(copy.icon, size: 40, color: AppColors.textSecondary),
            const SizedBox(height: AppSpacing.md),
            Text(
              copy.title,
              textAlign: TextAlign.center,
              style: const TextStyle(
                fontSize: 16,
                fontWeight: FontWeight.w700,
                color: AppColors.textPrimary,
              ),
            ),
            const SizedBox(height: AppSpacing.xs),
            Text(
              copy.body,
              textAlign: TextAlign.center,
              style: const TextStyle(
                fontSize: 13,
                color: AppColors.textSecondary,
              ),
            ),
            const SizedBox(height: AppSpacing.lg),
            SizedBox(
              width: 200,
              child: SecondaryButton(
                label: 'Reintentar',
                icon: Icons.refresh,
                onPressed: onRetry,
              ),
            ),
          ],
        ),
      ),
    );
  }

  _ErrorCopy _copyFor(Object error) {
    if (error is ApiTimeoutException) {
      return const _ErrorCopy(
        icon: Icons.hourglass_empty_rounded,
        title: 'La conexión está tardando demasiado',
        body: 'Comprueba tu red y vuelve a intentarlo.',
      );
    }
    if (error is ApiUnavailableException) {
      return const _ErrorCopy(
        icon: Icons.cloud_off_rounded,
        title: 'Servicio no disponible',
        body:
            'No hemos podido contactar con el servidor de aparcamientos. '
            'Inténtalo de nuevo en unos segundos.',
      );
    }
    if (error is ApiException) {
      return _ErrorCopy(
        icon: Icons.error_outline,
        title: 'No hemos podido cargar los aparcamientos',
        body: error.message,
      );
    }
    return const _ErrorCopy(
      icon: Icons.error_outline,
      title: 'Algo ha fallado',
      body: 'Vuelve a intentarlo en unos segundos.',
    );
  }
}

class _ErrorCopy {
  const _ErrorCopy({required this.icon, required this.title, required this.body});

  final IconData icon;
  final String title;
  final String body;
}
