import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../app/theme.dart';
import '../../core/models.dart';
import '../../core/providers.dart';
import '../../shared/widgets.dart';

/// Read-only facts about the server, privacy and AI providers, plus sign-out.
/// Provider choices are server configuration; the app never holds provider keys.
class SettingsScreen extends ConsumerWidget {
  const SettingsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final info = ref.watch(systemInfoProvider);
    final base = ref.watch(apiBaseUrlProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('Settings')),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.symmetric(horizontal: SfSpace.lg),
          children: [
            const SectionHeader('Server'),
            _Row('Address', base),
            ...switch (info) {
              AsyncData(:final value) => _infoRows(value),
              AsyncError(:final error) => [
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: SfSpace.sm),
                  child: Text(error.toString(), style: const TextStyle(color: SfColors.danger)),
                ),
                OutlinedButton(onPressed: () => ref.invalidate(systemInfoProvider), child: const Text('Try again')),
              ],
              _ => [const Padding(padding: EdgeInsets.all(SfSpace.md), child: LinearProgressIndicator())],
            },
            const SectionHeader('Account'),
            Text('Signed in with a development test account.', style: Theme.of(context).textTheme.bodyMedium),
            const SizedBox(height: SfSpace.md),
            OutlinedButton.icon(
              onPressed: () => ref.read(sessionProvider.notifier).signOut(),
              icon: const Icon(Icons.logout_rounded),
              label: const Text('Sign out'),
            ),
            const SizedBox(height: SfSpace.xl),
          ],
        ),
      ),
    );
  }

  List<Widget> _infoRows(SystemInfo i) => [
    _Row('Environment', i.environment),
    const SectionHeader('AI processing'),
    _Row('Transcription', i.transcriptionProvider == 'mock' ? 'Demo (placeholder text)' : i.transcriptionProvider),
    _Row('Story analysis', i.languageModelProvider == 'mock' ? 'Demo (placeholder text)' : i.languageModelProvider),
    if (i.demoMode) const Padding(padding: EdgeInsets.only(top: SfSpace.sm), child: DemoBanner()),
    const SectionHeader('Privacy'),
    _Row('Storage', 'Private, on your StoryForge server'),
    _Row('Originals kept for', '${i.retentionDays} days'),
    _Row('Upload limit', '${formatBytes(i.maxUploadBytes)} \u00b7 ${i.maxDurationSeconds ~/ 60} min'),
    const Padding(
      padding: EdgeInsets.only(top: SfSpace.sm),
      child: Text(
        'Deleting a project removes its original, analysis, edits and exports. '
        'Your videos and transcripts are not used to train models.',
        style: TextStyle(color: SfColors.textSecondary),
      ),
    ),
  ];
}

class _Row extends StatelessWidget {
  const _Row(this.label, this.value);
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: SfSpace.sm),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(flex: 2, child: Text(label, style: t.bodyMedium)),
          Expanded(flex: 3, child: Text(value, style: t.bodyLarge, textAlign: TextAlign.end)),
        ],
      ),
    );
  }
}
