import 'package:flutter/material.dart';

import '../../../../theme/app_colors.dart';

class ParkingMapMarker extends StatelessWidget {
  const ParkingMapMarker({super.key, this.isPaid = true});

  final bool isPaid;

  @override
  Widget build(BuildContext context) {
    final color = isPaid ? AppColors.primary : AppColors.success;
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 36,
          height: 36,
          decoration: BoxDecoration(
            color: color,
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
          child: const Center(
            child: Text(
              'P',
              style: TextStyle(
                color: AppColors.textOnPrimary,
                fontSize: 16,
                fontWeight: FontWeight.w800,
              ),
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
