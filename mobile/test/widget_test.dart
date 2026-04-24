import 'package:flutter_test/flutter_test.dart';

import 'package:aparcaceres/core/app.dart';
import 'package:aparcaceres/shared/constants/app_strings.dart';

void main() {
  testWidgets('Welcome screen shows branding and CTA', (tester) async {
    await tester.pumpWidget(const AparCaceresApp());

    expect(find.text(AppStrings.welcomeCta), findsOneWidget);
  });
}
