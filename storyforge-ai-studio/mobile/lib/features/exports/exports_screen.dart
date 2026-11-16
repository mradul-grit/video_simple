import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:video_player/video_player.dart';

import '../../app/theme.dart';
import '../../core/models.dart';
import '../../core/providers.dart';
import '../../shared/widgets.dart';

class ExportsScreen extends ConsumerWidget {
  const ExportsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final exports = ref.watch(allExportsProvider);
    final t = Theme.of(context).textTheme;

    return Scaffold(
      appBar: AppBar(title: const Text('Exports')),
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: () => ref.refresh(allExportsProvider.future),
          child: switch (exports) {
            AsyncError(:final error) when !exports.isLoading => ErrorView(
              error: error,
              onRetry: () => ref.invalidate(allExportsProvider),
            ),
            AsyncData(:final value) when value.isEmpty => ListView(
              children: const [
                SizedBox(height: SfSpace.xxl),
                MessageView(
                  icon: Icons.movie_filter_outlined,
                  title: 'No exports yet',
                  message: 'Open a project, review the suggested edits and tap \u201cExport video\u201d.',
                ),
              ],
            ),
            AsyncData(:final value) => ListView.separated(
              padding: const EdgeInsets.all(SfSpace.lg),
              itemCount: value.length + 1,
              separatorBuilder: (_, __) => const SizedBox(height: SfSpace.sm),
              itemBuilder: (context, i) {
                if (i == value.length) {
                  return Padding(
                    padding: const EdgeInsets.only(top: SfSpace.sm),
                    child: Text(
                      'Exports play here. Saving to your gallery and the share sheet are not built yet.',
                      style: t.bodyMedium,
                    ),
                  );
                }
                final (project, job) = value[i];
                return _ExportTile(project: project, job: job);
              },
            ),
            _ => const LoadingView(label: 'Loading exports'),
          },
        ),
      ),
    );
  }
}

class _ExportTile extends ConsumerWidget {
  const _ExportTile({required this.project, required this.job});
  final Project project;
  final RenderJob job;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = Theme.of(context).textTheme;
    final d = job.createdAt;
    final (label, tone) = switch (job.status) {
      'completed' => ('Ready', PillTone.success),
      'failed' => ('Failed', PillTone.danger),
      'cancelled' => ('Cancelled', PillTone.neutral),
      _ => ('Rendering ${job.progress}%', PillTone.progress),
    };
    return Card(
      child: InkWell(
        borderRadius: BorderRadius.circular(SfRadius.md),
        onTap:
            job.succeeded
                ? () => Navigator.of(
                  context,
                ).push(MaterialPageRoute<void>(builder: (_) => ExportPlayerScreen(title: project.title, job: job)))
                : null,
        child: Padding(
          padding: const EdgeInsets.all(SfSpace.md),
          child: Row(
            children: [
              Icon(
                job.succeeded ? Icons.play_circle_outline_rounded : Icons.hourglass_empty_rounded,
                color: job.succeeded ? SfColors.accent : SfColors.textSecondary,
                size: 32,
              ),
              const SizedBox(width: SfSpace.md),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(project.title, style: t.titleMedium, maxLines: 1, overflow: TextOverflow.ellipsis),
                    const SizedBox(height: 2),
                    Text(
                      job.succeeded
                          ? '${formatDuration(job.durationSeconds)} \u00b7 ${formatBytes(job.sizeBytes)} \u00b7 1080\u00d71920'
                          : (job.message ?? '${d.day}/${d.month} ${d.hour}:${d.minute.toString().padLeft(2, '0')}'),
                      style: t.bodyMedium,
                    ),
                  ],
                ),
              ),
              StatusPill(label, tone: tone),
            ],
          ),
        ),
      ),
    );
  }
}

class ExportPlayerScreen extends ConsumerStatefulWidget {
  const ExportPlayerScreen({super.key, required this.title, required this.job});
  final String title;
  final RenderJob job;

  @override
  ConsumerState<ExportPlayerScreen> createState() => _ExportPlayerScreenState();
}

class _ExportPlayerScreenState extends ConsumerState<ExportPlayerScreen> {
  VideoPlayerController? _c;
  Object? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final url = await ref.read(apiProvider).exportUrl(widget.job.id);
      final c = VideoPlayerController.networkUrl(url);
      await c.initialize();
      if (!mounted) return c.dispose();
      c
        ..addListener(() {
          if (mounted) setState(() {});
        })
        ..play();
      setState(() => _c = c);
    } catch (e) {
      if (mounted) setState(() => _error = e);
    }
  }

  @override
  void dispose() {
    _c?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final c = _c;
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(backgroundColor: Colors.black, title: Text(widget.title)),
      body: Center(
        child:
            _error != null
                ? ErrorView(
                  error: _error!,
                  onRetry: () {
                    setState(() => _error = null);
                    _load();
                  },
                )
                : c == null
                ? const LoadingView(label: 'Loading export')
                : GestureDetector(
                  onTap: () => c.value.isPlaying ? c.pause() : c.play(),
                  child: AspectRatio(aspectRatio: c.value.aspectRatio, child: VideoPlayer(c)),
                ),
      ),
    );
  }
}
