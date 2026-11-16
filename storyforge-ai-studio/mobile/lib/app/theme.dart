import 'package:flutter/material.dart';

/// StoryForge design tokens. Dark-first neutral canvas with one warm accent.
abstract final class SfColors {
  static const canvas = Color(0xFF0E0E10);
  static const surface = Color(0xFF17171A);
  static const surfaceRaised = Color(0xFF202024);
  static const outline = Color(0xFF2E2E34);
  static const textPrimary = Color(0xFFF3F1EE);
  static const textSecondary = Color(0xFFA9A6A1);
  static const accent = Color(0xFFFF8A3D); // warm amber-orange
  static const accentDeep = Color(0xFFE5622A);
  static const onAccent = Color(0xFF1A0E06);
  static const success = Color(0xFF5BC98C);
  static const warning = Color(0xFFF2C14E);
  static const danger = Color(0xFFFF6B6B);
}

abstract final class SfSpace {
  static const xs = 4.0;
  static const sm = 8.0;
  static const md = 16.0;
  static const lg = 24.0;
  static const xl = 32.0;
  static const xxl = 48.0;
}

abstract final class SfRadius {
  static const sm = 8.0;
  static const md = 14.0;
  static const lg = 22.0;
}

/// Restrained warm gradient used only for the primary call to action and hero art.
const sfAccentGradient = LinearGradient(
  begin: Alignment.topLeft,
  end: Alignment.bottomRight,
  colors: [SfColors.accent, SfColors.accentDeep],
);

ThemeData buildSfTheme() {
  final scheme = const ColorScheme.dark(
    primary: SfColors.accent,
    onPrimary: SfColors.onAccent,
    secondary: SfColors.accent,
    surface: SfColors.surface,
    onSurface: SfColors.textPrimary,
    surfaceContainerHighest: SfColors.surfaceRaised,
    outline: SfColors.outline,
    error: SfColors.danger,
  );

  const text = TextTheme(
    displaySmall: TextStyle(fontSize: 32, fontWeight: FontWeight.w700, letterSpacing: -0.6, height: 1.15),
    headlineSmall: TextStyle(fontSize: 24, fontWeight: FontWeight.w700, letterSpacing: -0.3),
    titleLarge: TextStyle(fontSize: 20, fontWeight: FontWeight.w600),
    titleMedium: TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
    bodyLarge: TextStyle(fontSize: 16, height: 1.45),
    bodyMedium: TextStyle(fontSize: 14, height: 1.45, color: SfColors.textSecondary),
    labelLarge: TextStyle(fontSize: 15, fontWeight: FontWeight.w600, letterSpacing: 0.1),
    labelSmall: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, letterSpacing: 0.4),
  );

  final base = ThemeData(useMaterial3: true, colorScheme: scheme, brightness: Brightness.dark);
  return base.copyWith(
    scaffoldBackgroundColor: SfColors.canvas,
    textTheme: base.textTheme.merge(text).apply(bodyColor: SfColors.textPrimary, displayColor: SfColors.textPrimary),
    appBarTheme: const AppBarTheme(
      backgroundColor: SfColors.canvas,
      elevation: 0,
      scrolledUnderElevation: 0,
      centerTitle: false,
    ),
    cardTheme: CardThemeData(
      color: SfColors.surface,
      elevation: 0,
      margin: EdgeInsets.zero,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(SfRadius.md),
        side: const BorderSide(color: SfColors.outline),
      ),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        minimumSize: const Size(64, 52),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(SfRadius.md)),
        textStyle: text.labelLarge,
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        minimumSize: const Size(64, 48),
        foregroundColor: SfColors.textPrimary,
        side: const BorderSide(color: SfColors.outline),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(SfRadius.md)),
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: SfColors.surface,
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(SfRadius.md),
        borderSide: const BorderSide(color: SfColors.outline),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(SfRadius.md),
        borderSide: const BorderSide(color: SfColors.outline),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(SfRadius.md),
        borderSide: const BorderSide(color: SfColors.accent, width: 1.5),
      ),
    ),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: SfColors.surface,
      indicatorColor: SfColors.accent.withValues(alpha: 0.18),
      labelTextStyle: WidgetStatePropertyAll(text.labelSmall),
      height: 68,
    ),
    dividerTheme: const DividerThemeData(color: SfColors.outline, space: 1),
    snackBarTheme: const SnackBarThemeData(behavior: SnackBarBehavior.floating),
  );
}
