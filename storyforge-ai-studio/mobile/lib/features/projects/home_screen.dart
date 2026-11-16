import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/theme.dart';
import '../../core/models.dart';
import '../../core/providers.dart';
import '../../shared/widgets.dart';

class HomeScreen extends ConsumerWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final projects = ref.watch(projectsProvider);
    final t = Theme.of(context).textTheme;

    return Scaffold(
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: () => ref.refresh(projectsProvider.future),
          child: CustomScrollView(
            slivers: [
              SliverPadding(
                padding: const EdgeInsets.fromLTRB(SfSpace.lg, SfSpace.lg, SfSpace.lg, 0),
                sliver: SliverList.list(
                  children: [
                    Text('Your videos', style: t.headlineSmall),
                    const SizedBox(height: SfSpace.xs),
                    Text('Record or import a talking-head clip to start a new edit.', style: t.bodyMedium),
                    const SizedBox(height: SfSpace.lg),
                    PrimaryButton(label: 'New video', icon: Icons.add_rounded, onPressed: () => context.push('/new')),
                    const SectionHeader('Recent projects'),
                  ],
                ),
              ),
              ...switch (projects) {
                AsyncError(:final error) when !projects.isLoading => [
                  SliverFillRemaining(
                    hasScrollBody: false,
                    child: ErrorView(error: error, onRetry: () => ref.invalidate(projectsProvider)),
                  ),
                ],
                AsyncData(:final value) when value.isEmpty => [
                  const SliverFillRemaining(
                    hasScrollBody: false,
                    child: MessageView(
                      icon: Icons.video_camera_front_outlined,
                      title: 'No projects yet',
                      message: 'Tap \u201cNew video\u201d to import your first recording.',
                    ),
                  ),
                ],
                AsyncData(:final value) => [
                  SliverPadding(
                    padding: const EdgeInsets.fromLTRB(SfSpace.lg, 0, SfSpace.lg, SfSpace.xl),
                    sliver: SliverList.separated(
                      itemCount: value.length,
                      separatorBuilder: (_, __) => const SizedBox(height: SfSpace.sm),
                      itemBuilder: (_, i) => _ProjectTile(project: value[i]),
                    ),
                  ),
                ],
                _ => [const SliverFillRemaining(hasScrollBody: false, child: LoadingView(label: 'Loading projects'))],
              },
            ],
          ),
        ),
      ),
    );
  }
}

class _ProjectTile extends StatelessWidget {
  const _ProjectTile({required this.project});
  final Project project;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final d = project.updatedAt;
    return Card(
      child: InkWell(
        borderRadius: BorderRadius.circular(SfRadius.md),
        onTap: () => context.push('/projects/${project.id}'),
        child: Padding(
          padding: const EdgeInsets.all(SfSpace.md),
          child: Row(
            children: [
              Container(
                width: 44,
                height: 64,
                decoration: BoxDecoration(
                  color: SfColors.surfaceRaised,
                  borderRadius: BorderRadius.circular(SfRadius.sm),
                  border: Border.all(color: SfColors.outline),
                ),
                child: const Icon(Icons.play_arrow_rounded, color: SfColors.textSecondary),
              ),
              const SizedBox(width: SfSpace.md),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(project.title, style: t.titleMedium, maxLines: 1, overflow: TextOverflow.ellipsis),
                    const SizedBox(height: 2),
                    Text('Updated ${d.day}/${d.month}/${d.year} \u00b7 ${project.outputPreset}', style: t.bodyMedium),
                  ],
                ),
              ),
              const Icon(Icons.chevron_right_rounded, color: SfColors.textSecondary),
            ],
          ),
        ),
      ),
    );
  }
}
