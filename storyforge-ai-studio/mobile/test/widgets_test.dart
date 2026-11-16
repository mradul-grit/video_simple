import 'package:flutter_test/flutter_test.dart';
import 'package:storyforge_mobile/shared/widgets.dart';

void main() {
  test('plural', () {
    expect(plural(0, 'suggested cut'), '0 suggested cuts');
    expect(plural(1, 'suggested cut'), '1 suggested cut');
    expect(plural(3, 'key-point caption'), '3 key-point captions');
  });

  test('formatDuration and formatBytes', () {
    expect(formatDuration(null), '–');
    expect(formatDuration(10.3), '0:10');
    expect(formatDuration(125), '2:05');
    expect(formatBytes(241691), '236 KB');
    expect(formatBytes(5 * 1024 * 1024), '5.0 MB');
  });
}
