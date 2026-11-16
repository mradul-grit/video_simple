import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../app/theme.dart';
import '../../core/providers.dart';
import '../../shared/widgets.dart';

/// Development sign-in. Real accounts (Supabase Auth or Cognito) arrive in Spec 06;
/// the server refuses this endpoint outside APP_ENV=development.
class SignInScreen extends ConsumerStatefulWidget {
  const SignInScreen({super.key});

  @override
  ConsumerState<SignInScreen> createState() => _SignInScreenState();
}

class _SignInScreenState extends ConsumerState<SignInScreen> {
  final _form = GlobalKey<FormState>();
  final _email = TextEditingController();
  bool _busy = false;
  String? _error;

  @override
  void dispose() {
    _email.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_form.currentState!.validate()) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await ref.read(sessionProvider.notifier).signInDev(_email.text.trim());
    } catch (e) {
      if (mounted) setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final info = ref.watch(systemInfoProvider);
    final devAvailable = info.value?.environment == 'development';

    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(SfSpace.lg),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: Form(
                key: _form,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Container(
                      width: 56,
                      height: 56,
                      alignment: Alignment.center,
                      decoration: BoxDecoration(gradient: sfAccentGradient, borderRadius: BorderRadius.circular(16)),
                      child: const Icon(Icons.auto_awesome_motion_rounded, color: SfColors.onAccent, size: 30),
                    ),
                    const SizedBox(height: SfSpace.lg),
                    Text('Tell the story.\nWe\u2019ll help you edit it.', style: t.displaySmall),
                    const SizedBox(height: SfSpace.sm),
                    Text(
                      'Record yourself explaining something. StoryForge proposes cuts, captions and visuals; '
                      'you approve every change.',
                      style: t.bodyMedium,
                    ),
                    const SizedBox(height: SfSpace.xl),
                    ...switch (info) {
                      AsyncLoading() => [const LoadingView(label: 'Contacting server')],
                      AsyncError(:final error) => [
                        ErrorView(error: error, onRetry: () => ref.invalidate(systemInfoProvider)),
                      ],
                      _ when !devAvailable => [
                        const MessageView(
                          icon: Icons.lock_outline_rounded,
                          title: 'Sign-in not available yet',
                          message:
                              'This server is not in development mode, and account sign-in '
                              'is not built yet. It is planned for a later release.',
                        ),
                      ],
                      _ => [
                        Text('Development sign-in', style: t.titleMedium),
                        const SizedBox(height: SfSpace.xs),
                        Text(
                          'For local testing only. Any email creates a private test account on your own server. '
                          'There is no password.',
                          style: t.bodyMedium,
                        ),
                        const SizedBox(height: SfSpace.md),
                        TextFormField(
                          controller: _email,
                          keyboardType: TextInputType.emailAddress,
                          autofillHints: const [AutofillHints.email],
                          textInputAction: TextInputAction.go,
                          onFieldSubmitted: (_) => _submit(),
                          decoration: const InputDecoration(labelText: 'Email'),
                          validator: (v) {
                            final s = v?.trim() ?? '';
                            return RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$').hasMatch(s) ? null : 'Enter a valid email';
                          },
                        ),
                        if (_error != null) ...[
                          const SizedBox(height: SfSpace.sm),
                          Text(_error!, style: t.bodyMedium?.copyWith(color: SfColors.danger)),
                        ],
                        const SizedBox(height: SfSpace.lg),
                        PrimaryButton(label: 'Continue', onPressed: _submit, busy: _busy),
                      ],
                    },
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
