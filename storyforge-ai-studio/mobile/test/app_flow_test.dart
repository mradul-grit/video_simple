import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:storyforge_mobile/core/models.dart';
import 'package:storyforge_mobile/features/projects/project_screen.dart';

import 'fakes.dart';

AnalysisResult demoAnalysis() => AnalysisResult(
  segments: [
    TranscriptSegment(id: 's0', start: 0, end: 4, text: '[DEMO] Hello everyone', isSpeech: true, confidence: 0.9),
    TranscriptSegment(id: 's1', start: 4, end: 6, text: '', isSpeech: false),
    TranscriptSegment(id: 's2', start: 6, end: 20, text: '[DEMO] The key insight', isSpeech: true, confidence: 0.4),
  ],
  cuts: [
    CutProposal(id: 'c1', start: 4, end: 6, reason: '[DEMO] Silence detected', cutType: 'pause', confidence: 0.8),
    CutProposal(id: 'c2', start: 10, end: 12, reason: '[DEMO] Filler', cutType: 'filler', confidence: 0.5),
  ],
  captions: [
    EditorialCaption(
      id: 'k1',
      start: 0,
      end: 4,
      text: '[DEMO CAPTION] Hello',
      segmentIds: ['s0'],
      lowConfidence: false,
    ),
  ],
);

void main() {
  testWidgets('signed-out user sees dev sign-in and lands on an empty Home', (tester) async {
    final tokens = MemoryTokenStore();
    final api = FakeApi();
    await pumpApp(tester, api: api, tokens: tokens);

    expect(find.text('Development sign-in'), findsOneWidget);
    // Regression (seen on device): the logo badge stretched to the full column width.
    final badge = find.ancestor(of: find.byIcon(Icons.auto_awesome_motion_rounded), matching: find.byType(Container));
    expect(tester.getSize(badge.first), const Size(56, 56));
    await tester.tap(find.text('Continue'));
    await tester.pumpAndSettle();
    expect(find.text('Enter a valid email'), findsOneWidget);

    await tester.enterText(find.byType(TextFormField), 'me@example.com');
    await tester.tap(find.text('Continue'));
    await tester.pumpAndSettle();

    expect(tokens.token, 'token-for-me@example.com');
    expect(api.token, 'token-for-me@example.com');
    expect(find.text('Your videos'), findsOneWidget);
    expect(find.text('No projects yet'), findsOneWidget);
  });

  testWidgets('sign-in is not offered when the server is not in development mode', (tester) async {
    await pumpApp(tester, api: FakeApi(info: fakeSystemInfo(env: 'production')), tokens: MemoryTokenStore());
    expect(find.text('Sign-in not available yet'), findsOneWidget);
    expect(find.text('Continue'), findsNothing);
  });

  testWidgets('bottom navigation reaches Exports and Settings with honest content', (tester) async {
    await pumpApp(tester, api: FakeApi());
    await tester.tap(find.text('Exports'));
    await tester.pumpAndSettle();
    expect(find.text('No exports yet'), findsOneWidget);

    await tester.tap(find.text('Settings'));
    await tester.pumpAndSettle();
    expect(find.text('Demo (placeholder text)'), findsNWidgets(2));
    expect(find.text('7 days'), findsOneWidget);

    await tester.tap(find.text('Sign out'));
    await tester.pumpAndSettle();
    expect(find.text('Development sign-in'), findsOneWidget);
  });

  testWidgets('create a project, upload with consent, analyse, open the editor', (tester) async {
    final api = FakeApi();
    await pumpApp(tester, api: api, picker: () async => (path: '/tmp/talk.mp4', name: 'talk.mp4', size: 5000000));

    await tester.tap(find.text('New video'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Create project'));
    await tester.pumpAndSettle();
    expect(find.text('Give your video a title'), findsOneWidget);

    await tester.enterText(find.byType(TextFormField), 'How a tap works');
    await tester.tap(find.text('Create project'));
    await tester.pumpAndSettle();

    expect(find.text('How a tap works'), findsOneWidget);
    expect(find.textContaining('up to 100.0 MB'), findsOneWidget);
    expect(find.textContaining('Demo mode'), findsOneWidget);

    await tester.tap(find.text('Choose video'));
    await tester.pumpAndSettle();
    expect(find.text('Upload this video?'), findsOneWidget);
    expect(find.textContaining('localhost'), findsOneWidget);
    await tester.tap(find.text('Upload'));
    await tester.pumpAndSettle();

    expect(api.uploads, ['talk.mp4:video/mp4']);
    expect(find.text('talk.mp4'), findsOneWidget);
    expect(find.text('Original kept'), findsOneWidget);

    api.analysis['p1'] = demoAnalysis();
    await tester.tap(find.text('Analyse video'));
    await tester.pumpAndSettle();
    expect(find.text('Ready to edit'), findsOneWidget);

    await tester.tap(find.text('Open editor'));
    await tester.pumpAndSettle();
    expect(find.text('Edit'), findsOneWidget);
    expect(find.textContaining('2 cuts to review'), findsOneWidget);
  });

  testWidgets('declining the consent dialog uploads nothing', (tester) async {
    final api = FakeApi()..projects.add(project('p1', 'Draft'));
    await pumpApp(tester, api: api, picker: () async => (path: '/tmp/a.mp4', name: 'a.mp4', size: 10));
    await tester.tap(find.text('Draft'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Choose video'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Cancel'));
    await tester.pumpAndSettle();
    expect(api.uploads, isEmpty);
  });

  testWidgets('unsupported and oversized files are rejected before upload', (tester) async {
    final api = FakeApi()..projects.add(project('p1', 'Draft'));
    VideoPick next = (path: '/tmp/a.exe', name: 'a.exe', size: 10);
    await pumpApp(tester, api: api, picker: () async => next);
    await tester.tap(find.text('Draft'));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Choose video'));
    await tester.pumpAndSettle();
    expect(find.textContaining('isn\u2019t supported'), findsOneWidget);

    next = (path: '/tmp/big.mp4', name: 'big.mp4', size: 200 * 1024 * 1024);
    await tester.tap(find.text('Choose video'));
    await tester.pumpAndSettle();
    expect(find.textContaining('The limit is 100.0 MB'), findsOneWidget);
    expect(api.uploads, isEmpty);
  });

  testWidgets('server-side validation failure is shown and the upload can be retried', (tester) async {
    final api =
        FakeApi()
          ..projects.add(project('p1', 'Draft'))
          ..validationResult = 'failed';
    await pumpApp(tester, api: api, picker: () async => (path: '/tmp/a.mp4', name: 'a.mp4', size: 10));
    await tester.tap(find.text('Draft'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Choose video'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Upload'));
    await tester.pumpAndSettle();
    expect(find.textContaining('File signature does not match'), findsOneWidget);
    expect(find.text('Choose video'), findsOneWidget);
  });

  testWidgets('editor applies only accepted cuts when exporting', (tester) async {
    final api =
        FakeApi()
          ..projects.add(project('p1', 'Draft'))
          ..media['p1'] = [
            MediaAsset(
              id: 'm1',
              status: 'ready',
              originalFilename: 'a.mp4',
              durationSeconds: 20,
              width: 1080,
              height: 1920,
            ),
          ]
          ..analysis['p1'] = demoAnalysis();
    await pumpApp(tester, api: api);
    await tester.tap(find.text('Draft'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Open editor'));
    await tester.pumpAndSettle();

    expect(find.text('Review'), findsNWidgets(2));
    expect(find.textContaining('low, listen before cutting'), findsOneWidget);

    // Accept the first cut, keep the second.
    await tester.tap(find.widgetWithText(FilledButton, 'Cut').first);
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(OutlinedButton, 'Keep').last);
    await tester.pumpAndSettle();
    expect(api.reviewed, {'c1': true, 'c2': false});
    expect(find.textContaining('Result 0:18 of 0:20'), findsOneWidget);

    await tester.tap(find.text('Export video'));
    await tester.pumpAndSettle();

    final items = (api.savedManifests.single['tracks'] as List).single['items'] as List;
    expect(
      [
        for (final i in items) [i['start'], i['end']],
      ],
      [
        [0.0, 4.0],
        [6.0, 20.0],
      ],
    );
    expect(api.savedManifests.single['audio_adjustments'], isNotNull);
    expect(find.text('Exports'), findsWidgets);
    expect(find.text('Ready'), findsOneWidget);
  });

  testWidgets('editor shows transcript and grounded key points', (tester) async {
    final api =
        FakeApi()
          ..projects.add(project('p1', 'Draft'))
          ..media['p1'] = [MediaAsset(id: 'm1', status: 'ready', durationSeconds: 20, width: 1080, height: 1920)]
          ..analysis['p1'] = demoAnalysis();
    await pumpApp(tester, api: api);
    await tester.tap(find.text('Draft'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Open editor'));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Transcript'));
    await tester.pumpAndSettle();
    expect(find.text('[DEMO] Hello everyone'), findsOneWidget);
    expect(find.text('Low confidence, check this line'), findsOneWidget);

    await tester.tap(find.text('Key points'));
    await tester.pumpAndSettle();
    expect(find.text('[DEMO CAPTION] Hello'), findsOneWidget);
    expect(find.textContaining('\u201c[DEMO] Hello everyone\u201d'), findsOneWidget);
  });

  testWidgets('deleting a project asks first and returns Home', (tester) async {
    final api = FakeApi()..projects.add(project('p1', 'Draft'));
    await pumpApp(tester, api: api);
    await tester.tap(find.text('Draft'));
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Project options'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Delete project'));
    await tester.pumpAndSettle();
    expect(find.text('Delete this project?'), findsOneWidget);
    await tester.tap(find.text('Delete'));
    await tester.pumpAndSettle();
    expect(api.projects, isEmpty);
    expect(find.text('No projects yet'), findsOneWidget);
  });

  testWidgets('a server error offers retry', (tester) async {
    final api = _FailingProjectsApi();
    await pumpApp(tester, api: api);
    expect(find.text("Couldn't load this"), findsOneWidget);
    api.fail = false;
    await tester.tap(find.text('Try again'));
    await tester.pumpAndSettle();
    expect(find.text('No projects yet'), findsOneWidget);
  });
}

class _FailingProjectsApi extends FakeApi {
  bool fail = true;
  @override
  Future<List<Project>> listProjects() async {
    if (fail) throw Exception("Can't reach the StoryForge server.");
    return super.listProjects();
  }
}
