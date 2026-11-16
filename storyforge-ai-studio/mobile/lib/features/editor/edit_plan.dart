import 'dart:math';

import '../../core/models.dart';

/// A source-relative time range in seconds.
class TimeRange {
  const TimeRange(this.start, this.end);

  final double start;
  final double end;

  double get duration => end - start;

  @override
  bool operator ==(Object other) => other is TimeRange && other.start == start && other.end == end;

  @override
  int get hashCode => Object.hash(start, end);

  @override
  String toString() => 'TimeRange($start, $end)';
}

/// Ranges shorter than this (seconds) are dropped: a sliver of a frame is a glitch, not content.
const minKeepSeconds = 0.1;

/// The parts of the source to keep once every *accepted* cut is removed.
///
/// Only cuts the user accepted are applied (null = unreviewed, false = rejected).
/// Cuts are clamped to the source, overlapping cuts are merged, and the result is
/// sorted and non-overlapping, which is what the server-side manifest rules require.
List<TimeRange> keepRanges(double sourceDuration, Iterable<CutProposal> cuts) {
  if (sourceDuration <= 0) return const [];
  final removed =
      <TimeRange>[
          for (final c in cuts)
            if (c.accepted == true)
              TimeRange(c.start.clamp(0, sourceDuration).toDouble(), c.end.clamp(0, sourceDuration).toDouble()),
        ].where((r) => r.end > r.start).toList()
        ..sort((a, b) => a.start.compareTo(b.start));

  final merged = <TimeRange>[];
  for (final r in removed) {
    if (merged.isNotEmpty && r.start <= merged.last.end) {
      merged[merged.length - 1] = TimeRange(merged.last.start, max(merged.last.end, r.end));
    } else {
      merged.add(r);
    }
  }

  final keep = <TimeRange>[];
  var cursor = 0.0;
  for (final r in merged) {
    if (r.start - cursor >= minKeepSeconds) keep.add(TimeRange(cursor, r.start));
    cursor = r.end;
  }
  if (sourceDuration - cursor >= minKeepSeconds) keep.add(TimeRange(cursor, sourceDuration));
  return keep;
}

String newUuid([Random? random]) {
  final rnd = random ?? Random.secure();
  final b = List<int>.generate(16, (_) => rnd.nextInt(256));
  b[6] = (b[6] & 0x0f) | 0x40; // version 4
  b[8] = (b[8] & 0x3f) | 0x80; // RFC 4122 variant
  String hex(int from, int to) => b.sublist(from, to).map((x) => x.toRadixString(16).padLeft(2, '0')).join();
  return '${hex(0, 4)}-${hex(4, 6)}-${hex(6, 8)}-${hex(8, 10)}-${hex(10, 16)}';
}

/// Audio presets offered in the editor. Values stay inside EDIT_MANIFEST.schema.json limits.
enum AudioPreset {
  off('Original audio', null),
  clean('Clean voice', {
    'noise_reduction': 'light',
    'high_pass_hz': 80,
    'loudness_target_lufs': -16,
    'limiter_enabled': true,
  });

  const AudioPreset(this.label, this.settings);
  final String label;
  final Map<String, Object>? settings;
}

/// Build a schema-valid EditManifest v1.0 for one source video.
Map<String, dynamic> buildManifest({
  required String projectId,
  required String mediaId,
  required List<TimeRange> keep,
  AudioPreset audio = AudioPreset.off,
  String quality = 'preview',
  double fps = 30,
}) {
  if (keep.isEmpty) throw ArgumentError('Nothing left to render: every part of the video is cut.');
  return {
    'schema_version': '1.0',
    'project_id': projectId,
    'version': 1, // the server assigns the real version on save
    'output': {
      'width': 1080,
      'height': 1920,
      'fps': fps,
      'container': 'mp4',
      'video_codec': 'h264',
      'audio_codec': 'aac',
      'quality_preset': quality,
    },
    'tracks': [
      {
        'id': newUuid(),
        'type': 'video',
        'items': [
          for (final r in keep)
            {
              'id': newUuid(),
              'source_media_id': mediaId,
              // Rounded to milliseconds: stable JSON, well under one frame.
              'start': double.parse(r.start.toStringAsFixed(3)),
              'end': double.parse(r.end.toStringAsFixed(3)),
            },
        ],
      },
    ],
    if (audio.settings != null) 'audio_adjustments': audio.settings,
  };
}
