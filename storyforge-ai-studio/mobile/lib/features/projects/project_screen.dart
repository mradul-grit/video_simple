import 'package:dio/dio.dart';
import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/theme.dart';
import '../../core/api_client.dart';
import '../../core/models.dart';
import '../../core/providers.dart';
import '../../shared/widgets.dart';

/// Picks a video file. Replaced with a fake in widget tests.
typedef VideoPick = ({String path, String name, int size});

final videoPickerProvider = Provider<Future<VideoPick?> Function()>(
  (ref) => () async {
    final r = await FilePicker.pickFiles(type: FileType.video);
    final f = r?.files.single;
    if (f == null) return null;
    if (f.path == null) throw ApiException("This file can't be read from your device.");
    return (path: f.path!, name: f.name, size: f.size);
  },
);

const _contentTypes = {
  'mp4': 'video/mp4',
  'm4v': 'video/mp4',
  'mov': 'video/quicktime',
  'webm': 'video/webm',
  'mkv': 'video/x-matroska',
  'avi': 'video/x-msvideo',
  'mpeg': 'video/mpeg',
  'mpg': 'video/mpeg',
};

String? contentTypeFor(String fileName) {
  final dot = fileName.lastIndexOf('.');
  return dot < 0 ? null : _contentTypes[fileName.substring(dot + 1).toLowerCase()];
}

enum _Phase { idle, uploading, validating, analysing }

class ProjectScreen extends ConsumerStatefulWidget {
  const ProjectScreen({super.key, required this.projectId});
  final String projectId;

  @override
  ConsumerState<ProjectScreen> createState() => _ProjectScreenState();
}

class _ProjectScreenState extends ConsumerState<ProjectScreen> {
  _Phase _phase = _Phase.idle;
  double _progress = 0;
  String? _stage;
  String? _error;
  CancelToken? _cancel;

  String get _id => widget.projectId;

  @override
  void dispose() {
    _cancel?.cancel();
    super.dispose();
  }

  void _setError(Object e) => setState(() {
    _phase = _Phase.idle;
    _error = e.toString();
  });

  Future<void> _pickAndUpload(SystemInfo info) async {
    setState(() => _error = null);
    final VideoPick? file;
    try {
      file = await ref.read(videoPickerProvider)();
    } catch (e) {
      return _setError(e);
    }
    if (file == null || !mounted) return;

    final type = contentTypeFor(file.name);
    if (type == null || !info.acceptedContentTypes.contains(type)) {
      return _setError('That file type isn\u2019t supported. Use MP4, MOV, WebM, MKV or AVI.');
    }
    if (file.size > info.maxUploadBytes) {
      return _setError('That video is ${formatBytes(file.size)}. The limit is ${formatBytes(info.maxUploadBytes)}.');
    }
    if (!await _confirmUpload(info, file) || !mounted) return;

    final api = ref.read(apiProvider);
    _cancel = CancelToken();
    setState(() {
      _phase = _Phase.uploading;
      _progress = 0;
    });
    try {
      final job = await api.uploadVideo(
        projectId: _id,
        filePath: file.path,
        fileName: file.name,
        sizeBytes: file.size,
        contentType: type,
        cancelToken: _cancel,
        onProgress: (f) {
          if (mounted) setState(() => _progress = f);
        },
      );
      if (!mounted) return;
      setState(() => _phase = _Phase.validating);
      final done = await pollUntil(() => api.getJob(job.id), isDone: (j) => j.isTerminal, isActive: () => mounted);
      if (!mounted) return;
      ref.invalidate(mediaProvider(_id));
      if (done.succeeded) {
        setState(() => _phase = _Phase.idle);
      } else {
        _setError(done.message ?? 'The video could not be validated.');
      }
    } on UploadCancelled {
      if (mounted) {
        setState(() => _phase = _Phase.idle);
        showSnack(context, 'Upload cancelled');
      }
    } catch (e) {
      if (mounted) _setError(e);
    }
  }

  Future<bool> _confirmUpload(SystemInfo info, VideoPick file) async {
    final host = Uri.tryParse(ref.read(apiBaseUrlProvider))?.host ?? 'your server';
    return await showDialog<bool>(
          context: context,
          builder:
              (c) => AlertDialog(
                title: const Text('Upload this video?'),
                content: Text(
                  '\u201c${file.name}\u201d (${formatBytes(file.size)}) will be uploaded to $host and stored privately. '
                  'Your original is never modified. It is kept for up to ${info.retentionDays} days or until you delete the project.'
                  '${info.demoMode ? '\n\nThis server is in demo mode: analysis returns placeholder text, not real AI output.' : ''}',
                ),
                actions: [
                  TextButton(onPressed: () => Navigator.pop(c, false), child: const Text('Cancel')),
                  FilledButton(onPressed: () => Navigator.pop(c, true), child: const Text('Upload')),
                ],
              ),
        ) ??
        false;
  }

  Future<void> _analyse(MediaAsset media) async {
    final api = ref.read(apiProvider);
    setState(() {
      _phase = _Phase.analysing;
      _error = null;
      _stage = 'Queued';
      _progress = 0;
    });
    try {
      final job = await api.startAnalysis(
        _id,
        idempotencyKey: 'analysis-${media.id}-${DateTime.now().millisecondsSinceEpoch}',
      );
      final done = await pollUntil(
        () => api.getJob(job.id),
        isDone: (j) => j.isTerminal,
        isActive: () => mounted,
        onUpdate: (j) {
          if (mounted) {
            setState(() {
              _stage = j.stage;
              _progress = j.progress / 100;
            });
          }
        },
      );
      if (!mounted) return;
      ref.invalidate(analysisProvider(_id));
      if (done.succeeded) {
        setState(() => _phase = _Phase.idle);
      } else {
        _setError(done.message ?? 'Analysis failed. Please retry.');
      }
    } catch (e) {
      if (mounted) _setError(e);
    }
  }

  Future<void> _delete() async {
    final ok = await showDialog<bool>(
      context: context,
      builder:
          (c) => AlertDialog(
            title: const Text('Delete this project?'),
            content: const Text('This permanently deletes the original video, the analysis, edits and all exports.'),
            actions: [
              TextButton(onPressed: () => Navigator.pop(c, false), child: const Text('Keep')),
              FilledButton(
                style: FilledButton.styleFrom(backgroundColor: SfColors.danger),
                onPressed: () => Navigator.pop(c, true),
                child: const Text('Delete'),
              ),
            ],
          ),
    );
    if (ok != true || !mounted) return;
    try {
      await ref.read(apiProvider).deleteProject(_id);
      ref.invalidate(projectsProvider);
      ref.invalidate(allExportsProvider);
      if (mounted) context.pop();
    } catch (e) {
      if (mounted) showSnack(context, e.toString());
    }
  }

  @override
  Widget build(BuildContext context) {
    final project = ref.watch(projectProvider(_id));
    final media = ref.watch(mediaProvider(_id));
    final info = ref.watch(systemInfoProvider);
    final busy = _phase != _Phase.idle;

    return Scaffold(
      appBar: AppBar(
        title: Text(project.value?.title ?? ''),
        actions: [
          PopupMenuButton<String>(
            tooltip: 'Project options',
            enabled: !busy,
            onSelected: (_) => _delete(),
            itemBuilder: (_) => const [PopupMenuItem(value: 'delete', child: Text('Delete project'))],
          ),
        ],
      ),
      body: SafeArea(
        child: switch ((project, media, info)) {
          (AsyncError(:final error), _, _) ||
          (_, AsyncError(:final error), _) ||
          (_, _, AsyncError(:final error)) => ErrorView(
            error: error,
            onRetry: () {
              ref.invalidate(projectProvider(_id));
              ref.invalidate(mediaProvider(_id));
              ref.invalidate(systemInfoProvider);
            },
          ),
          (AsyncData(), AsyncData(value: final assets), AsyncData(value: final sys)) => _body(
            context,
            assets,
            sys,
            busy,
          ),
          _ => const LoadingView(),
        },
      ),
    );
  }

  Widget _body(BuildContext context, List<MediaAsset> assets, SystemInfo info, bool busy) {
    final t = Theme.of(context).textTheme;
    final ready = assets.where((a) => a.isReady).toList();
    final video = ready.isEmpty ? null : ready.last;

    return ListView(
      padding: const EdgeInsets.all(SfSpace.lg),
      children: [
        if (info.demoMode) ...[const DemoBanner(), const SizedBox(height: SfSpace.md)],
        if (_error != null) ...[
          _ErrorCard(message: _error!, onDismiss: () => setState(() => _error = null)),
          const SizedBox(height: SfSpace.md),
        ],
        if (video == null) ...[
          Text('Add your recording', style: t.titleLarge),
          const SizedBox(height: SfSpace.xs),
          Text(
            'MP4, MOV, WebM, MKV or AVI \u00b7 up to ${formatBytes(info.maxUploadBytes)} \u00b7 '
            'up to ${info.maxDurationSeconds ~/ 60} minutes.',
            style: t.bodyMedium,
          ),
          const SizedBox(height: SfSpace.lg),
          if (_phase == _Phase.uploading)
            _ProgressCard(
              title: 'Uploading',
              detail: '${(_progress * 100).round()}%',
              value: _progress,
              onCancel: () => _cancel?.cancel(),
            )
          else if (_phase == _Phase.validating)
            const _ProgressCard(title: 'Checking your video', detail: 'Reading format, length and audio')
          else
            PrimaryButton(
              label: 'Choose video',
              icon: Icons.video_library_outlined,
              onPressed: busy ? null : () => _pickAndUpload(info),
            ),
          const SizedBox(height: SfSpace.sm),
          Text(
            'In-app recording is not available yet; record with your camera app and import it.',
            style: t.bodyMedium,
          ),
        ] else ...[
          _MediaCard(media: video),
          const SizedBox(height: SfSpace.lg),
          _AnalysisSection(
            projectId: _id,
            busy: busy,
            analysing: _phase == _Phase.analysing,
            stage: _stage,
            progress: _progress,
            onAnalyse: () => _analyse(video),
          ),
        ],
      ],
    );
  }
}

class _AnalysisSection extends ConsumerWidget {
  const _AnalysisSection({
    required this.projectId,
    required this.busy,
    required this.analysing,
    required this.stage,
    required this.progress,
    required this.onAnalyse,
  });

  final String projectId;
  final bool busy;
  final bool analysing;
  final String? stage;
  final double progress;
  final VoidCallback onAnalyse;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = Theme.of(context).textTheme;
    if (analysing) {
      return _ProgressCard(
        title: 'Listening to your story',
        detail: switch (stage) {
          'transcribing' => 'Transcribing speech',
          'analysing' => 'Finding key points and pauses',
          'preparing' => 'Preparing audio',
          _ => 'Waiting for the worker',
        },
        value: progress > 0 ? progress : null,
      );
    }
    final analysis = ref.watch(analysisProvider(projectId));
    return switch (analysis) {
      AsyncData(:final value) when !value.isEmpty => Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text('Ready to edit', style: t.titleLarge),
          const SizedBox(height: SfSpace.xs),
          Text(
            '${plural(value.segments.where((s) => s.isSpeech).length, 'transcript segment')} \u00b7 '
            '${plural(value.cuts.length, 'suggested cut')} \u00b7 ${plural(value.captions.length, 'key-point caption')}',
            style: t.bodyMedium,
          ),
          const SizedBox(height: SfSpace.lg),
          PrimaryButton(
            label: 'Open editor',
            icon: Icons.content_cut_rounded,
            onPressed: busy ? null : () => context.push('/projects/$projectId/editor'),
          ),
          const SizedBox(height: SfSpace.sm),
          OutlinedButton(onPressed: busy ? null : onAnalyse, child: const Text('Analyse again')),
        ],
      ),
      AsyncData() => Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text('Analyse your story', style: t.titleLarge),
          const SizedBox(height: SfSpace.xs),
          Text(
            'StoryForge transcribes the speech, finds pauses and key points, and suggests edits. '
            'Nothing is changed until you approve it.',
            style: t.bodyMedium,
          ),
          const SizedBox(height: SfSpace.lg),
          PrimaryButton(label: 'Analyse video', icon: Icons.auto_awesome_rounded, onPressed: busy ? null : onAnalyse),
        ],
      ),
      AsyncError(:final error) => ErrorView(error: error, onRetry: () => ref.invalidate(analysisProvider(projectId))),
      _ => const LoadingView(),
    };
  }
}

class _MediaCard extends StatelessWidget {
  const _MediaCard({required this.media});
  final MediaAsset media;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(SfSpace.md),
        child: Row(
          children: [
            const Icon(Icons.movie_creation_outlined, color: SfColors.accent),
            const SizedBox(width: SfSpace.md),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    media.originalFilename ?? 'Video',
                    style: t.titleMedium,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                  const SizedBox(height: 2),
                  Text(
                    '${formatDuration(media.durationSeconds)} \u00b7 ${media.width}\u00d7${media.height} \u00b7 '
                    '${formatBytes(media.fileSizeBytes)}${media.hasAudio == false ? ' \u00b7 no audio' : ''}',
                    style: t.bodyMedium,
                  ),
                ],
              ),
            ),
            const StatusPill('Original kept', tone: PillTone.success),
          ],
        ),
      ),
    );
  }
}

class _ProgressCard extends StatelessWidget {
  const _ProgressCard({required this.title, required this.detail, this.value, this.onCancel});
  final String title;
  final String detail;
  final double? value;
  final VoidCallback? onCancel;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(SfSpace.md),
        child: Semantics(
          liveRegion: true,
          label: '$title, $detail',
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(
                children: [
                  Expanded(child: Text(title, style: t.titleMedium)),
                  if (onCancel != null) TextButton(onPressed: onCancel, child: const Text('Cancel')),
                ],
              ),
              const SizedBox(height: SfSpace.xs),
              Text(detail, style: t.bodyMedium),
              const SizedBox(height: SfSpace.md),
              ClipRRect(
                borderRadius: BorderRadius.circular(99),
                child: LinearProgressIndicator(value: value, minHeight: 6),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _ErrorCard extends StatelessWidget {
  const _ErrorCard({required this.message, required this.onDismiss});
  final String message;
  final VoidCallback onDismiss;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.fromLTRB(SfSpace.md, SfSpace.sm, SfSpace.xs, SfSpace.sm),
    decoration: BoxDecoration(
      color: SfColors.danger.withValues(alpha: 0.10),
      borderRadius: BorderRadius.circular(SfRadius.md),
      border: Border.all(color: SfColors.danger.withValues(alpha: 0.4)),
    ),
    child: Row(
      children: [
        const Icon(Icons.error_outline_rounded, color: SfColors.danger),
        const SizedBox(width: SfSpace.sm),
        Expanded(
          child: Text(message, style: Theme.of(context).textTheme.bodyMedium?.copyWith(color: SfColors.textPrimary)),
        ),
        IconButton(tooltip: 'Dismiss', onPressed: onDismiss, icon: const Icon(Icons.close_rounded)),
      ],
    ),
  );
}
