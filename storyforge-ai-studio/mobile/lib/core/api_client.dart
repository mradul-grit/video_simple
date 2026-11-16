import 'dart:async';
import 'dart:io';
import 'dart:math';

import 'package:dio/dio.dart';

import 'config.dart';
import 'models.dart';

/// User-safe API error. [message] is suitable to show on screen.
class ApiException implements Exception {
  ApiException(this.message, {this.statusCode});

  final String message;
  final int? statusCode;

  bool get isUnauthorized => statusCode == 401;
  bool get isConflict => statusCode == 409;

  @override
  String toString() => message;
}

/// Thrown when the user cancels an upload.
class UploadCancelled implements Exception {}

/// Everything the app needs from the backend. A fake implements this in tests.
abstract interface class StoryForgeApi {
  void setToken(String? token);

  Future<SystemInfo> systemInfo();
  Future<String> devLogin(String email);

  Future<List<Project>> listProjects();
  Future<Project> createProject({required String title, required String language, required String preset});
  Future<Project> getProject(String id);
  Future<void> deleteProject(String id);

  Future<List<MediaAsset>> listMedia(String projectId);

  /// Absolute, short-lived URL to play the original in the editor.
  Future<Uri> mediaPreviewUrl(String projectId, String mediaId);

  /// Grant -> streamed PUT -> complete. Returns the validation job.
  Future<JobStatus> uploadVideo({
    required String projectId,
    required String filePath,
    required String fileName,
    required int sizeBytes,
    required String contentType,
    required void Function(double fraction) onProgress,
    CancelToken? cancelToken,
  });

  Future<JobStatus> getJob(String jobId);
  Future<JobStatus> startAnalysis(String projectId, {required String idempotencyKey});
  Future<AnalysisResult> getAnalysis(String projectId);
  Future<CutProposal> reviewCut(String projectId, String cutId, {required bool accepted});

  /// Latest saved manifest version, or 0 when none exists.
  Future<int> latestManifestVersion(String projectId);
  Future<int> saveManifest(String projectId, Map<String, dynamic> manifest, {required int expectedVersion});

  Future<RenderJob> startRender(String projectId, {required int manifestVersion, required String preset});
  Future<RenderJob> getRender(String renderId);
  Future<List<RenderJob>> listExports(String projectId);

  /// Absolute, short-lived URL for playing or downloading an export.
  Future<Uri> exportUrl(String renderId);
}

class DioStoryForgeApi implements StoryForgeApi {
  DioStoryForgeApi({Dio? dio, String baseUrl = AppConfig.apiBaseUrl})
    : _base = baseUrl,
      _dio =
          dio ??
          Dio(
            BaseOptions(
              baseUrl: '$baseUrl${AppConfig.apiPrefix}',
              connectTimeout: const Duration(seconds: 10),
              receiveTimeout: const Duration(seconds: 30),
            ),
          );

  final Dio _dio;
  final String _base;
  String? _token;

  @override
  void setToken(String? token) => _token = token;

  Options get _auth => Options(headers: {if (_token != null) 'Authorization': 'Bearer $_token'});

  Future<T> _guard<T>(Future<T> Function() run) async {
    try {
      return await run();
    } on DioException catch (e) {
      if (CancelToken.isCancel(e)) throw UploadCancelled();
      throw _toApiException(e);
    }
  }

  static ApiException _toApiException(DioException e) {
    final status = e.response?.statusCode;
    if (status == null) {
      return ApiException("Can't reach the StoryForge server. Check your connection and try again.");
    }
    final data = e.response?.data;
    String? detail;
    if (data is Map) {
      final d = data['detail'];
      if (d is String) detail = d;
      if (d is Map && d['message'] is String) {
        final errors = (d['errors'] as List?)?.cast<String>() ?? const [];
        detail = [d['message'] as String, ...errors.take(3)].join('\n');
      }
      if (d is List && d.isNotEmpty && d.first is Map) detail = (d.first as Map)['msg']?.toString();
    }
    return ApiException(switch (status) {
      401 => 'Your session has ended. Please sign in again.',
      404 => detail ?? 'Not found.',
      _ => detail ?? 'Something went wrong (HTTP $status).',
    }, statusCode: status);
  }

  Map<String, dynamic> _map(Response r) => (r.data as Map).cast<String, dynamic>();

  @override
  Future<SystemInfo> systemInfo() => _guard(() async => SystemInfo.fromJson(_map(await _dio.get('/system/info'))));

  @override
  Future<String> devLogin(String email) => _guard(() async {
    final r = await _dio.post('/auth/dev-login', data: {'email': email});
    return _map(r)['access_token'] as String;
  });

  @override
  Future<List<Project>> listProjects() => _guard(() async {
    final r = await _dio.get('/projects', queryParameters: {'limit': 100}, options: _auth);
    return [for (final p in _map(r)['items'] as List) Project.fromJson((p as Map).cast())];
  });

  @override
  Future<Project> createProject({required String title, required String language, required String preset}) => _guard(
    () async => Project.fromJson(
      _map(
        await _dio.post(
          '/projects',
          data: {'title': title, 'language_preference': language, 'output_preset': preset},
          options: _auth,
        ),
      ),
    ),
  );

  @override
  Future<Project> getProject(String id) =>
      _guard(() async => Project.fromJson(_map(await _dio.get('/projects/$id', options: _auth))));

  @override
  Future<void> deleteProject(String id) => _guard(() async {
    await _dio.delete('/projects/$id', options: _auth);
  });

  @override
  Future<List<MediaAsset>> listMedia(String projectId) => _guard(() async {
    final r = await _dio.get('/projects/$projectId/media', options: _auth);
    return [for (final m in r.data as List) MediaAsset.fromJson((m as Map).cast())];
  });

  @override
  Future<Uri> mediaPreviewUrl(String projectId, String mediaId) => _guard(() async {
    final r = await _dio.post('/projects/$projectId/media/$mediaId/preview-url', options: _auth);
    return Uri.parse('$_base${_map(r)['url']}');
  });

  @override
  Future<JobStatus> uploadVideo({
    required String projectId,
    required String filePath,
    required String fileName,
    required int sizeBytes,
    required String contentType,
    required void Function(double fraction) onProgress,
    CancelToken? cancelToken,
  }) => _guard(() async {
    final grant = _map(
      await _dio.post(
        '/projects/$projectId/media/upload-url',
        data: {'filename': fileName, 'content_type': contentType, 'expected_bytes': sizeBytes},
        options: _auth,
      ),
    );
    // The grant URL carries its own signature; the bearer token is not sent to storage.
    // The file is streamed from disk, never loaded whole into memory.
    await Dio().put<void>(
      '$_base${grant['upload_url']}',
      data: File(filePath).openRead(),
      options: Options(
        headers: {Headers.contentLengthHeader: sizeBytes, Headers.contentTypeHeader: contentType},
        sendTimeout: const Duration(minutes: 30),
      ),
      cancelToken: cancelToken,
      onSendProgress: (sent, total) => onProgress(total > 0 ? sent / total : 0),
    );
    final job = await _dio.post(
      '/projects/$projectId/media/complete',
      data: {'media_asset_id': grant['media_asset_id']},
      options: _auth,
    );
    return JobStatus.fromJson(_map(job));
  });

  @override
  Future<JobStatus> getJob(String jobId) =>
      _guard(() async => JobStatus.fromJson(_map(await _dio.get('/jobs/$jobId', options: _auth))));

  @override
  Future<JobStatus> startAnalysis(String projectId, {required String idempotencyKey}) => _guard(
    () async => JobStatus.fromJson(
      _map(await _dio.post('/projects/$projectId/analysis', data: {'idempotency_key': idempotencyKey}, options: _auth)),
    ),
  );

  @override
  Future<AnalysisResult> getAnalysis(String projectId) => _guard(
    () async => AnalysisResult.fromJson(_map(await _dio.get('/projects/$projectId/analysis', options: _auth))),
  );

  @override
  Future<CutProposal> reviewCut(String projectId, String cutId, {required bool accepted}) => _guard(
    () async => CutProposal.fromJson(
      _map(await _dio.patch('/projects/$projectId/cuts/$cutId', data: {'accepted': accepted}, options: _auth)),
    ),
  );

  @override
  Future<int> latestManifestVersion(String projectId) async {
    try {
      final r = await _dio.get('/projects/$projectId/edit-manifest', options: _auth);
      return _map(r)['version'] as int;
    } on DioException catch (e) {
      if (e.response?.statusCode == 404) return 0;
      throw _toApiException(e);
    }
  }

  @override
  Future<int> saveManifest(String projectId, Map<String, dynamic> manifest, {required int expectedVersion}) =>
      _guard(() async {
        final r = await _dio.put(
          '/projects/$projectId/edit-manifest',
          data: {'expected_version': expectedVersion, 'manifest_json': manifest},
          options: _auth,
        );
        return _map(r)['version'] as int;
      });

  @override
  Future<RenderJob> startRender(String projectId, {required int manifestVersion, required String preset}) => _guard(
    () async => RenderJob.fromJson(
      _map(
        await _dio.post(
          '/projects/$projectId/renders',
          data: {'manifest_version': manifestVersion, 'preset': preset},
          options: _auth,
        ),
      ),
    ),
  );

  @override
  Future<RenderJob> getRender(String renderId) =>
      _guard(() async => RenderJob.fromJson(_map(await _dio.get('/renders/$renderId', options: _auth))));

  @override
  Future<List<RenderJob>> listExports(String projectId) => _guard(() async {
    final r = await _dio.get('/projects/$projectId/exports', options: _auth);
    return [for (final j in r.data as List) RenderJob.fromJson((j as Map).cast())];
  });

  @override
  Future<Uri> exportUrl(String renderId) => _guard(() async {
    final r = await _dio.post('/exports/$renderId/download-url', options: _auth);
    return Uri.parse('$_base${_map(r)['url']}');
  });
}

/// Poll [fetch] until [isDone] or the timeout. [isActive] lets a screen stop polling on dispose.
///
/// The job keeps running on the server whatever happens here, so a dropped request must not
/// end the wait: transient failures (no connection, 5xx) are retried with a growing delay
/// until the deadline. Client errors (4xx) are real answers and are rethrown at once.
Future<T> pollUntil<T>(
  Future<T> Function() fetch, {
  required bool Function(T) isDone,
  void Function(T)? onUpdate,
  bool Function()? isActive,
  Duration interval = AppConfig.pollInterval,
  Duration timeout = AppConfig.pollTimeout,
}) async {
  final deadline = DateTime.now().add(timeout);
  var failures = 0;
  while (true) {
    final T value;
    try {
      value = await fetch();
      failures = 0;
    } on ApiException catch (e) {
      final transient = e.statusCode == null || e.statusCode! >= 500;
      if (!transient) rethrow;
      if (isActive != null && !isActive()) rethrow;
      if (DateTime.now().isAfter(deadline)) {
        throw ApiException('Lost contact with the server. Your job keeps running there; check back later.');
      }
      failures++;
      await Future<void>.delayed(interval * min(failures, 5));
      continue;
    }
    onUpdate?.call(value);
    if (isDone(value)) return value;
    if (isActive != null && !isActive()) return value;
    if (DateTime.now().isAfter(deadline)) {
      throw ApiException('This is taking longer than expected. It will keep running; check back later.');
    }
    await Future<void>.delayed(interval);
  }
}
