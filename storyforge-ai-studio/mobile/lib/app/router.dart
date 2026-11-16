import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../core/providers.dart';
import '../features/auth/sign_in_screen.dart';
import '../features/editor/editor_screen.dart';
import '../features/exports/exports_screen.dart';
import '../features/projects/home_screen.dart';
import '../features/projects/new_project_screen.dart';
import '../features/projects/project_screen.dart';
import '../features/settings/settings_screen.dart';
import 'shell.dart';

/// Bridges Riverpod session changes to GoRouter's redirect.
class _SessionListenable extends ChangeNotifier {
  _SessionListenable(Ref ref) {
    ref.listen(sessionProvider, (_, __) => notifyListeners());
  }
}

final routerProvider = Provider<GoRouter>((ref) {
  final refresh = _SessionListenable(ref);
  ref.onDispose(refresh.dispose);

  return GoRouter(
    initialLocation: '/',
    refreshListenable: refresh,
    redirect: (context, state) {
      final session = ref.read(sessionProvider);
      if (session.isLoading) return state.matchedLocation == '/loading' ? null : '/loading';
      final signedIn = session.value != null;
      final atSignIn = state.matchedLocation == '/sign-in';
      if (!signedIn) return atSignIn ? null : '/sign-in';
      if (atSignIn || state.matchedLocation == '/loading') return '/';
      return null;
    },
    routes: [
      GoRoute(path: '/loading', builder: (_, __) => const _Splash()),
      GoRoute(path: '/sign-in', builder: (_, __) => const SignInScreen()),
      StatefulShellRoute.indexedStack(
        builder: (context, state, shell) => AppShell(shell: shell),
        branches: [
          StatefulShellBranch(routes: [GoRoute(path: '/', builder: (_, __) => const HomeScreen())]),
          StatefulShellBranch(routes: [GoRoute(path: '/exports', builder: (_, __) => const ExportsScreen())]),
          StatefulShellBranch(routes: [GoRoute(path: '/settings', builder: (_, __) => const SettingsScreen())]),
        ],
      ),
      GoRoute(path: '/new', builder: (_, __) => const NewProjectScreen()),
      GoRoute(
        path: '/projects/:id',
        builder: (_, s) => ProjectScreen(projectId: s.pathParameters['id']!),
        routes: [GoRoute(path: 'editor', builder: (_, s) => EditorScreen(projectId: s.pathParameters['id']!))],
      ),
    ],
  );
});

class _Splash extends StatelessWidget {
  const _Splash();

  @override
  Widget build(BuildContext context) =>
      const Scaffold(body: Center(child: CircularProgressIndicator(strokeWidth: 2.5)));
}
