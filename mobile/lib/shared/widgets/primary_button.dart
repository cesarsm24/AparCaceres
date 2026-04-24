import 'package:flutter/material.dart';

class PrimaryButton extends StatelessWidget {
  const PrimaryButton({
    super.key,
    required this.label,
    required this.onPressed,
    this.icon,
  });

  final String label;
  final VoidCallback? onPressed;
  final IconData? icon;

  @override
  Widget build(BuildContext context) {
    if (icon != null) {
      return ElevatedButton.icon(
        onPressed: onPressed,
        icon: Icon(icon, size: 18),
        label: Text(label, textAlign: TextAlign.center),
      );
    }
    return ElevatedButton(
      onPressed: onPressed,
      child: SizedBox(
        width: double.infinity,
        child: Text(label, textAlign: TextAlign.center),
      ),
    );
  }
}
