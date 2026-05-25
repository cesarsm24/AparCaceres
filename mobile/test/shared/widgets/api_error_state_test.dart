import 'package:aparcaceres/core/network/api_exceptions.dart';
import 'package:aparcaceres/shared/widgets/api_error_state.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Future<void> _pump(WidgetTester tester, Widget child) {
  return tester.pumpWidget(MaterialApp(home: Scaffold(body: child)));
}

void main() {
  testWidgets('shows hourglass copy for ApiTimeoutException', (tester) async {
    await _pump(
      tester,
      ApiErrorState(
        error: const ApiTimeoutException('slow'),
        onRetry: () {},
      ),
    );

    expect(find.text('La conexión está tardando demasiado'), findsOneWidget);
    expect(find.byIcon(Icons.hourglass_empty_rounded), findsOneWidget);
  });

  testWidgets('shows cloud-off copy for ApiUnavailableException', (
    tester,
  ) async {
    await _pump(
      tester,
      ApiErrorState(
        error: const ApiUnavailableException('502 bad gateway'),
        onRetry: () {},
      ),
    );

    expect(find.text('Servicio no disponible'), findsOneWidget);
    expect(find.byIcon(Icons.cloud_off_rounded), findsOneWidget);
  });

  testWidgets('falls back to ApiException detail message', (tester) async {
    await _pump(
      tester,
      ApiErrorState(
        error: const ApiException('parking not found', statusCode: 404),
        onRetry: () {},
      ),
    );

    expect(
      find.text('No hemos podido cargar los aparcamientos'),
      findsOneWidget,
    );
    expect(find.text('parking not found'), findsOneWidget);
  });

  testWidgets('shows generic copy for unexpected error types', (tester) async {
    await _pump(
      tester,
      ApiErrorState(
        error: StateError('unrelated'),
        onRetry: () {},
      ),
    );

    expect(find.text('Algo ha fallado'), findsOneWidget);
  });

  testWidgets('Reintentar button invokes the callback', (tester) async {
    var taps = 0;
    await _pump(
      tester,
      ApiErrorState(
        error: const ApiUnavailableException('boom'),
        onRetry: () => taps++,
      ),
    );

    await tester.tap(find.text('Reintentar'));
    await tester.pump();

    expect(taps, 1);
  });
}
