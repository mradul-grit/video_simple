import 'dart:math';

import 'package:flutter_test/flutter_test.dart';
import 'package:storyforge_mobile/core/models.dart';
import 'package:storyforge_mobile/features/editor/edit_plan.dart';

CutProposal cut(double s, double e, {bool? accepted = true}) =>
    CutProposal(id: '$s-$e', start: s, end: e, reason: 'pause', cutType: 'pause', confidence: 0.9, accepted: accepted);

void main() {
  group('keepRanges', () {
    test('no cuts keeps the whole source', () {
      expect(keepRanges(10, []), [const TimeRange(0, 10)]);
    });

    test('only accepted cuts are applied', () {
      final r = keepRanges(10, [cut(2, 3, accepted: null), cut(4, 5, accepted: false), cut(6, 7)]);
      expect(r, [const TimeRange(0, 6), const TimeRange(7, 10)]);
    });

    test('overlapping and touching cuts merge', () {
      final r = keepRanges(10, [cut(5, 7), cut(2, 4), cut(3, 5.5)]);
      expect(r, [const TimeRange(0, 2), const TimeRange(7, 10)]);
    });

    test('cuts are clamped to the source duration', () {
      expect(keepRanges(8, [cut(6, 30)]), [const TimeRange(0, 6)]);
      expect(keepRanges(8, [cut(9, 11)]), [const TimeRange(0, 8)]);
      expect(keepRanges(8, [cut(-2, 1)]), [const TimeRange(1, 8)]);
    });

    test('slivers shorter than the minimum are dropped', () {
      expect(keepRanges(10, [cut(0.05, 9.95)]), isEmpty);
    });

    test('cutting everything leaves nothing', () {
      expect(keepRanges(5, [cut(0, 5)]), isEmpty);
      expect(keepRanges(0, []), isEmpty);
    });

    test('result is sorted, non-overlapping and inside the source (randomised)', () {
      final rnd = Random(7);
      for (var i = 0; i < 300; i++) {
        final duration = 1 + rnd.nextDouble() * 60;
        final cuts = List.generate(rnd.nextInt(8), (_) {
          final s = rnd.nextDouble() * duration * 1.2 - 2;
          return cut(s, s + rnd.nextDouble() * 10, accepted: rnd.nextBool() ? true : null);
        });
        final keep = keepRanges(duration, cuts);
        for (var k = 0; k < keep.length; k++) {
          expect(keep[k].start, greaterThanOrEqualTo(0));
          expect(keep[k].end, lessThanOrEqualTo(duration));
          expect(keep[k].duration, greaterThanOrEqualTo(minKeepSeconds));
          if (k > 0) expect(keep[k].start, greaterThanOrEqualTo(keep[k - 1].end));
        }
        // Nothing an accepted cut covers survives.
        for (final c in cuts.where((c) => c.accepted == true)) {
          for (final r in keep) {
            expect(r.end <= c.start || r.start >= c.end, isTrue, reason: '$r overlaps accepted $c');
          }
        }
      }
    });
  });

  group('buildManifest', () {
    test('matches the schema shape the server expects', () {
      final m = buildManifest(
        projectId: 'p1',
        mediaId: 'm1',
        keep: const [TimeRange(0, 1.23456), TimeRange(2, 4)],
        audio: AudioPreset.clean,
      );
      expect(m['schema_version'], '1.0');
      expect(m['output'], containsPair('width', 1080));
      expect(m['output'], containsPair('height', 1920));
      final items = (m['tracks'] as List).single['items'] as List;
      expect(items, hasLength(2));
      expect(items.first['start'], 0.0);
      expect(items.first['end'], 1.235);
      expect(items.first['source_media_id'], 'm1');
      expect(m['audio_adjustments'], containsPair('loudness_target_lufs', -16));
    });

    test('omits audio adjustments when off', () {
      final m = buildManifest(projectId: 'p', mediaId: 'm', keep: const [TimeRange(0, 1)]);
      expect(m.containsKey('audio_adjustments'), isFalse);
    });

    test('refuses an empty edit', () {
      expect(() => buildManifest(projectId: 'p', mediaId: 'm', keep: const []), throwsArgumentError);
    });
  });

  test('newUuid produces RFC 4122 v4 ids', () {
    final re = RegExp(r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$');
    final ids = List.generate(200, (_) => newUuid());
    expect(ids.every(re.hasMatch), isTrue);
    expect(ids.toSet(), hasLength(200));
  });
}
