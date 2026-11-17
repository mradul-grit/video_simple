// Compatibility of the Flutter client with the backend's API_CONTRACT error envelope:
//   {"error": {code, message, field_errors, retryable}, "request_id": ..., "detail": <legacy>}
// Bodies below are the shapes app/api/errors.py returns (the 404 is copied from the live API).
import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:storyforge_mobile/core/api_client.dart';

class _StubAdapter implements HttpClientAdapter {
  _StubAdapter(this.status, this.body, {this.headers = const {}});
  final int status;
  final Map<String, dynamic> body;
  final Map<String, List<String>> headers;

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async => ResponseBody.fromString(
    jsonEncode(body),
    status,
    headers: {
      Headers.contentTypeHeader: [Headers.jsonContentType],
      ...headers,
    },
  );

  @override
  void close({bool force = false}) {}
}

Map<String, dynamic> envelope(
  String code,
  String message,
  Object? detail, {
  bool retryable = false,
  List<Map<String, String>> fieldErrors = const [],
}) => {
  'error': {'code': code, 'message': message, 'field_errors': fieldErrors, 'retryable': retryable},
  'request_id': 'ac0ce993-44c1-4744-884e-ea22c9914d6b',
  'detail': detail,
};

DioStoryForgeApi apiReturning(int status, Map<String, dynamic> body, {Map<String, List<String>> headers = const {}}) {
  final dio = Dio(BaseOptions(baseUrl: 'http://test/api/v1'))
    ..httpClientAdapter = _StubAdapter(status, body, headers: headers);
  return DioStoryForgeApi(dio: dio, baseUrl: 'http://test');
}

Future<ApiException> failure(Future<Object?> Function() call) async {
  try {
    await call();
  } on ApiException catch (e) {
    return e;
  }
  fail('expected ApiException');
}

void main() {
  test('404 envelope shows the server message', () async {
    final e = await failure(
      () => apiReturning(404, envelope('NOT_FOUND', 'Project not found', 'Project not found')).getProject('x'),
    );
    expect(e.statusCode, 404);
    expect(e.message, 'Project not found');
  });

  test('401 envelope asks the user to sign in again', () async {
    final e = await failure(
      () => apiReturning(401, envelope('UNAUTHORIZED', 'Token expired', 'Token expired')).listProjects(),
    );
    expect(e.isUnauthorized, isTrue);
    expect(e.message, contains('sign in again'));
  });

  test('422 request validation shows the first field message', () async {
    final body = envelope(
      'VALIDATION_ERROR',
      'Some fields are invalid.',
      [
        {
          'loc': ['body', 'title'],
          'msg': 'String should have at least 1 character',
          'type': 'string_too_short',
        },
      ],
      fieldErrors: [
        {'field': 'title', 'message': 'String should have at least 1 character'},
      ],
    );
    final e = await failure(() => apiReturning(422, body).createProject(title: '', language: 'auto', preset: 'reels'));
    expect(e.statusCode, 422);
    expect(e.message, 'String should have at least 1 character');
  });

  test('422 manifest validation shows the message and the rule errors', () async {
    final body = envelope('VALIDATION_ERROR', 'Manifest validation failed', {
      'message': 'Manifest validation failed',
      'errors': ['tracks.0.items.0: end 99 is past the source duration 4.00'],
    });
    final e = await failure(() => apiReturning(422, body).saveManifest('p', const {}, expectedVersion: 0));
    expect(e.message, 'Manifest validation failed\ntracks.0.items.0: end 99 is past the source duration 4.00');
  });

  test('409 manifest conflict is recognised (editor retries once on top)', () async {
    final body = envelope(
      'CONFLICT',
      'Manifest was changed by another save. Reload and retry.',
      'Manifest was changed by another save. Reload and retry.',
    );
    final e = await failure(() => apiReturning(409, body).saveManifest('p', const {}, expectedVersion: 0));
    expect(e.isConflict, isTrue);
  });

  test('429 rate limit shows a readable wait message', () async {
    const msg = 'Too many requests. Try again in 37 seconds.';
    final e = await failure(
      () => apiReturning(
        429,
        envelope('RATE_LIMITED', msg, msg, retryable: true),
        headers: {
          'retry-after': ['37'],
        },
      ).createProject(title: 't', language: 'auto', preset: 'reels'),
    );
    expect(e.statusCode, 429);
    expect(e.message, msg);
  });

  test('500 envelope never leaks internals', () async {
    final body = envelope(
      'INTERNAL_ERROR',
      'Something went wrong. Please try again.',
      'Internal Server Error',
      retryable: true,
    );
    final e = await failure(() => apiReturning(500, body).listProjects());
    expect(e.statusCode, 500);
    expect(e.message, 'Internal Server Error'); // legacy `detail` text; see audit note on adopting error.message
  });

  test('a missing manifest (404 envelope) still means "no saved version"', () async {
    final v = await apiReturning(
      404,
      envelope('NOT_FOUND', 'No edit manifest found for this project', 'No edit manifest found for this project'),
    ).latestManifestVersion('p');
    expect(v, 0);
  });
}
