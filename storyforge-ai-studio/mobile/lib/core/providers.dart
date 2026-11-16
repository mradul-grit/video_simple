import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import 'api_client.dart';
import 'config.dart';
import 'models.dart';

/// Stores the session token in the platform keystore (Android Keystore / iOS Keychain).
abstract interface class TokenStore {
  Future<String?> read();
  Future<void> write(String token);
  Future<void> clear();
}

class SecureTokenStore implements TokenStore {
  static const _key = 'sf_session_token';
  final _storage = const FlutterSecureStorage();

  @override
  Future<String?> read() => _storage.read(key: _key);
  @override
  Future<void> write(String token) => _storage.write(key: _key, value: token);
  @override
  Future<void> clear() => _storage.delete(key: _key);
}

final apiBaseUrlProvider = Provider<String>((ref) => AppConfig.apiBaseUrl);
final apiProvider = Provider<StoryForgeApi>((ref) => DioStoryForgeApi(baseUrl: ref.watch(apiBaseUrlProvider)));

/// Off in widget tests, where the native video plugin is not available.
final videoPreviewEnabledProvider = Provider<bool>((ref) => true);
final tokenStoreProvider = Provider<TokenStore>((ref) => SecureTokenStore());

/// Current session token; null when signed out.
class SessionController extends AsyncNotifier<String?> {
  @override
  Future<String?> build() async {
    final token = await ref.read(tokenStoreProvider).read();
    ref.read(apiProvider).setToken(token);
    return token;
  }

  Future<void> signInDev(String email) async {
    final api = ref.read(apiProvider);
    final token = await api.devLogin(email);
    await ref.read(tokenStoreProvider).write(token);
    api.setToken(token);
    state = AsyncData(token);
  }

  Future<void> signOut() async {
    await ref.read(tokenStoreProvider).clear();
    ref.read(apiProvider).setToken(null);
    state = const AsyncData(null);
  }
}

final sessionProvider = AsyncNotifierProvider<SessionController, String?>(SessionController.new);

final systemInfoProvider = FutureProvider<SystemInfo>((ref) => ref.watch(apiProvider).systemInfo());

final projectsProvider = FutureProvider.autoDispose<List<Project>>((ref) async {
  await ref.watch(sessionProvider.future);
  return ref.watch(apiProvider).listProjects();
});

final projectProvider = FutureProvider.autoDispose.family<Project, String>((ref, id) async {
  await ref.watch(sessionProvider.future);
  return ref.watch(apiProvider).getProject(id);
});

final mediaProvider = FutureProvider.autoDispose.family<List<MediaAsset>, String>((ref, id) async {
  await ref.watch(sessionProvider.future);
  return ref.watch(apiProvider).listMedia(id);
});

final analysisProvider = FutureProvider.autoDispose.family<AnalysisResult, String>((ref, id) async {
  await ref.watch(sessionProvider.future);
  return ref.watch(apiProvider).getAnalysis(id);
});

final exportsProvider = FutureProvider.autoDispose.family<List<RenderJob>, String>((ref, id) async {
  await ref.watch(sessionProvider.future);
  return ref.watch(apiProvider).listExports(id);
});

/// Exports across all of the user's projects, newest first, with the project title.
final allExportsProvider = FutureProvider.autoDispose<List<(Project, RenderJob)>>((ref) async {
  final projects = await ref.watch(projectsProvider.future);
  final api = ref.watch(apiProvider);
  final lists = await Future.wait(projects.map((p) async => [for (final r in await api.listExports(p.id)) (p, r)]));
  final all = lists.expand((x) => x).toList()..sort((a, b) => b.$2.createdAt.compareTo(a.$2.createdAt));
  return all;
});
