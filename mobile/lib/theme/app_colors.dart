import 'package:flutter/material.dart';

/// Paleta de color compartida por la aplicación.
///
/// Agrupa los colores semánticos usados por temas y widgets para evitar
/// literales dispersos en la interfaz.
class AppColors {
  const AppColors._();

  static const Color primary = Color(0xFF1E40AF);
  static const Color primaryDark = Color(0xFF1B3A99);
  static const Color accent = Color(0xFF3B82F6);
  static const Color accentLight = Color(0xFF60A5FA);

  static const Color background = Color(0xFFFFFFFF);
  static const Color surface = Color(0xFFFFFFFF);

  static const Color textPrimary = Color(0xFF111827);
  static const Color textSecondary = Color(0xFF6B7280);
  static const Color textOnPrimary = Color(0xFFFFFFFF);

  static const Color border = Color(0xFFE5E7EB);
  static const Color surfaceMuted = Color(0xFFF3F4F6);
  static const Color pageBackground = Color(0xFFF9FAFB);

  static const Color success = Color(0xFF10B981);
}