import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:storyforge_mobile/app/app.dart';
import 'package:storyforge_mobile/core/api_client.dart';
import 'package:storyforge_mobile/core/models.dart';
import 'package:storyforge_mobile/core/providers.dart';
import 'package:storyforge_mobile/features/projects/project_screen.dart';

class MemoryTokenStore implements TokenStore {
  MemoryTokenStore([this.token]);
  String? token;
  @override
  Future<String?> read() async => token;
  @override
  Future<void> write(String t) async => token = t;
  @override
  Future<void> clear() async => token = null;
}

final _now = DateTime.utc(2026, 11, 16, 10);

Project project(String id, String title) =>
    Project(id: id, title: title, languagePreference: 'auto', outputPreset: 'reels', createdAt: _now, updatedAt: _now);

SystemInfo fakeSystemInfo({bool demo = true, String env = 'development'}) => SystemInfo(
  environment: env,
  maxUploadBytes: 100 * 1024 * 1024,
  maxDurationSeconds: 900,
  acceptedContentTypes: const ['video/mp4', 'video/quicktime'],
  retentionDays: 7,
  transcriptionProvider: demo ? 'mock' : 'faster_whisper',
  languageModelProvider: demo ? 'mock' : 'ollama',
  demoMode: demo,
);

/// In-memory backend with call recording. Jobs complete immediately.
class FakeApi implements StoryForgeApi {
  FakeApi({SystemInfo? info}) : info = info ?? fakeSystemInfo();

  SystemInfo info;
  String? token;
  final projects = <Project>[];
  final media = <String, List<MediaAsset>>{};
  final analysis = <String, AnalysisResult>{};
  final exports = <String, List<RenderJob>>{};
  final reviewed = <String, bool>{};
  final savedManifests = <Map<String, dynamic>>[];
  final uploads = <String>[];
  int manifestVersion = 0;
  String validationResult = 'completed';

  @override
  void setToken(String? t) => token = t;

  @override
  Future<SystemInfo> systemInfo() async => info;

  @override
  Future<String> devLogin(String email) async => 'token-for-$email';

  @override
  Future<List<Project>> listProjects() async => List.of(projects);

  @override
  Future<Project> createProject({required String title, required String language, required String preset}) async {
    final p = project('p${projects.length + 1}', title);
    projects.add(p);
    return p;
  }

  @override
  Future<Project> getProject(String id) async => projects.firstWhere((p) => p.id == id);

  @override
  Future<void> deleteProject(String id) async => projects.removeWhere((p) => p.id == id);

  @override
  Future<List<MediaAsset>> listMedia(String projectId) async => media[projectId] ?? [];

  @override
  Future<Uri> mediaPreviewUrl(String projectId, String mediaId) async => Uri.parse('http://test/preview');

  @override
  Future<JobStatus> uploadVideo({
    required String projectId,
    required String filePath,
    required String fileName,
    required int sizeBytes,
    required String contentType,
    required void Function(double fraction) onProgress,
    CancelToken? cancelToken,
  }) async {
    uploads.add('$fileName:$contentType');
    onProgress(0.5);
    onProgress(1);
    if (validationResult == 'completed') {
      media[projectId] = [
        MediaAsset(
          id: 'm1',
          status: 'ready',
          originalFilename: fileName,
          fileSizeBytes: sizeBytes,
          durationSeconds: 20,
          width: 1080,
          height: 1920,
          hasAudio: true,
        ),
      ];
    }
    return JobStatus(id: 'upload-job', status: 'queued', progress: 0);
  }

  @override
  Future<JobStatus> getJob(String jobId) async => JobStatus(
    id: jobId,
    status: jobId == 'upload-job' ? validationResult : 'completed',
    progress: 100,
    message: validationResult == 'completed' ? null : 'File signature does not match a supported video format.',
  );

  @override
  Future<JobStatus> startAnalysis(String projectId, {required String idempotencyKey}) async =>
      JobStatus(id: 'analysis-job', status: 'queued', progress: 0);

  @override
  Future<AnalysisResult> getAnalysis(String projectId) async =>
      analysis[projectId] ?? AnalysisResult(segments: [], cuts: [], captions: []);

  @override
  Future<CutProposal> reviewCut(String projectId, String cutId, {required bool accepted}) async {
    reviewed[cutId] = accepted;
    final c = analysis[projectId]!.cuts.firstWhere((c) => c.id == cutId);
    return CutProposal(
      id: c.id,
      start: c.start,
      end: c.end,
      reason: c.reason,
      cutType: c.cutType,
      confidence: c.confidence,
      accepted: accepted,
    );
  }

  @override
  Future<int> latestManifestVersion(String projectId) async => manifestVersion;

  @override
  Future<int> saveManifest(String projectId, Map<String, dynamic> manifest, {required int expectedVersion}) async {
    if (expectedVersion != manifestVersion) throw ApiException('conflict', statusCode: 409);
    savedManifests.add(manifest);
    return ++manifestVersion;
  }

  @override
  Future<RenderJob> startRender(String projectId, {required int manifestVersion, required String preset}) async {
    final job = RenderJob(
      id: 'r1',
      projectId: projectId,
      preset: preset,
      status: 'completed',
      progress: 100,
      createdAt: _now,
      sizeBytes: 2048000,
      durationSeconds: 18,
    );
    exports[projectId] = [job];
    return job;
  }

  @override
  Future<RenderJob> getRender(String renderId) async =>
      exports.values.expand((e) => e).firstWhere((r) => r.id == renderId);

  @override
  Future<List<RenderJob>> listExports(String projectId) async => exports[projectId] ?? [];

  @override
  Future<Uri> exportUrl(String renderId) async => Uri.parse('http://test/export');
}

/// Pump the full app (real router, theme and screens) on top of fakes.
Future<void> pumpApp(
  WidgetTester tester, {
  required FakeApi api,
  MemoryTokenStore? tokens,
  Future<VideoPick?> Function()? picker,
}) async {
  // 360 dp wide (small Android phone) catches horizontal overflow; tall so lazy lists stay built.
  tester.view.physicalSize = const Size(1080, 4800);
  tester.view.devicePixelRatio = 3;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    ProviderScope(
      retry: (_, __) => null,
      overrides: [
        apiProvider.overrideWithValue(api),
        tokenStoreProvider.overrideWithValue(tokens ?? MemoryTokenStore('existing-token')),
        apiBaseUrlProvider.overrideWithValue('http://localhost:8000'),
        videoPreviewEnabledProvider.overrideWithValue(false),
        if (picker != null) videoPickerProvider.overrideWithValue(picker),
      ],
      child: const StoryForgeApp(),
    ),
  );
  await tester.pumpAndSettle();
}
