import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'router.dart';
import 'theme.dart';

class StoryForgeApp extends ConsumerWidget {
  const StoryForgeApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) => MaterialApp.router(
    title: 'StoryForge',
    debugShowCheckedModeBanner: false,
    theme: buildSfTheme(),
    darkTheme: buildSfTheme(),
    themeMode: ThemeMode.dark,
    routerConfig: ref.watch(routerProvider),
  );
}
