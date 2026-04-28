import 'package:flutter/material.dart';

import '../../../../theme/app_colors.dart';
import '../../../parking/domain/parking_place.dart';
import '../../../parking/presentation/parking_ui.dart';

/// Marcador de aparcamiento para el mapa.
///
/// Usa el color y el icono de la categoría para identificar el tipo de plaza;
/// el estado seleccionado aumenta tamaño y borde para destacar el elemento.
class ParkingMapMarker extends StatelessWidget {
  const ParkingMapMarker({
    super.key,
    required this.category,
    this.isSelected = false,
  });

  final ParkingCategory category;
  final bool isSelected;

  @override
  Widget build(BuildContext context) {
    final color = category.color;

    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: isSelected ? 42 : 36,
          height: isSelected ? 42 : 36,
          decoration: BoxDecoration(
            color: color,
            shape: BoxShape.circle,
            border: Border.all(
              color: AppColors.textOnPrimary,
              width: isSelected ? 3 : 2,
            ),
            boxShadow: const [
              BoxShadow(
                color: Color(0x33000000),
                blurRadius: 4,
                offset: Offset(0, 2),
              ),
            ],
          ),
          child: Center(
            child: Icon(
              category.icon,
              color: AppColors.textOnPrimary,
              size: isSelected ? 22 : 19,
            ),
          ),
        ),
        Padding(
          padding: const EdgeInsets.only(top: 1),
          child: CustomPaint(
            size: const Size(10, 8),
            painter: _MarkerTipPainter(color),
          ),
        ),
      ],
    );
  }
}

class _MarkerTipPainter extends CustomPainter {
  _MarkerTipPainter(this.color);

  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()..color = color;
    final path = Path()
      ..moveTo(0, 0)
      ..lineTo(size.width / 2, size.height)
      ..lineTo(size.width, 0)
      ..close();

    canvas.drawPath(path, paint);
  }

  @override
  bool shouldRepaint(covariant _MarkerTipPainter oldDelegate) =>
      oldDelegate.color != color;
}

/// Marcador de la posición activa del usuario.
class UserLocationMarker extends StatelessWidget {
  const UserLocationMarker({super.key});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 22,
      height: 22,
      decoration: BoxDecoration(
        color: AppColors.accent,
        shape: BoxShape.circle,
        border: Border.all(color: AppColors.textOnPrimary, width: 3),
        boxShadow: const [
          BoxShadow(
            color: Color(0x33000000),
            blurRadius: 4,
            offset: Offset(0, 2),
          ),
        ],
      ),
    );
  }
}

/// Marcador del destino manual elegido en el selector de ubicación.
class DestinationPinMarker extends StatelessWidget {
  const DestinationPinMarker({super.key});

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 30,
          height: 30,
          decoration: BoxDecoration(
            color: AppColors.primary,
            shape: BoxShape.circle,
            border: Border.all(color: AppColors.textOnPrimary, width: 2),
            boxShadow: const [
              BoxShadow(
                color: Color(0x33000000),
                blurRadius: 4,
                offset: Offset(0, 2),
              ),
            ],
          ),
          child: const Icon(
            Icons.place,
            color: AppColors.textOnPrimary,
            size: 18,
          ),
        ),
        Padding(
          padding: const EdgeInsets.only(top: 1),
          child: CustomPaint(
            size: const Size(8, 7),
            painter: _MarkerTipPainter(AppColors.primary),
          ),
        ),
      ],
    );
  }
}