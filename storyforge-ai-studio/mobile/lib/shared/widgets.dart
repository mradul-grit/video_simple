import 'package:flutter/material.dart';

import '../app/theme.dart';

/// Full-area loading state with a short label (screen readers announce it).
class LoadingView extends StatelessWidget {
  const LoadingView({super.key, this.label = 'Loading'});
  final String label;

  @override
  Widget build(BuildContext context) => Center(
    child: Semantics(
      label: label,
      liveRegion: true,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const SizedBox.square(dimension: 28, child: CircularProgressIndicator(strokeWidth: 2.5)),
          const SizedBox(height: SfSpace.md),
          Text(label, style: Theme.of(context).textTheme.bodyMedium),
        ],
      ),
    ),
  );
}

/// Empty or error state: icon, title, explanation and at most one real action.
class MessageView extends StatelessWidget {
  const MessageView({
    super.key,
    required this.icon,
    required this.title,
    required this.message,
    this.actionLabel,
    this.onAction,
    this.isError = false,
  });

  final IconData icon;
  final String title;
  final String message;
  final String? actionLabel;
  final VoidCallback? onAction;
  final bool isError;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(SfSpace.xl),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              padding: const EdgeInsets.all(SfSpace.md),
              decoration: BoxDecoration(
                color: (isError ? SfColors.danger : SfColors.accent).withValues(alpha: 0.12),
                shape: BoxShape.circle,
              ),
              child: Icon(icon, size: 32, color: isError ? SfColors.danger : SfColors.accent),
            ),
            const SizedBox(height: SfSpace.md),
            Text(title, style: t.titleLarge, textAlign: TextAlign.center),
            const SizedBox(height: SfSpace.sm),
            Text(message, style: t.bodyMedium, textAlign: TextAlign.center),
            if (actionLabel != null && onAction != null) ...[
              const SizedBox(height: SfSpace.lg),
              OutlinedButton(onPressed: onAction, child: Text(actionLabel!)),
            ],
          ],
        ),
      ),
    );
  }
}

class ErrorView extends StatelessWidget {
  const ErrorView({super.key, required this.error, this.onRetry});
  final Object error;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) => MessageView(
    icon: Icons.cloud_off_rounded,
    title: "Couldn't load this",
    message: error.toString(),
    actionLabel: onRetry == null ? null : 'Try again',
    onAction: onRetry,
    isError: true,
  );
}

enum PillTone { neutral, progress, success, warning, danger }

class StatusPill extends StatelessWidget {
  const StatusPill(this.label, {super.key, this.tone = PillTone.neutral});
  final String label;
  final PillTone tone;

  @override
  Widget build(BuildContext context) {
    final c = switch (tone) {
      PillTone.neutral => SfColors.textSecondary,
      PillTone.progress => SfColors.accent,
      PillTone.success => SfColors.success,
      PillTone.warning => SfColors.warning,
      PillTone.danger => SfColors.danger,
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(color: c.withValues(alpha: 0.14), borderRadius: BorderRadius.circular(99)),
      child: Text(label, style: Theme.of(context).textTheme.labelSmall?.copyWith(color: c)),
    );
  }
}

/// Shown wherever mock providers produced the data, so demo output is never mistaken for real AI.
class DemoBanner extends StatelessWidget {
  const DemoBanner({super.key});

  @override
  Widget build(BuildContext context) => Semantics(
    container: true,
    label: 'Demo mode. The transcript and suggestions are placeholder data, not real AI output.',
    child: Container(
      padding: const EdgeInsets.all(SfSpace.md),
      decoration: BoxDecoration(
        color: SfColors.warning.withValues(alpha: 0.10),
        borderRadius: BorderRadius.circular(SfRadius.md),
        border: Border.all(color: SfColors.warning.withValues(alpha: 0.35)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Icon(Icons.science_outlined, color: SfColors.warning, size: 20),
          const SizedBox(width: SfSpace.sm),
          Expanded(
            child: ExcludeSemantics(
              child: Text(
                'Demo mode: the server is using placeholder transcription and story analysis. '
                'Text marked [DEMO] is not from your video.',
                style: Theme.of(context).textTheme.bodyMedium?.copyWith(color: SfColors.textPrimary),
              ),
            ),
          ),
        ],
      ),
    ),
  );
}

/// The one visually dominant action on a screen.
class PrimaryButton extends StatelessWidget {
  const PrimaryButton({super.key, required this.label, required this.onPressed, this.icon, this.busy = false});
  final String label;
  final VoidCallback? onPressed;
  final IconData? icon;
  final bool busy;

  @override
  Widget build(BuildContext context) {
    final enabled = onPressed != null && !busy;
    return Semantics(
      button: true,
      enabled: enabled,
      label: label,
      child: Opacity(
        opacity: enabled ? 1 : 0.5,
        child: DecoratedBox(
          decoration: BoxDecoration(gradient: sfAccentGradient, borderRadius: BorderRadius.circular(SfRadius.md)),
          child: Material(
            type: MaterialType.transparency,
            child: InkWell(
              borderRadius: BorderRadius.circular(SfRadius.md),
              onTap: enabled ? onPressed : null,
              child: SizedBox(
                height: 56,
                child: Center(
                  child: ExcludeSemantics(
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        if (busy)
                          const SizedBox.square(
                            dimension: 18,
                            child: CircularProgressIndicator(strokeWidth: 2, color: SfColors.onAccent),
                          )
                        else if (icon != null)
                          Icon(icon, color: SfColors.onAccent),
                        const SizedBox(width: SfSpace.sm),
                        Text(label, style: Theme.of(context).textTheme.labelLarge?.copyWith(color: SfColors.onAccent)),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class SectionHeader extends StatelessWidget {
  const SectionHeader(this.title, {super.key, this.trailing});
  final String title;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(top: SfSpace.lg, bottom: SfSpace.sm),
    child: Row(
      children: [
        Expanded(
          child: Semantics(
            header: true,
            child: Text(
              title.toUpperCase(),
              style: Theme.of(context).textTheme.labelSmall?.copyWith(color: SfColors.textSecondary),
            ),
          ),
        ),
        if (trailing != null) trailing!,
      ],
    ),
  );
}

String formatDuration(double? seconds) {
  if (seconds == null) return '–';
  final s = seconds.round();
  return '${s ~/ 60}:${(s % 60).toString().padLeft(2, '0')}';
}

String formatBytes(int? bytes) {
  if (bytes == null) return '–';
  if (bytes < 1024 * 1024) return '${(bytes / 1024).toStringAsFixed(0)} KB';
  if (bytes < 1024 * 1024 * 1024) return '${(bytes / (1024 * 1024)).toStringAsFixed(1)} MB';
  return '${(bytes / (1024 * 1024 * 1024)).toStringAsFixed(2)} GB';
}

void showSnack(BuildContext context, String message) =>
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(message)));
