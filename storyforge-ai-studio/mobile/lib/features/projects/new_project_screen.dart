import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/theme.dart';
import '../../core/providers.dart';
import '../../shared/widgets.dart';

/// Language hint passed to transcription. Accuracy claims need an evaluation set first.
const projectLanguages = <(String, String, String?)>[
  ('auto', 'Detect automatically', null),
  ('en-IN', 'English (India)', null),
  ('hi', 'Hindi', null),
  ('hi-en', 'Hinglish (Hindi + English)', 'Mixed-language accuracy has not been evaluated yet. Review the transcript.'),
];

/// All presets export 1080\u00d71920 (9:16); they differ only in the intended platform.
const outputPresets = <(String, String)>[('reels', 'Instagram Reel'), ('shorts', 'YouTube Short'), ('story', 'Story')];

class NewProjectScreen extends ConsumerStatefulWidget {
  const NewProjectScreen({super.key});

  @override
  ConsumerState<NewProjectScreen> createState() => _NewProjectScreenState();
}

class _NewProjectScreenState extends ConsumerState<NewProjectScreen> {
  final _form = GlobalKey<FormState>();
  final _title = TextEditingController();
  String _language = 'auto';
  String _preset = 'reels';
  bool _busy = false;

  @override
  void dispose() {
    _title.dispose();
    super.dispose();
  }

  Future<void> _create() async {
    if (!_form.currentState!.validate()) return;
    setState(() => _busy = true);
    try {
      final p = await ref
          .read(apiProvider)
          .createProject(title: _title.text.trim(), language: _language, preset: _preset);
      ref.invalidate(projectsProvider);
      if (mounted) context.pushReplacement('/projects/${p.id}');
    } catch (e) {
      if (mounted) showSnack(context, e.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final note = projectLanguages.firstWhere((l) => l.$1 == _language).$3;

    return Scaffold(
      appBar: AppBar(title: const Text('New video')),
      body: SafeArea(
        child: Form(
          key: _form,
          child: ListView(
            padding: const EdgeInsets.all(SfSpace.lg),
            children: [
              TextFormField(
                controller: _title,
                autofocus: true,
                maxLength: 500,
                textCapitalization: TextCapitalization.sentences,
                decoration: const InputDecoration(
                  labelText: 'Title',
                  hintText: 'e.g. How a tap washer works',
                  counterText: '',
                ),
                validator: (v) => (v ?? '').trim().isEmpty ? 'Give your video a title' : null,
              ),
              const SectionHeader('Spoken language'),
              DropdownButtonFormField<String>(
                value: _language,
                isExpanded: true,
                items: [
                  for (final l in projectLanguages)
                    DropdownMenuItem(value: l.$1, child: Text(l.$2, overflow: TextOverflow.ellipsis)),
                ],
                onChanged: (v) => setState(() => _language = v!),
              ),
              if (note != null) ...[
                const SizedBox(height: SfSpace.sm),
                Row(
                  children: [
                    const Icon(Icons.info_outline_rounded, size: 18, color: SfColors.warning),
                    const SizedBox(width: SfSpace.sm),
                    Expanded(child: Text(note, style: t.bodyMedium)),
                  ],
                ),
              ],
              const SectionHeader('Made for'),
              Wrap(
                spacing: SfSpace.sm,
                runSpacing: SfSpace.sm,
                children: [
                  for (final p in outputPresets)
                    ChoiceChip(
                      label: Text(p.$2),
                      selected: _preset == p.$1,
                      onSelected: (_) => setState(() => _preset = p.$1),
                    ),
                ],
              ),
              const SizedBox(height: SfSpace.sm),
              Text('Exports are vertical 1080\u00d71920 MP4. You publish them yourself.', style: t.bodyMedium),
              const SizedBox(height: SfSpace.xl),
              PrimaryButton(label: 'Create project', onPressed: _create, busy: _busy),
            ],
          ),
        ),
      ),
    );
  }
}
