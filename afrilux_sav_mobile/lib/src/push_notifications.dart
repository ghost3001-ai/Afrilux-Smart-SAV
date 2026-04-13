import 'dart:async';

import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import 'api_client.dart';

class PushNotificationService {
  PushNotificationService({required GlobalKey<NavigatorState> navigatorKey}) : _navigatorKey = navigatorKey;

  final GlobalKey<NavigatorState> _navigatorKey;
  StreamSubscription<String>? _tokenRefreshSubscription;
  StreamSubscription<RemoteMessage>? _messageSubscription;
  String? _lastToken;

  Future<void> registerCurrentDevice(SavApiClient api) async {
    if (await _ensureFirebaseApp() == null) {
      return;
    }

    try {
      final messaging = FirebaseMessaging.instance;
      final permission = await messaging.requestPermission(alert: true, badge: true, sound: true, provisional: true);
      if (permission.authorizationStatus == AuthorizationStatus.denied) {
        return;
      }

      await messaging.setAutoInitEnabled(true);
      await messaging.setForegroundNotificationPresentationOptions(alert: true, badge: true, sound: true);

      final token = await messaging.getToken();
      if (token == null || token.isEmpty) {
        return;
      }

      _lastToken = token;
      await _registerToken(api, token);
      await _tokenRefreshSubscription?.cancel();
      _tokenRefreshSubscription = FirebaseMessaging.instance.onTokenRefresh.listen((refreshedToken) async {
        _lastToken = refreshedToken;
        try {
          await _registerToken(api, refreshedToken);
        } catch (_) {}
      });

      _messageSubscription ??= FirebaseMessaging.onMessage.listen(_showForegroundNotification);
    } catch (_) {}
  }

  Future<void> unregisterCurrentDevice(SavApiClient api) async {
    try {
      final token = _lastToken ?? await FirebaseMessaging.instance.getToken();
      if (token == null || token.isEmpty) {
        return;
      }
      await api.post("device-registrations/unregister/", {"token": token});
    } catch (_) {}
  }

  Future<void> dispose() async {
    await _tokenRefreshSubscription?.cancel();
    await _messageSubscription?.cancel();
  }

  Future<void> _registerToken(SavApiClient api, String token) async {
    await api.post("device-registrations/register/", {
      "token": token,
      "platform": _platformLabel(),
      "device_id": _platformLabel(),
      "app_version": "1.0.0",
    });
  }

  void _showForegroundNotification(RemoteMessage message) {
    final context = _navigatorKey.currentContext;
    if (context == null) {
      return;
    }

    final title = message.notification?.title ?? message.data["subject"] ?? message.data["event_type"] ?? "Nouvelle notification";
    final body = message.notification?.body ?? message.data["message"] ?? "Mise a jour disponible.";
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text("$title\n$body")),
    );
  }

  Future<FirebaseApp?> _ensureFirebaseApp() async {
    if (kIsWeb) {
      return null;
    }

    try {
      if (Firebase.apps.isNotEmpty) {
        return Firebase.app();
      }

      final options = _firebaseOptionsForCurrentPlatform();
      if (options != null) {
        return Firebase.initializeApp(options: options);
      }
      return Firebase.initializeApp();
    } catch (_) {
      return null;
    }
  }

  String _platformLabel() {
    if (kIsWeb) {
      return "web";
    }
    switch (defaultTargetPlatform) {
      case TargetPlatform.android:
        return "android";
      case TargetPlatform.iOS:
        return "ios";
      case TargetPlatform.macOS:
      case TargetPlatform.windows:
      case TargetPlatform.linux:
        return "desktop";
      case TargetPlatform.fuchsia:
        return "android";
    }
  }

  FirebaseOptions? _firebaseOptionsForCurrentPlatform() {
    const apiKey = String.fromEnvironment("FIREBASE_API_KEY", defaultValue: "");
    const projectId = String.fromEnvironment("FIREBASE_PROJECT_ID", defaultValue: "");
    const messagingSenderId = String.fromEnvironment("FIREBASE_MESSAGING_SENDER_ID", defaultValue: "");
    const storageBucket = String.fromEnvironment("FIREBASE_STORAGE_BUCKET", defaultValue: "");
    const androidAppId = String.fromEnvironment("FIREBASE_ANDROID_APP_ID", defaultValue: "");
    const iosAppId = String.fromEnvironment("FIREBASE_IOS_APP_ID", defaultValue: "");
    const iosBundleId = String.fromEnvironment("FIREBASE_IOS_BUNDLE_ID", defaultValue: "");

    if (apiKey.isEmpty || projectId.isEmpty || messagingSenderId.isEmpty) {
      return null;
    }

    if (defaultTargetPlatform == TargetPlatform.android) {
      if (androidAppId.isEmpty) {
        return null;
      }
      return FirebaseOptions(
        apiKey: apiKey,
        appId: androidAppId,
        messagingSenderId: messagingSenderId,
        projectId: projectId,
        storageBucket: storageBucket.isEmpty ? null : storageBucket,
      );
    }

    if (defaultTargetPlatform == TargetPlatform.iOS) {
      if (iosAppId.isEmpty) {
        return null;
      }
      return FirebaseOptions(
        apiKey: apiKey,
        appId: iosAppId,
        messagingSenderId: messagingSenderId,
        projectId: projectId,
        storageBucket: storageBucket.isEmpty ? null : storageBucket,
        iosBundleId: iosBundleId.isEmpty ? null : iosBundleId,
      );
    }

    return null;
  }
}
