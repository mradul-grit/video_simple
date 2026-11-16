// On-device end-to-end test against a real StoryForge backend.
//
// Run with scripts/run-device-e2e.ps1, which starts the stack, copies a test clip
// into the app's private files dir, and runs `flutter drive` (screenshots land in
// mobile/build/e2e_screenshots). Only the system file picker is replaced.
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:storyforge_mobile/app/app.dart';
import 'package:storyforge_mobile/core/providers.dart';
import 'package:storyforge_mobile/features/projects/project_screen.dart';
import 'package:video_player/video_player.dart';

const clipPath = String.fromEnvironment('SF_E2E_CLIP', defaultValue: '/data/user/0/dev.storyforge.storyforge_mobile/files/e2e_clip.mp4');

Future<void> pumpUntil(WidgetTester tester, Finder finder, {Duration timeout = const Duration(seconds: 60)}) async {
  final end = DateTime.now().add(timeout);
  while (DateTime.now().isBefore(end)) {
    await tester.pump(const Duration(milliseconds: 250));
    if (finder.evaluate().isNotEmpty) return;
  }
  throw TestFailure('Timed out after ${timeout.inSeconds}s waiting for $finder');
}

void main() {
  final binding = IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  Future<void> shot(WidgetTester tester, String name) async {
    await tester.pump(const Duration(milliseconds: 400));
    await binding.takeScreenshot(name);
  }

  testWidgets('record-to-export flow against the real backend', (tester) async {
    final clip = File(clipPath);
    expect(clip.existsSync(), isTrue, reason: 'push the test clip first (see scripts/run-device-e2e.ps1)');
    await SecureTokenStore().clear(); // start signed out
    await binding.convertFlutterSurfaceToImage();

    await tester.pumpWidget(ProviderScope(
      overrides: [
        videoPickerProvider.overrideWithValue(() async => (path: clip.path, name: 'e2e_clip.mp4', size: clip.lengthSync())),
      ],
      child: const StoryForgeApp(),
    ));

    // Sign in (development endpoint on the local server).
    await pumpUntil(tester, find.text('Development sign-in'));
    await shot(tester, '01_sign_in');
    await tester.enterText(find.byType(TextFormField), 'device-${DateTime.now().millisecondsSinceEpoch}@example.com');
    await tester.tap(find.text('Continue'));
    await pumpUntil(tester, find.text('No projects yet'));
    await shot(tester, '02_home_empty');

    // Create a project.
    await tester.tap(find.text('New video'));
    await pumpUntil(tester, find.text('Create project'));
    await tester.enterText(find.byType(TextFormField), 'How a tap washer works');
    await tester.testTextInput.receiveAction(TextInputAction.done);
    await tester.pump(const Duration(milliseconds: 500));
    await shot(tester, '03_new_project');
    await tester.tap(find.text('Create project'));

    // Upload a real file over HTTP, then wait for the worker's ffprobe validation.
    await pumpUntil(tester, find.text('Choose video'));
    await shot(tester, '04_project_empty');
    await tester.tap(find.text('Choose video'));
    await pumpUntil(tester, find.text('Upload this video?'));
    await shot(tester, '05_consent');
    await tester.tap(find.text('Upload'));
    await pumpUntil(tester, find.text('Analyse video'), timeout: const Duration(seconds: 90));
    expect(find.text('Original kept'), findsOneWidget);
    await shot(tester, '06_uploaded');

    // Analyse (mock providers on the dev server; the demo banner must be visible).
    await tester.tap(find.text('Analyse video'));
    await pumpUntil(tester, find.text('Open editor'), timeout: const Duration(seconds: 90));
    expect(find.textContaining('Demo mode'), findsOneWidget);
    await shot(tester, '07_analysed');

    // Editor: real video preview, accept the suggested pause cut.
    await tester.tap(find.text('Open editor'));
    await pumpUntil(tester, find.text('Export video'));
    await pumpUntil(tester, find.byType(VideoPlayer), timeout: const Duration(seconds: 30));
    await shot(tester, '08_editor');
    final cut = find.widgetWithText(FilledButton, 'Cut');
    expect(cut, findsWidgets, reason: 'pause detection should find the 6-8 s silence');
    await tester.tap(cut.first);
    // 12 s clip with silence 6-8 s; the cut keeps 0.15 s padding each side: 12 - 1.7 = 10.3 s.
    await pumpUntil(tester, find.textContaining('Result 0:10 of 0:12'));
    await shot(tester, '09_cut_accepted');

    // Export and wait for the worker's ffmpeg render + ffprobe verification.
    await tester.tap(find.text('Export video'));
    await pumpUntil(tester, find.text('Ready'), timeout: const Duration(minutes: 4));
    await shot(tester, '10_exports');

    // Play the export through its short-lived signed URL.
    await tester.tap(find.text('How a tap washer works'));
    await pumpUntil(tester, find.byType(VideoPlayer), timeout: const Duration(seconds: 30));
    await tester.pump(const Duration(seconds: 2));
    await shot(tester, '11_export_player');
  });
}
