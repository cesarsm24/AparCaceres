import 'auth/auth_session.dart';
import 'network/api_client.dart';

/// `ApiClient` único para toda la app: comparte el `http.Client` (connection
/// pool) y el `tokenProvider` que apunta a `authSession`. Los tests inyectan
/// instancias propias en lugar de tocar este global.
///
/// Nota sobre el orden de inicialización: este `final` se evalúa la primera
/// vez que alguien lo lee. La closure `() => authSession.tokenForRequest()`
/// difiere la lectura de `authSession`, así que no importa que la
/// declaración de `authSession` venga después en el archivo.
final ApiClient sharedApiClient = ApiClient(
  tokenProvider: () => authSession.tokenForRequest(),
);

/// Sesión global con `POST /auth/session`. Usa el mismo `sharedApiClient`
/// porque `/auth/session` es el único endpoint sin auth y no recursa por la
/// closure de arriba (`requiresAuth` por defecto es `false`).
final AuthSession authSession = AuthSession(apiClient: sharedApiClient);
