/// Build-time configuration. Holds no secrets: provider keys live only on the server.
///
/// Override per build:
///   flutter run --dart-define=SF_API_BASE_URL=http://192.168.1.20:8000
/// Default targets the Android emulator's alias for the host machine.
abstract final class AppConfig {
  static const apiBaseUrl = String.fromEnvironment('SF_API_BASE_URL', defaultValue: 'http://10.0.2.2:8000');

  static const apiPrefix = '/api/v1';

  /// Job polling cadence and ceiling. Long renders keep polling while the screen is open.
  static const pollInterval = Duration(seconds: 1);
  static const pollTimeout = Duration(minutes: 15);
}
