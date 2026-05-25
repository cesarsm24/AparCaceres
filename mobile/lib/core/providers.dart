import 'auth/auth_session.dart';
import 'network/api_client.dart';

/// Cliente HTTP compartido por la aplicación.
///
/// Reutiliza el cliente subyacente y obtiene el token de sesión de forma
/// diferida para evitar dependencias de orden durante la inicialización global.
final ApiClient sharedApiClient = ApiClient(
  tokenProvider: () => authSession.tokenForRequest(),
  authInvalidator: () => authSession.invalidateToken(),
);

/// Sesión de autenticación compartida por la aplicación.
final AuthSession authSession = AuthSession(apiClient: sharedApiClient);
