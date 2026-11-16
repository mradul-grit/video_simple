// Wire models for the StoryForge API (/api/v1). Hand-written for now; replace
// with OpenAPI-generated models once the API surface settles (ARCHITECTURE.md).

DateTime _date(Object? v) => DateTime.parse(v as String).toLocal();
double? _dbl(Object? v) => v == null ? null : (v as num).toDouble();
List<String> _ids(Object? v) => (v as List? ?? const []).cast<String>();

class Project {
  Project({
    required this.id,
    required this.title,
    required this.languagePreference,
    required this.outputPreset,
    required this.createdAt,
    required this.updatedAt,
  });

  factory Project.fromJson(Map<String, dynamic> j) => Project(
    id: j['id'] as String,
    title: j['title'] as String,
    languagePreference: j['language_preference'] as String,
    outputPreset: j['output_preset'] as String,
    createdAt: _date(j['created_at']),
    updatedAt: _date(j['updated_at']),
  );

  final String id;
  final String title;
  final String languagePreference;
  final String outputPreset;
  final DateTime createdAt;
  final DateTime updatedAt;
}

class MediaAsset {
  MediaAsset({
    required this.id,
    required this.status,
    this.originalFilename,
    this.fileSizeBytes,
    this.durationSeconds,
    this.width,
    this.height,
    this.hasAudio,
  });

  factory MediaAsset.fromJson(Map<String, dynamic> j) => MediaAsset(
    id: j['id'] as String,
    status: j['status'] as String,
    originalFilename: j['original_filename'] as String?,
    fileSizeBytes: j['file_size_bytes'] as int?,
    durationSeconds: _dbl(j['duration_seconds']),
    width: j['width'] as int?,
    height: j['height'] as int?,
    hasAudio: j['has_audio'] as bool?,
  );

  final String id;
  final String status;
  final String? originalFilename;
  final int? fileSizeBytes;
  final double? durationSeconds;
  final int? width;
  final int? height;
  final bool? hasAudio;

  bool get isReady => status == 'ready';
}

class JobStatus {
  JobStatus({required this.id, required this.status, required this.progress, this.stage, this.message});

  factory JobStatus.fromJson(Map<String, dynamic> j) => JobStatus(
    id: j['id'] as String,
    status: j['status'] as String,
    progress: (j['progress'] as num?)?.toInt() ?? 0,
    stage: j['stage'] as String?,
    message: j['message'] as String?,
  );

  final String id;
  final String status;
  final int progress;
  final String? stage;
  final String? message;

  bool get isTerminal => const {'completed', 'failed', 'cancelled'}.contains(status);
  bool get succeeded => status == 'completed';
}

class TranscriptSegment {
  TranscriptSegment({
    required this.id,
    required this.start,
    required this.end,
    required this.text,
    required this.isSpeech,
    this.confidence,
  });

  factory TranscriptSegment.fromJson(Map<String, dynamic> j) => TranscriptSegment(
    id: j['id'] as String,
    start: _dbl(j['start_seconds'])!,
    end: _dbl(j['end_seconds'])!,
    text: j['text'] as String,
    isSpeech: j['is_speech'] as bool,
    confidence: _dbl(j['confidence']),
  );

  final String id;
  final double start;
  final double end;
  final String text;
  final bool isSpeech;
  final double? confidence;
}

class CutProposal {
  CutProposal({
    required this.id,
    required this.start,
    required this.end,
    required this.reason,
    required this.cutType,
    required this.confidence,
    this.accepted,
  });

  factory CutProposal.fromJson(Map<String, dynamic> j) => CutProposal(
    id: j['id'] as String,
    start: _dbl(j['start_seconds'])!,
    end: _dbl(j['end_seconds'])!,
    reason: j['reason'] as String,
    cutType: j['cut_type'] as String,
    confidence: _dbl(j['confidence'])!,
    accepted: j['accepted'] as bool?,
  );

  final String id;
  final double start;
  final double end;
  final String reason;
  final String cutType;
  final double confidence;

  /// null = not reviewed yet. Nothing is cut unless the user accepts it.
  final bool? accepted;
}

class EditorialCaption {
  EditorialCaption({
    required this.id,
    required this.start,
    required this.end,
    required this.text,
    required this.segmentIds,
    required this.lowConfidence,
  });

  factory EditorialCaption.fromJson(Map<String, dynamic> j) => EditorialCaption(
    id: j['id'] as String,
    start: _dbl(j['start_seconds'])!,
    end: _dbl(j['end_seconds'])!,
    text: (j['edited_text'] as String?) ?? j['text'] as String,
    segmentIds: _ids(j['transcript_segment_ids']),
    lowConfidence: j['low_confidence'] as bool,
  );

  final String id;
  final double start;
  final double end;
  final String text;
  final List<String> segmentIds;
  final bool lowConfidence;
}

class AnalysisResult {
  AnalysisResult({required this.segments, required this.cuts, required this.captions, this.language});

  factory AnalysisResult.fromJson(Map<String, dynamic> j) => AnalysisResult(
    segments: [for (final s in j['transcript_segments'] as List) TranscriptSegment.fromJson(s as Map<String, dynamic>)],
    cuts: [for (final c in j['cut_proposals'] as List) CutProposal.fromJson(c as Map<String, dynamic>)],
    captions: [for (final c in j['editorial_captions'] as List) EditorialCaption.fromJson(c as Map<String, dynamic>)],
    language: j['language_detected'] as String?,
  );

  final List<TranscriptSegment> segments;
  final List<CutProposal> cuts;
  final List<EditorialCaption> captions;
  final String? language;

  bool get isEmpty => segments.isEmpty;
}

class RenderJob {
  RenderJob({
    required this.id,
    required this.projectId,
    required this.preset,
    required this.status,
    required this.progress,
    required this.createdAt,
    this.stage,
    this.message,
    this.sizeBytes,
    this.durationSeconds,
  });

  factory RenderJob.fromJson(Map<String, dynamic> j) => RenderJob(
    id: j['id'] as String,
    projectId: j['project_id'] as String,
    preset: j['preset'] as String,
    status: j['status'] as String,
    progress: (j['progress'] as num?)?.toInt() ?? 0,
    createdAt: _date(j['created_at']),
    stage: j['stage'] as String?,
    message: j['message'] as String?,
    sizeBytes: j['output_size_bytes'] as int?,
    durationSeconds: _dbl(j['output_duration_seconds']),
  );

  final String id;
  final String projectId;
  final String preset;
  final String status;
  final int progress;
  final DateTime createdAt;
  final String? stage;
  final String? message;
  final int? sizeBytes;
  final double? durationSeconds;

  bool get isTerminal => const {'completed', 'failed', 'cancelled'}.contains(status);
  bool get succeeded => status == 'completed';
}

class SystemInfo {
  SystemInfo({
    required this.environment,
    required this.maxUploadBytes,
    required this.maxDurationSeconds,
    required this.acceptedContentTypes,
    required this.retentionDays,
    required this.transcriptionProvider,
    required this.languageModelProvider,
    required this.demoMode,
  });

  factory SystemInfo.fromJson(Map<String, dynamic> j) {
    final p = j['providers'] as Map<String, dynamic>;
    return SystemInfo(
      environment: j['environment'] as String,
      maxUploadBytes: j['max_upload_bytes'] as int,
      maxDurationSeconds: j['max_video_duration_seconds'] as int,
      acceptedContentTypes: _ids(j['accepted_content_types']),
      retentionDays: j['media_retention_days'] as int,
      transcriptionProvider: p['transcription'] as String,
      languageModelProvider: p['language_model'] as String,
      demoMode: p['demo_mode'] as bool,
    );
  }

  final String environment;
  final int maxUploadBytes;
  final int maxDurationSeconds;
  final List<String> acceptedContentTypes;
  final int retentionDays;
  final String transcriptionProvider;
  final String languageModelProvider;
  final bool demoMode;
}
