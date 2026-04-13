import 'package:flutter_test/flutter_test.dart';

import 'package:afrilux_sav_mobile/src/app.dart';

void main() {
  testWidgets('login screen renders', (WidgetTester tester) async {
    await tester.pumpWidget(const AfriluxSavMobileApp());

    expect(find.text('Afrilux SAV Mobile'), findsOneWidget);
    expect(find.text('Connexion'), findsOneWidget);
    expect(find.text('Serveur'), findsOneWidget);
  });
}
