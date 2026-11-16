import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:video_player/video_player.dart';

import '../../app/theme.dart';
import '../../core/api_client.dart';
import '../../core/models.dart';
import '../../core/providers.dart';
import '../../shared/widgets.dart';
import 'edit_plan.dart';

/// Review-and-render editor: preview first, then a simple layered timeline and the
/// review lists. Every AI proposal starts unreviewed and is applied only when accepted.
class EditorScreen extends ConsumerStatefulWidget {
  const EditorScreen({super.key, required this.projectId});
  final String projectId;

  @override
  ConsumerState<EditorScreen> createState() => _EditorScreenState();
}

class _EditorScreenState extends ConsumerState<EditorScreen> {
  final _player = GlobalKey<_PreviewState>();
  final Map<String, bool?> _decisions = {}; // local view of cut decisions (server is the source of truth)
  final Set<String> _saving = {};
  AudioPreset _audio = AudioPreset.clean;
  bool _rendering = false;
  int _renderProgress = 0;
  String? _renderStage;

  String get _id => widget.projectId;

  bool? _accepted(CutProposal c) => _decisions.containsKey(c.id) ? _decisions[c.id] : c.accepted;

  Future<void> _decide(CutProposal cut, bool accepted) async {
    final before = _accepted(cut);
    setState(() {
      _decisions[cut.id] = accepted;
      _saving.add(cut.id);
    });
    try {
      await ref.read(apiProvider).reviewCut(_id, cut.id, accepted: accepted);
    } catch (e) {
      if (!mounted) return;
      setState(() => _decisions[cut.id] = before);
      showSnack(context, e.toString());
    } finally {
      if (mounted) setState(() => _saving.remove(cut.id));
    }
  }

  Future<void> _render(MediaAsset media, List<CutProposal> cuts) async {
    final reviewed = [
      for (final c in cuts)
        CutProposal(
          id: c.id,
          start: c.start,
          end: c.end,
          reason: c.reason,
          cutType: c.cutType,
          confidence: c.confidence,
          accepted: _accepted(c),
        ),
    ];
    final keep = keepRanges(media.durationSeconds ?? 0, reviewed);
    if (keep.isEmpty) {
      showSnack(context, 'Every part of the video is cut. Reject a cut to keep something.');
      return;
    }
    final api = ref.read(apiProvider);
    setState(() {
      _rendering = true;
      _renderProgress = 0;
      _renderStage = 'Saving your edit';
    });
    try {
      final manifest = buildManifest(projectId: _id, mediaId: media.id, keep: keep, audio: _audio);
      int version;
      try {
        version = await api.saveManifest(_id, manifest, expectedVersion: await api.latestManifestVersion(_id));
      } on ApiException catch (e) {
        if (!e.isConflict) rethrow;
        // Another save landed first. This manifest is rebuilt from server state, so retry once on top.
        version = await api.saveManifest(_id, manifest, expectedVersion: await api.latestManifestVersion(_id));
      }
      final job = await api.startRender(_id, manifestVersion: version, preset: 'preview');
      final done = await pollUntil(
        () => api.getRender(job.id),
        isDone: (r) => r.isTerminal,
        isActive: () => mounted,
        onUpdate: (r) {
          if (mounted) {
            setState(() {
              _renderProgress = r.progress;
              _renderStage = r.stage;
            });
          }
        },
      );
      if (!mounted) return;
      ref.invalidate(exportsProvider(_id));
      ref.invalidate(allExportsProvider);
      if (done.succeeded) {
        showSnack(context, 'Export ready');
        context.go('/exports');
      } else {
        showSnack(context, done.message ?? 'The render failed. Please retry.');
      }
    } catch (e) {
      if (mounted) showSnack(context, e.toString());
    } finally {
      if (mounted) setState(() => _rendering = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final analysis = ref.watch(analysisProvider(_id));
    final media = ref.watch(mediaProvider(_id));
    final info = ref.watch(systemInfoProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('Edit')),
      body: SafeArea(
        child: switch ((analysis, media)) {
          (AsyncError(:final error), _) || (_, AsyncError(:final error)) => ErrorView(
            error: error,
            onRetry: () {
              ref.invalidate(analysisProvider(_id));
              ref.invalidate(mediaProvider(_id));
            },
          ),
          (AsyncData(value: final a), AsyncData(value: final m)) => _buildEditor(
            context,
            a,
            m.where((x) => x.isReady).lastOrNull,
            info.value?.demoMode ?? false,
          ),
          _ => const LoadingView(label: 'Loading your edit'),
        },
      ),
    );
  }

  Widget _buildEditor(BuildContext context, AnalysisResult a, MediaAsset? media, bool demo) {
    if (media == null) {
      return const MessageView(
        icon: Icons.videocam_off_outlined,
        title: 'No video in this project',
        message: 'Go back and add a recording first.',
      );
    }
    final duration = media.durationSeconds ?? 0;
    final keep = keepRanges(duration, [
      for (final c in a.cuts)
        CutProposal(
          id: c.id,
          start: c.start,
          end: c.end,
          reason: c.reason,
          cutType: c.cutType,
          confidence: c.confidence,
          accepted: _accepted(c),
        ),
    ]);
    final kept = keep.fold<double>(0, (s, r) => s + r.duration);
    final pending = a.cuts.where((c) => _accepted(c) == null).length;

    return DefaultTabController(
      length: 3,
      child: Column(
        children: [
          Expanded(
            child: NestedScrollView(
              headerSliverBuilder:
                  (context, _) => [
                    SliverPadding(
                      padding: const EdgeInsets.fromLTRB(SfSpace.md, 0, SfSpace.md, 0),
                      sliver: SliverList.list(
                        children: [
                          if (demo) ...[const DemoBanner(), const SizedBox(height: SfSpace.sm)],
                          _Preview(key: _player, projectId: _id, media: media),
                          const SizedBox(height: SfSpace.sm),
                          _Timeline(
                            duration: duration,
                            cuts: a.cuts,
                            accepted: _accepted,
                            captions: a.captions,
                            onSeek: (s) => _player.currentState?.seek(s),
                          ),
                          const SizedBox(height: SfSpace.xs),
                          Text(
                            'Result ${formatDuration(kept)} of ${formatDuration(duration)}'
                            '${pending > 0 ? ' \u00b7 $pending cut${pending == 1 ? '' : 's'} to review' : ''}',
                            style: Theme.of(context).textTheme.bodyMedium,
                          ),
                        ],
                      ),
                    ),
                    const SliverToBoxAdapter(
                      child: TabBar(tabs: [Tab(text: 'Cuts'), Tab(text: 'Transcript'), Tab(text: 'Key points')]),
                    ),
                  ],
              body: TabBarView(
                children: [
                  _CutsList(
                    cuts: a.cuts,
                    accepted: _accepted,
                    saving: _saving,
                    onDecide: _decide,
                    onSeek: (s) => _player.currentState?.seek(s),
                  ),
                  _TranscriptList(segments: a.segments, onSeek: (s) => _player.currentState?.seek(s)),
                  _CaptionsList(captions: a.captions, segments: a.segments),
                ],
              ),
            ),
          ),
          _RenderBar(
            audio: _audio,
            onAudio: _rendering ? null : (v) => setState(() => _audio = v),
            rendering: _rendering,
            progress: _renderProgress,
            stage: _renderStage,
            onRender: () => _render(media, a.cuts),
          ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------- preview

class _Preview extends ConsumerStatefulWidget {
  const _Preview({super.key, required this.projectId, required this.media});
  final String projectId;
  final MediaAsset media;

  @override
  ConsumerState<_Preview> createState() => _PreviewState();
}

class _PreviewState extends ConsumerState<_Preview> {
  VideoPlayerController? _c;
  Object? _error;

  @override
  void initState() {
    super.initState();
    if (ref.read(videoPreviewEnabledProvider)) _load();
  }

  Future<void> _load() async {
    try {
      final url = await ref.read(apiProvider).mediaPreviewUrl(widget.projectId, widget.media.id);
      final c = VideoPlayerController.networkUrl(url);
      await c.initialize();
      if (!mounted) return c.dispose();
      c.addListener(() {
        if (mounted) setState(() {});
      });
      setState(() => _c = c);
    } catch (e) {
      if (mounted) setState(() => _error = e);
    }
  }

  void seek(double seconds) {
    final c = _c;
    if (c == null) return;
    c.seekTo(Duration(milliseconds: (seconds * 1000).round()));
    c.play();
  }

  @override
  void dispose() {
    _c?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final c = _c;
    final aspect = (widget.media.width ?? 9) / (widget.media.height ?? 16);
    return ClipRRect(
      borderRadius: BorderRadius.circular(SfRadius.md),
      child: Container(
        height: 280,
        color: Colors.black,
        alignment: Alignment.center,
        child:
            c != null && c.value.isInitialized
                ? GestureDetector(
                  onTap: () => c.value.isPlaying ? c.pause() : c.play(),
                  child: Stack(
                    alignment: Alignment.center,
                    children: [
                      AspectRatio(aspectRatio: c.value.aspectRatio, child: VideoPlayer(c)),
                      if (!c.value.isPlaying)
                        Semantics(
                          button: true,
                          label: 'Play preview',
                          child: Container(
                            padding: const EdgeInsets.all(SfSpace.sm),
                            decoration: const BoxDecoration(color: Colors.black54, shape: BoxShape.circle),
                            child: const Icon(Icons.play_arrow_rounded, size: 40),
                          ),
                        ),
                    ],
                  ),
                )
                : AspectRatio(
                  aspectRatio: aspect,
                  child: Center(
                    child:
                        _error != null
                            ? Padding(
                              padding: const EdgeInsets.all(SfSpace.md),
                              child: Text('Preview unavailable', style: Theme.of(context).textTheme.bodyMedium),
                            )
                            : ref.read(videoPreviewEnabledProvider)
                            ? const CircularProgressIndicator(strokeWidth: 2)
                            : const Icon(Icons.movie_outlined, color: SfColors.textSecondary),
                  ),
                ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------- timeline

/// Source-time layers: video (kept/cut) and key-point caption markers. Tap to seek.
class _Timeline extends StatelessWidget {
  const _Timeline({
    required this.duration,
    required this.cuts,
    required this.accepted,
    required this.captions,
    required this.onSeek,
  });

  final double duration;
  final List<CutProposal> cuts;
  final bool? Function(CutProposal) accepted;
  final List<EditorialCaption> captions;
  final void Function(double) onSeek;

  @override
  Widget build(BuildContext context) => Semantics(
    label: 'Timeline, ${formatDuration(duration)} long',
    child: LayoutBuilder(
      builder:
          (context, box) => GestureDetector(
            onTapDown: (d) => duration > 0 ? onSeek((d.localPosition.dx / box.maxWidth).clamp(0, 1) * duration) : null,
            child: CustomPaint(
              size: Size(box.maxWidth, 44),
              painter: _TimelinePainter(duration: duration, cuts: cuts, accepted: accepted, captions: captions),
            ),
          ),
    ),
  );
}

class _TimelinePainter extends CustomPainter {
  _TimelinePainter({required this.duration, required this.cuts, required this.accepted, required this.captions});
  final double duration;
  final List<CutProposal> cuts;
  final bool? Function(CutProposal) accepted;
  final List<EditorialCaption> captions;

  @override
  void paint(Canvas canvas, Size size) {
    if (duration <= 0) return;
    double x(double s) => (s / duration).clamp(0, 1) * size.width;
    final r = const Radius.circular(6);
    final video = Rect.fromLTWH(0, 0, size.width, 26);
    canvas.drawRRect(RRect.fromRectAndRadius(video, r), Paint()..color = SfColors.surfaceRaised);
    for (final c in cuts) {
      final rect = Rect.fromLTRB(x(c.start), 0, x(c.end), 26);
      final a = accepted(c);
      if (a == true) {
        canvas.drawRect(rect, Paint()..color = SfColors.danger.withValues(alpha: 0.55));
      } else if (a == null) {
        canvas.drawRect(rect, Paint()..color = SfColors.warning.withValues(alpha: 0.30));
      }
    }
    final cap = Paint()..color = SfColors.accent;
    for (final c in captions) {
      canvas.drawRRect(
        RRect.fromRectAndRadius(Rect.fromLTRB(x(c.start), 32, x(c.end), 40), const Radius.circular(3)),
        cap,
      );
    }
  }

  @override
  bool shouldRepaint(covariant _TimelinePainter old) => true;
}

// ---------------------------------------------------------------------------- lists

class _CutsList extends StatelessWidget {
  const _CutsList({
    required this.cuts,
    required this.accepted,
    required this.saving,
    required this.onDecide,
    required this.onSeek,
  });

  final List<CutProposal> cuts;
  final bool? Function(CutProposal) accepted;
  final Set<String> saving;
  final void Function(CutProposal, bool) onDecide;
  final void Function(double) onSeek;

  @override
  Widget build(BuildContext context) {
    if (cuts.isEmpty) {
      return const MessageView(
        icon: Icons.check_circle_outline_rounded,
        title: 'No cuts suggested',
        message: 'No long pauses or filler words were found. Your video is kept as recorded.',
      );
    }
    final t = Theme.of(context).textTheme;
    return ListView.separated(
      padding: const EdgeInsets.all(SfSpace.md),
      itemCount: cuts.length,
      separatorBuilder: (_, __) => const SizedBox(height: SfSpace.sm),
      itemBuilder: (_, i) {
        final c = cuts[i];
        final a = accepted(c);
        final lowConfidence = c.confidence < 0.6;
        return Card(
          child: Padding(
            padding: const EdgeInsets.all(SfSpace.md),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: InkWell(
                        onTap: () => onSeek(c.start),
                        child: Text(
                          '${formatDuration(c.start)} \u2013 ${formatDuration(c.end)} \u00b7 ${c.cutType}',
                          style: t.titleMedium,
                        ),
                      ),
                    ),
                    StatusPill(
                      switch (a) {
                        true => 'Cut',
                        false => 'Kept',
                        null => 'Review',
                      },
                      tone: switch (a) {
                        true => PillTone.danger,
                        false => PillTone.success,
                        null => PillTone.warning,
                      },
                    ),
                  ],
                ),
                const SizedBox(height: SfSpace.xs),
                Text(c.reason, style: t.bodyMedium),
                Text(
                  'Confidence ${(c.confidence * 100).round()}%${lowConfidence ? ' \u00b7 low, listen before cutting' : ''}',
                  style: t.bodyMedium?.copyWith(color: lowConfidence ? SfColors.warning : null),
                ),
                const SizedBox(height: SfSpace.sm),
                Row(
                  children: [
                    Expanded(
                      child: OutlinedButton(
                        onPressed: saving.contains(c.id) || a == false ? null : () => onDecide(c, false),
                        child: const Text('Keep'),
                      ),
                    ),
                    const SizedBox(width: SfSpace.sm),
                    Expanded(
                      child: FilledButton(
                        onPressed: saving.contains(c.id) || a == true ? null : () => onDecide(c, true),
                        child: const Text('Cut'),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}

class _TranscriptList extends StatelessWidget {
  const _TranscriptList({required this.segments, required this.onSeek});
  final List<TranscriptSegment> segments;
  final void Function(double) onSeek;

  @override
  Widget build(BuildContext context) {
    final speech = segments.where((s) => s.isSpeech && s.text.trim().isNotEmpty).toList();
    if (speech.isEmpty) {
      return const MessageView(
        icon: Icons.hearing_disabled_outlined,
        title: 'No speech found',
        message: 'The transcript is empty.',
      );
    }
    final t = Theme.of(context).textTheme;
    return ListView.builder(
      padding: const EdgeInsets.all(SfSpace.md),
      itemCount: speech.length,
      itemBuilder: (_, i) {
        final s = speech[i];
        final low = (s.confidence ?? 1) < 0.6;
        return InkWell(
          onTap: () => onSeek(s.start),
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: SfSpace.sm),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                SizedBox(
                  width: 48,
                  child: Text(formatDuration(s.start), style: t.labelSmall?.copyWith(color: SfColors.accent)),
                ),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(s.text, style: t.bodyLarge),
                      if (low)
                        Text('Low confidence, check this line', style: t.bodyMedium?.copyWith(color: SfColors.warning)),
                    ],
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}

class _CaptionsList extends StatelessWidget {
  const _CaptionsList({required this.captions, required this.segments});
  final List<EditorialCaption> captions;
  final List<TranscriptSegment> segments;

  @override
  Widget build(BuildContext context) {
    if (captions.isEmpty) {
      return const MessageView(
        icon: Icons.short_text_rounded,
        title: 'No key points',
        message: 'No editorial captions were suggested.',
      );
    }
    final t = Theme.of(context).textTheme;
    final byId = {for (final s in segments) s.id: s};
    return ListView.separated(
      padding: const EdgeInsets.all(SfSpace.md),
      itemCount: captions.length + 1,
      separatorBuilder: (_, __) => const SizedBox(height: SfSpace.sm),
      itemBuilder: (_, i) {
        if (i == captions.length) {
          return Text(
            'Key points are shown for review. Editing them and burning them into the export come in the next editor release.',
            style: t.bodyMedium,
          );
        }
        final c = captions[i];
        final sources = [for (final id in c.segmentIds) byId[id]].whereType<TranscriptSegment>();
        return Card(
          child: Padding(
            padding: const EdgeInsets.all(SfSpace.md),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(child: Text(c.text, style: t.titleMedium)),
                    if (c.lowConfidence) const StatusPill('Needs review', tone: PillTone.warning),
                  ],
                ),
                const SizedBox(height: SfSpace.sm),
                Text('From the transcript', style: t.labelSmall?.copyWith(color: SfColors.textSecondary)),
                for (final s in sources) Text('${formatDuration(s.start)}  \u201c${s.text}\u201d', style: t.bodyMedium),
                if (sources.isEmpty)
                  Text('Not linked to any transcript line', style: t.bodyMedium?.copyWith(color: SfColors.warning)),
              ],
            ),
          ),
        );
      },
    );
  }
}

// ---------------------------------------------------------------------------- render bar

class _RenderBar extends StatelessWidget {
  const _RenderBar({
    required this.audio,
    required this.onAudio,
    required this.rendering,
    required this.progress,
    required this.stage,
    required this.onRender,
  });

  final AudioPreset audio;
  final ValueChanged<AudioPreset>? onAudio;
  final bool rendering;
  final int progress;
  final String? stage;
  final VoidCallback onRender;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.fromLTRB(SfSpace.md, SfSpace.sm, SfSpace.md, SfSpace.md),
    decoration: const BoxDecoration(color: SfColors.surface, border: Border(top: BorderSide(color: SfColors.outline))),
    child: Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          children: [
            Text('Audio', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(width: SfSpace.md),
            Expanded(
              child: DropdownButton<AudioPreset>(
                value: audio,
                isExpanded: true,
                underline: const SizedBox.shrink(),
                onChanged: onAudio == null ? null : (v) => onAudio!(v!),
                items: [
                  for (final p in AudioPreset.values)
                    DropdownMenuItem(
                      value: p,
                      child: Align(
                        alignment: Alignment.centerRight,
                        child: Text(p.label, overflow: TextOverflow.ellipsis),
                      ),
                    ),
                ],
              ),
            ),
          ],
        ),
        if (rendering) ...[
          Semantics(
            liveRegion: true,
            label: 'Rendering $progress percent',
            child: Text(
              '${switch (stage) {
                'rendering' => 'Rendering',
                'verifying' => 'Checking the export',
                'completed' => 'Done',
                null => 'Starting',
                _ => 'Preparing',
              }} \u00b7 $progress%',
              style: Theme.of(context).textTheme.bodyMedium,
            ),
          ),
          const SizedBox(height: SfSpace.sm),
          LinearProgressIndicator(value: progress > 0 ? progress / 100 : null),
          const SizedBox(height: SfSpace.sm),
        ],
        PrimaryButton(label: 'Export video', icon: Icons.ios_share_rounded, busy: rendering, onPressed: onRender),
      ],
    ),
  );
}
