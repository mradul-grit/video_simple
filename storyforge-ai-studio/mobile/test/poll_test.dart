import 'package:flutter_test/flutter_test.dart';
import 'package:storyforge_mobile/core/api_client.dart';

/// Returns scripted results in order: an [ApiException] is thrown, anything else is returned.
Future<String> Function() scripted(List<Object> steps, List<int> calls) => () async {
  calls.add(1);
  final next = steps.removeAt(0);
  if (next is ApiException) throw next;
  return next as String;
};

void main() {
  test('dropped requests do not end the wait (regression: device e2e lost a finished render)', () async {
    final calls = <int>[];
    final result = await pollUntil(
      scripted([
        'rendering',
        ApiException('no connection'),
        ApiException('bad gateway', statusCode: 502),
        'completed',
      ], calls),
      isDone: (s) => s == 'completed',
      interval: Duration.zero,
    );
    expect(result, 'completed');
    expect(calls, hasLength(4));
  });

  test('client errors are real answers and stop polling at once', () async {
    final calls = <int>[];
    await expectLater(
      pollUntil(
        scripted(['rendering', ApiException('not found', statusCode: 404), 'completed'], calls),
        isDone: (s) => s == 'completed',
        interval: Duration.zero,
      ),
      throwsA(isA<ApiException>().having((e) => e.statusCode, 'status', 404)),
    );
    expect(calls, hasLength(2));
  });

  test('a server that never comes back fails with a clear message at the deadline', () async {
    final steps = List<Object>.generate(10000, (_) => ApiException('no connection'));
    await expectLater(
      pollUntil(
        scripted(steps, []),
        isDone: (s) => s == 'completed',
        interval: Duration.zero,
        timeout: const Duration(milliseconds: 50),
      ),
      throwsA(isA<ApiException>().having((e) => e.message, 'message', contains('keeps running'))),
    );
  });

  test('stops when the screen goes away', () async {
    final calls = <int>[];
    var active = true;
    final result = await pollUntil(
      scripted(['queued', 'rendering', 'completed'], calls),
      isDone: (s) => s == 'completed',
      onUpdate: (_) => active = false,
      isActive: () => active,
      interval: Duration.zero,
    );
    expect(result, 'queued');
    expect(calls, hasLength(1));
  });
}
