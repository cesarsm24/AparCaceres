import 'package:flutter_test/flutter_test.dart';

import 'package:aparcaceres/core/app.dart';

void main() {
  testWidgets('AparCaceresApp builds without errors', (tester) async {
    await tester.pumpWidget(const AparCaceresApp());
    expect(find.byType(AparCaceresApp), findsOneWidget);
  });
}
