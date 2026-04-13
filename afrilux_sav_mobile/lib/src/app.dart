import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import 'api_client.dart';
import 'push_notifications.dart';

void runAfriluxSavMobile() {
  runApp(const AfriluxSavMobileApp());
}

String _normalizeServerUrlValue(String serverUrl) {
  var value = serverUrl.trim();
  if (!value.startsWith("http://") && !value.startsWith("https://")) {
    value = "http://$value";
  }
  if (!value.endsWith("/")) {
    value = "$value/";
  }
  return value;
}

Color _colorFromHex(String value, Color fallback) {
  final normalized = value.trim().replaceFirst("#", "");
  if (normalized.length != 6) {
    return fallback;
  }
  final parsed = int.tryParse(normalized, radix: 16);
  if (parsed == null) {
    return fallback;
  }
  return Color(0xFF000000 | parsed);
}

ThemeData _themeForSession(SavSession? session) {
  final primary = _colorFromHex(session?.organizationPrimaryColor ?? "", const Color(0xFFD5671D));
  final accent = _colorFromHex(session?.organizationAccentColor ?? "", const Color(0xFF1C7A6A));
  return ThemeData(
    useMaterial3: true,
    colorScheme: ColorScheme.fromSeed(
      seedColor: primary,
      brightness: Brightness.light,
      primary: primary,
      secondary: accent,
      surface: const Color(0xFFF8F2E7),
    ),
    scaffoldBackgroundColor: const Color(0xFFF2EBDC),
    appBarTheme: const AppBarTheme(centerTitle: false, backgroundColor: Colors.transparent),
    cardTheme: CardThemeData(
      color: Colors.white.withValues(alpha: 0.88),
      elevation: 0,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(28)),
    ),
  );
}

class SavSession {
  const SavSession({
    required this.api,
    required this.baseServerUrl,
    required this.currentUser,
  });

  final SavApiClient api;
  final String baseServerUrl;
  final Map<String, dynamic> currentUser;

  String get role => (currentUser["role"] ?? "client").toString();
  bool get isInternal => const {
        "agent",
        "manager",
        "support",
        "technician",
        "head_sav",
        "admin",
      }.contains(role);
  bool get isManager => const {
        "manager",
        "head_sav",
        "admin",
      }.contains(role);
  int get userId => (currentUser["id"] ?? 0) as int;
  String get organizationName => (currentUser["organization_name"] ?? "").toString();
  String get organizationPrimaryColor => (currentUser["organization_primary_color"] ?? "").toString();
  String get organizationAccentColor => (currentUser["organization_accent_color"] ?? "").toString();
  String get organizationTagline => (currentUser["organization_portal_tagline"] ?? "").toString();
  String get organizationSupportEmail => (currentUser["organization_support_email"] ?? "").toString();
  String get organizationSupportPhone => (currentUser["organization_support_phone"] ?? "").toString();
  bool get isVerified => currentUser["is_verified"] == true;
  String get accountBalance => (currentUser["account_balance"] ?? "0.00").toString();
  String get displayName {
    final firstName = (currentUser["first_name"] ?? "").toString();
    final lastName = (currentUser["last_name"] ?? "").toString();
    final merged = "$firstName $lastName".trim();
    if (merged.isNotEmpty) {
      return merged;
    }
    return (currentUser["username"] ?? "Utilisateur").toString();
  }
}

class SessionController extends ChangeNotifier {
  SessionController({required GlobalKey<NavigatorState> navigatorKey})
      : _pushNotifications = PushNotificationService(navigatorKey: navigatorKey);

  SavSession? session;
  bool loading = false;
  String? error;
  final PushNotificationService _pushNotifications;

  Future<void> login({
    required String serverUrl,
    required String username,
    required String password,
  }) async {
    loading = true;
    error = null;
    notifyListeners();

    final normalizedServerUrl = _normalizeServerUrlValue(serverUrl);
    final api = SavApiClient(
      baseUrl: "${normalizedServerUrl}api/",
    );

    try {
      await api.authenticate(identifier: username, password: password);
      final currentUser = await api.getMap("users/me/");
      await api.getMap("dashboard/");
      session = SavSession(api: api, baseServerUrl: normalizedServerUrl, currentUser: currentUser);
      await _pushNotifications.registerCurrentDevice(api);
    } catch (exc) {
      error = exc.toString();
      session = null;
    } finally {
      loading = false;
      notifyListeners();
    }
  }

  Future<void> logout() async {
    final activeSession = session;
    session = null;
    error = null;
    notifyListeners();
    if (activeSession != null) {
      try {
        await _pushNotifications.unregisterCurrentDevice(activeSession.api);
      } catch (_) {}
      activeSession.api.clearTokens();
    }
  }

  @override
  void dispose() {
    unawaited(_pushNotifications.dispose());
    super.dispose();
  }

}

class AfriluxSavMobileApp extends StatefulWidget {
  const AfriluxSavMobileApp({super.key});

  @override
  State<AfriluxSavMobileApp> createState() => _AfriluxSavMobileAppState();
}

class _AfriluxSavMobileAppState extends State<AfriluxSavMobileApp> {
  final GlobalKey<NavigatorState> _navigatorKey = GlobalKey<NavigatorState>();
  late final SessionController _sessionController;

  @override
  void initState() {
    super.initState();
    _sessionController = SessionController(navigatorKey: _navigatorKey);
  }

  @override
  void dispose() {
    _sessionController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: "Afrilux SAV Mobile",
      debugShowCheckedModeBanner: false,
      navigatorKey: _navigatorKey,
      theme: _themeForSession(_sessionController.session),
      home: AnimatedBuilder(
        animation: _sessionController,
        builder: (context, _) {
          if (_sessionController.session == null) {
            return LoginPage(controller: _sessionController);
          }
          return HomeShell(controller: _sessionController);
        },
      ),
    );
  }
}

class LoginPage extends StatefulWidget {
  const LoginPage({super.key, required this.controller});

  final SessionController controller;

  @override
  State<LoginPage> createState() => _LoginPageState();
}

class _LoginPageState extends State<LoginPage> {
  late final TextEditingController _serverController;
  final TextEditingController _usernameController = TextEditingController();
  final TextEditingController _passwordController = TextEditingController();

  @override
  void initState() {
    super.initState();
    const definedHost = String.fromEnvironment("SAV_SERVER_URL", defaultValue: "");
    final fallbackHost = !kIsWeb && defaultTargetPlatform == TargetPlatform.android
        ? "http://10.0.2.2:8000"
        : "http://127.0.0.1:8000";
    _serverController = TextEditingController(text: definedHost.isNotEmpty ? definedHost : fallbackHost);
  }

  @override
  void dispose() {
    _serverController.dispose();
    _usernameController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    await widget.controller.login(
      serverUrl: _serverController.text,
      username: _usernameController.text,
      password: _passwordController.text,
    );
  }

  Future<void> _openRegistration() async {
    final registeredEmail = await Navigator.of(context).push<String>(
      MaterialPageRoute<String>(
        builder: (_) => ClientRegistrationPage(initialServerUrl: _serverController.text),
      ),
    );
    if (registeredEmail != null && registeredEmail.isNotEmpty) {
      setState(() {
        _usernameController.text = registeredEmail;
        _passwordController.clear();
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: DecoratedBox(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            colors: [Color(0xFFF8F2E7), Color(0xFFEEDBC2)],
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
          ),
        ),
        child: SafeArea(
          child: LayoutBuilder(
            builder: (context, constraints) => SingleChildScrollView(
              padding: const EdgeInsets.all(24),
              child: ConstrainedBox(
                constraints: BoxConstraints(minHeight: constraints.maxHeight),
                child: Center(
                  child: ConstrainedBox(
                    constraints: const BoxConstraints(maxWidth: 560),
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Card(
                          child: Padding(
                            padding: const EdgeInsets.all(24),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  "Afrilux SAV Mobile",
                                  style: Theme.of(context).textTheme.headlineMedium?.copyWith(fontWeight: FontWeight.w700),
                                ),
                                const SizedBox(height: 8),
                                Text(
                                  "Tickets, predictive maintenance, notifications and AI actions in one mobile cockpit.",
                                  style: Theme.of(context).textTheme.bodyLarge?.copyWith(color: Colors.black54, height: 1.5),
                                ),
                                const SizedBox(height: 20),
                                _LabeledField(label: "Serveur", child: TextField(controller: _serverController)),
                                const SizedBox(height: 14),
                                _LabeledField(
                                  label: "Email ou identifiant",
                                  child: TextField(
                                    controller: _usernameController,
                                    keyboardType: TextInputType.emailAddress,
                                  ),
                                ),
                                const SizedBox(height: 14),
                                _LabeledField(
                                  label: "Mot de passe",
                                  child: TextField(
                                    controller: _passwordController,
                                    obscureText: true,
                                    onSubmitted: (_) => _submit(),
                                  ),
                                ),
                                if (widget.controller.error != null) ...[
                                  const SizedBox(height: 14),
                                  Text(widget.controller.error!, style: const TextStyle(color: Color(0xFFA33728))),
                                ],
                                const SizedBox(height: 20),
                                FilledButton(
                                  onPressed: widget.controller.loading ? null : _submit,
                                  child: widget.controller.loading
                                      ? const SizedBox(
                                          height: 18,
                                          width: 18,
                                          child: CircularProgressIndicator(strokeWidth: 2),
                                        )
                                      : const Text("Connexion"),
                                ),
                                const SizedBox(height: 12),
                                OutlinedButton(
                                  onPressed: widget.controller.loading ? null : _openRegistration,
                                  child: const Text("Creer un compte client"),
                                ),
                              ],
                            ),
                          ),
                        ),
                        const SizedBox(height: 16),
                        Text(
                          "Astuce: sur emulateur Android, utilisez http://10.0.2.2:8000",
                          textAlign: TextAlign.center,
                          style: Theme.of(context).textTheme.bodySmall?.copyWith(color: Colors.black54),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class ClientRegistrationPage extends StatefulWidget {
  const ClientRegistrationPage({super.key, required this.initialServerUrl});

  final String initialServerUrl;

  @override
  State<ClientRegistrationPage> createState() => _ClientRegistrationPageState();
}

class _ClientRegistrationPageState extends State<ClientRegistrationPage> {
  late final TextEditingController _serverController;
  final TextEditingController _firstNameController = TextEditingController();
  final TextEditingController _lastNameController = TextEditingController();
  final TextEditingController _emailController = TextEditingController();
  final TextEditingController _phoneController = TextEditingController();
  final TextEditingController _companyController = TextEditingController();
  final TextEditingController _passwordController = TextEditingController();
  final TextEditingController _confirmPasswordController = TextEditingController();

  List<Map<String, dynamic>> _organizations = [];
  int? _selectedOrganizationId;
  bool _loadingOrganizations = false;
  bool _submitting = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _serverController = TextEditingController(text: widget.initialServerUrl);
    unawaited(_loadOrganizations());
  }

  @override
  void dispose() {
    _serverController.dispose();
    _firstNameController.dispose();
    _lastNameController.dispose();
    _emailController.dispose();
    _phoneController.dispose();
    _companyController.dispose();
    _passwordController.dispose();
    _confirmPasswordController.dispose();
    super.dispose();
  }

  SavPublicApiClient _publicApi() {
    final normalizedServerUrl = _normalizeServerUrlValue(_serverController.text);
    return SavPublicApiClient(baseUrl: "${normalizedServerUrl}api/");
  }

  Future<void> _loadOrganizations() async {
    setState(() {
      _loadingOrganizations = true;
      _error = null;
    });
    try {
      final organizations = await _publicApi().getList("public/organizations/");
      if (!mounted) {
        return;
      }
      setState(() {
        _organizations = organizations;
        _selectedOrganizationId = organizations.isNotEmpty ? organizations.first["id"] as int : null;
      });
    } catch (exc) {
      if (!mounted) {
        return;
      }
      setState(() => _error = exc.toString());
    } finally {
      if (mounted) {
        setState(() => _loadingOrganizations = false);
      }
    }
  }

  Future<void> _submit() async {
    if (_selectedOrganizationId == null) {
      setState(() => _error = "Selectionnez une organisation.");
      return;
    }
    setState(() {
      _submitting = true;
      _error = null;
    });
    try {
      await _publicApi().post("public/register/", {
        "organization": _selectedOrganizationId,
        "first_name": _firstNameController.text.trim(),
        "last_name": _lastNameController.text.trim(),
        "email": _emailController.text.trim(),
        "phone": _phoneController.text.trim(),
        "company_name": _companyController.text.trim(),
        "password": _passwordController.text,
        "password_confirm": _confirmPasswordController.text,
      });
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text("Compte cree. Connectez-vous avec votre email.")),
      );
      Navigator.of(context).pop(_emailController.text.trim());
    } catch (exc) {
      if (!mounted) {
        return;
      }
      setState(() => _error = exc.toString());
    } finally {
      if (mounted) {
        setState(() => _submitting = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text("Creer un compte client")),
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          Card(
            child: Padding(
              padding: const EdgeInsets.all(20),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    "Inscription",
                    style: Theme.of(context).textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w700),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    "Renseignez manuellement vos informations pour creer votre acces client SAV.",
                    style: Theme.of(context).textTheme.bodyLarge?.copyWith(color: Colors.black54),
                  ),
                  const SizedBox(height: 20),
                  _LabeledField(label: "Serveur", child: TextField(controller: _serverController)),
                  const SizedBox(height: 12),
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          "Organisation cliente",
                          style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700),
                        ),
                      ),
                      TextButton(
                        onPressed: _loadingOrganizations ? null : _loadOrganizations,
                        child: const Text("Actualiser"),
                      ),
                    ],
                  ),
                  if (_loadingOrganizations)
                    const Padding(
                      padding: EdgeInsets.symmetric(vertical: 12),
                      child: LinearProgressIndicator(),
                    )
                  else
                    DropdownButtonFormField<int>(
                      initialValue: _selectedOrganizationId,
                      decoration: const InputDecoration(labelText: "Organisation"),
                      items: _organizations
                          .map(
                            (organization) => DropdownMenuItem<int>(
                              value: organization["id"] as int,
                              child: Text((organization["display_name"] ?? organization["slug"] ?? "").toString()),
                            ),
                          )
                          .toList(),
                      onChanged: (value) => setState(() => _selectedOrganizationId = value),
                    ),
                  const SizedBox(height: 12),
                  _LabeledField(label: "Prenom", child: TextField(controller: _firstNameController)),
                  const SizedBox(height: 12),
                  _LabeledField(label: "Nom", child: TextField(controller: _lastNameController)),
                  const SizedBox(height: 12),
                  _LabeledField(
                    label: "Email",
                    child: TextField(
                      controller: _emailController,
                      keyboardType: TextInputType.emailAddress,
                    ),
                  ),
                  const SizedBox(height: 12),
                  _LabeledField(label: "Telephone", child: TextField(controller: _phoneController)),
                  const SizedBox(height: 12),
                  _LabeledField(label: "Entreprise", child: TextField(controller: _companyController)),
                  const SizedBox(height: 12),
                  _LabeledField(
                    label: "Mot de passe",
                    child: TextField(controller: _passwordController, obscureText: true),
                  ),
                  const SizedBox(height: 12),
                  _LabeledField(
                    label: "Confirmation",
                    child: TextField(
                      controller: _confirmPasswordController,
                      obscureText: true,
                      onSubmitted: (_) => _submit(),
                    ),
                  ),
                  if (_error != null) ...[
                    const SizedBox(height: 12),
                    Text(_error!, style: const TextStyle(color: Color(0xFFA33728))),
                  ],
                  const SizedBox(height: 18),
                  FilledButton(
                    onPressed: _submitting ? null : _submit,
                    child: _submitting
                        ? const SizedBox(
                            height: 18,
                            width: 18,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Text("Creer mon compte"),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class HomeShell extends StatefulWidget {
  const HomeShell({super.key, required this.controller});

  final SessionController controller;

  @override
  State<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends State<HomeShell> {
  int _index = 0;
  int _ticketRevision = 0;

  @override
  Widget build(BuildContext context) {
    final session = widget.controller.session!;
    final pages = session.isInternal
        ? [
            DashboardScreen(session: session),
            TicketsScreen(key: ValueKey("tickets-$_ticketRevision"), session: session),
            ProductsScreen(session: session),
            KnowledgeScreen(session: session),
            OffersScreen(session: session),
            NotificationsScreen(session: session),
          ]
        : [
            DashboardScreen(session: session),
            SupportScreen(key: ValueKey("support-$_ticketRevision"), session: session),
            ProductsScreen(session: session),
            KnowledgeScreen(session: session),
            OffersScreen(session: session),
            NotificationsScreen(session: session),
          ];
    final supportLabel = session.isInternal ? "Tickets" : "Support";
    final titles = ["Dashboard", supportLabel, "Produits", "Knowledge", "Offres", "Inbox"];

    return Scaffold(
      appBar: AppBar(
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(titles[_index]),
            if (session.organizationName.isNotEmpty)
              Text(
                session.organizationName,
                style: Theme.of(context).textTheme.labelMedium?.copyWith(color: Colors.black54),
              ),
          ],
        ),
        actions: [
          IconButton(
            tooltip: "Analytics",
            onPressed: () => showModalBottomSheet<void>(
              context: context,
              isScrollControlled: true,
              showDragHandle: true,
              builder: (context) => AnalyticsSheet(session: session),
            ),
            icon: const Icon(Icons.analytics_outlined),
          ),
          IconButton(
            tooltip: "Deconnexion",
            onPressed: () {
              unawaited(widget.controller.logout());
            },
            icon: const Icon(Icons.logout),
          ),
        ],
      ),
      body: SafeArea(child: pages[_index]),
      floatingActionButton: _index == 1
          ? FloatingActionButton.extended(
              onPressed: () async {
                final created = await Navigator.of(context).push<bool>(
                  MaterialPageRoute<bool>(
                    builder: (_) => TicketCreatePage(session: session),
                  ),
                );
                if (created == true) {
                  setState(() {
                    _index = 1;
                    _ticketRevision += 1;
                  });
                }
              },
              label: Text(session.isInternal ? "Nouveau ticket" : "Demander de l'aide"),
              icon: const Icon(Icons.add),
            )
          : null,
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        onDestinationSelected: (value) => setState(() => _index = value),
        destinations: [
          const NavigationDestination(icon: Icon(Icons.space_dashboard_outlined), label: "Dashboard"),
          NavigationDestination(icon: const Icon(Icons.support_agent_outlined), label: supportLabel),
          const NavigationDestination(icon: Icon(Icons.battery_charging_full_outlined), label: "Produits"),
          const NavigationDestination(icon: Icon(Icons.menu_book_outlined), label: "Knowledge"),
          const NavigationDestination(icon: Icon(Icons.local_offer_outlined), label: "Offres"),
          const NavigationDestination(icon: Icon(Icons.notifications_outlined), label: "Inbox"),
        ],
      ),
    );
  }
}

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key, required this.session});

  final SavSession session;

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  late Future<Map<String, dynamic>> _future;

  @override
  void initState() {
    super.initState();
    _future = widget.session.api.getMap("dashboard/");
  }

  Future<void> _refresh() async {
    setState(() {
      _future = widget.session.api.getMap("dashboard/");
    });
    await _future;
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<Map<String, dynamic>>(
      future: _future,
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done) {
          return const Center(child: CircularProgressIndicator());
        }
        if (snapshot.hasError) {
          return _ErrorView(message: snapshot.error.toString(), onRetry: _refresh);
        }

        final data = snapshot.data ?? <String, dynamic>{};
        final stats = [
          ("Tickets ouverts", "${data["tickets_open"] ?? 0}", Icons.confirmation_number_outlined),
          ("Critiques", "${data["tickets_critical_open"] ?? 0}", Icons.priority_high_rounded),
          ("Plaintes", "${data["complaints_total"] ?? 0}", Icons.report_problem_outlined),
          ("Fraude", "${data["fraud_suspected_open"] ?? 0}", Icons.gpp_maybe_outlined),
          ("Produits", "${data["products_total"] ?? 0}", Icons.battery_charging_full_outlined),
          ("Alertes", "${data["predictive_alerts_open"] ?? 0}", Icons.sensors_outlined),
          ("Notifications", "${data["notifications_unread"] ?? 0}", Icons.notifications_active_outlined),
          ("IA executee", "${data["ai_actions_executed"] ?? 0}", Icons.auto_awesome_outlined),
        ];
        final topAgents = (data["top_agents"] as List<dynamic>? ?? []).cast<Map<String, dynamic>>();

        return RefreshIndicator(
          onRefresh: _refresh,
          child: ListView(
            padding: const EdgeInsets.all(20),
            children: [
              _HeroPanel(
                title: widget.session.organizationName.isNotEmpty
                    ? widget.session.organizationName
                    : "Tableau de bord SAV Afrilux",
                subtitle: widget.session.organizationTagline.isNotEmpty
                    ? "${widget.session.organizationTagline} · Connecte en tant que ${widget.session.displayName}."
                    : widget.session.isInternal
                        ? "Bienvenue ${widget.session.displayName}. Supervisez les tickets, les SLA, les interventions et le reporting SAV."
                        : "Bienvenue ${widget.session.displayName}. Suivez vos demandes SAV, vos equipements et les notifications de traitement.",
              ),
              const SizedBox(height: 20),
              Wrap(
                spacing: 14,
                runSpacing: 14,
                children: stats
                    .map(
                      (entry) => SizedBox(
                        width: 170,
                        child: _MetricCard(
                          label: entry.$1,
                          value: entry.$2,
                          icon: entry.$3,
                        ),
                      ),
                    )
                    .toList(),
              ),
              const SizedBox(height: 20),
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(20),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text("Indicateurs SAV", style: Theme.of(context).textTheme.titleLarge),
                      const SizedBox(height: 12),
                      _LineItem("Tickets hors SLA", "${data["tickets_overdue"] ?? 0}"),
                      _LineItem("Produits sous garantie", "${data["products_under_warranty"] ?? 0}"),
                      _LineItem("Sessions support actives", "${data["support_sessions_active"] ?? 0}"),
                      _LineItem("Knowledge articles publies", "${data["knowledge_articles_published"] ?? 0}"),
                      if (widget.session.isInternal) ...[
                        _LineItem("Clients verifies", "${data["clients_verified"] ?? 0}"),
                        _LineItem("Transactions contestees", "${data["transactions_disputed"] ?? 0}"),
                        _LineItem(
                          "Satisfaction moyenne",
                          data["feedback_average_rating"] != null ? "${data["feedback_average_rating"]}/5" : "N/A",
                        ),
                      ] else ...[
                        _LineItem("Compte verifie", widget.session.isVerified ? "Oui" : "En attente"),
                        _LineItem("Solde", "${widget.session.accountBalance} XAF"),
                      ],
                      _LineItem(
                        "Premiere reponse moyenne",
                        data["average_first_response_hours"] != null
                            ? "${data["average_first_response_hours"]} h"
                            : "N/A",
                      ),
                      _LineItem(
                        "Resolution moyenne",
                        data["average_resolution_hours"] != null ? "${data["average_resolution_hours"]} h" : "N/A",
                      ),
                      if (topAgents.isNotEmpty)
                        _LineItem(
                          "Agent leader",
                          "${topAgents.first["agent_name"]} · ${topAgents.first["resolved_tickets"]} resolus",
                        ),
                    ],
                  ),
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}

class _SupportConversationEntry {
  const _SupportConversationEntry({
    required this.role,
    required this.message,
    this.payload,
  });

  final String role;
  final String message;
  final Map<String, dynamic>? payload;
}

class SupportScreen extends StatefulWidget {
  const SupportScreen({super.key, required this.session});

  final SavSession session;

  @override
  State<SupportScreen> createState() => _SupportScreenState();
}

class _SupportScreenState extends State<SupportScreen> {
  late Future<Map<String, dynamic>> _future;
  final TextEditingController _assistantController = TextEditingController();
  final List<_SupportConversationEntry> _conversation = const [
    _SupportConversationEntry(
      role: "assistant",
      message:
          "Expliquez votre incident comme dans un chat SAV. Je peux vous guider, suggérer des articles et preparer un ticket.",
    ),
  ].toList();
  bool _assistantBusy = false;
  int? _selectedProductId;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  @override
  void dispose() {
    _assistantController.dispose();
    super.dispose();
  }

  Future<Map<String, dynamic>> _load() async {
    final tickets = await widget.session.api.getList("tickets/");
    final products = await widget.session.api.getList("products/");
    if (_selectedProductId == null && products.isNotEmpty) {
      _selectedProductId = products.first["id"] as int;
    }
    return {
      "tickets": tickets,
      "products": products,
    };
  }

  Future<void> _refresh() async {
    setState(() => _future = _load());
    await _future;
  }

  Future<void> _askAssistant() async {
    final question = _assistantController.text.trim();
    if (question.isEmpty) {
      return;
    }

    setState(() {
      _assistantBusy = true;
      _conversation.add(_SupportConversationEntry(role: "user", message: question));
    });

    try {
      final payload = await widget.session.api.post("support/assistant/", {
        "question": question,
        if (_selectedProductId != null) "product": _selectedProductId,
      });
      if (!mounted) {
        return;
      }
      _assistantController.clear();
      setState(() {
        _conversation.add(
          _SupportConversationEntry(
            role: "assistant",
            message: (payload["answer"] ?? "").toString(),
            payload: payload,
          ),
        );
      });
    } catch (exc) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(exc.toString())));
    } finally {
      if (mounted) {
        setState(() => _assistantBusy = false);
      }
    }
  }

  Future<void> _openDraftTicket(Map<String, dynamic> payload) async {
    final draft = Map<String, dynamic>.from(payload["draft_ticket"] as Map? ?? <String, dynamic>{});
    final created = await Navigator.of(context).push<bool>(
      MaterialPageRoute<bool>(
        builder: (_) => TicketCreatePage(
          session: widget.session,
          initialTitle: (draft["title"] ?? "").toString(),
          initialDescription: (draft["description"] ?? "").toString(),
          initialCategory: (draft["category"] ?? "breakdown").toString(),
          initialPriority: (draft["priority"] ?? "normal").toString(),
          initialProductId: _selectedProductId,
        ),
      ),
    );
    if (created == true) {
      await _refresh();
    }
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<Map<String, dynamic>>(
      future: _future,
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done) {
          return const Center(child: CircularProgressIndicator());
        }
        if (snapshot.hasError) {
          return _ErrorView(message: snapshot.error.toString(), onRetry: _refresh);
        }

        final products = (snapshot.data?["products"] as List<dynamic>? ?? []).cast<Map<String, dynamic>>();
        final allTickets = (snapshot.data?["tickets"] as List<dynamic>? ?? []).cast<Map<String, dynamic>>();
        final selectedProductId =
            products.any((product) => product["id"] == _selectedProductId) ? _selectedProductId : null;
        final openTickets = allTickets.where((ticket) {
          final status = (ticket["status"] ?? "").toString();
          return status != "resolved" && status != "closed";
        }).toList();

        return RefreshIndicator(
          onRefresh: _refresh,
          child: ListView(
            padding: const EdgeInsets.all(20),
            children: [
              _HeroPanel(
                title: "Support",
                subtitle:
                    "Discutez avec l'assistant SAV, joignez vos preuves et ouvrez un ticket sans quitter le mobile.",
              ),
              const SizedBox(height: 16),
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(20),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text("Chat SAV", style: Theme.of(context).textTheme.titleLarge),
                      const SizedBox(height: 12),
                      if (products.isNotEmpty)
                        DropdownButtonFormField<int>(
                          initialValue: selectedProductId,
                          decoration: const InputDecoration(labelText: "Produit concerne"),
                          items: products
                              .map(
                                (product) => DropdownMenuItem<int>(
                                  value: product["id"] as int,
                                  child: Text("${product["name"]} · ${product["serial_number"]}"),
                                ),
                              )
                              .toList(),
                          onChanged: (value) => setState(() => _selectedProductId = value),
                        ),
                      if (products.isNotEmpty) const SizedBox(height: 12),
                      ..._conversation.map((entry) {
                        final payload = entry.payload;
                        final matchedArticles =
                            (payload?["matched_articles"] as List<dynamic>? ?? []).cast<dynamic>();
                        return Align(
                          alignment: entry.role == "user" ? Alignment.centerRight : Alignment.centerLeft,
                          child: Container(
                            margin: const EdgeInsets.only(bottom: 12),
                            padding: const EdgeInsets.all(16),
                            constraints: const BoxConstraints(maxWidth: 460),
                            decoration: BoxDecoration(
                              color: entry.role == "user"
                                  ? const Color(0xFFF4DEC2)
                                  : const Color(0xFFF8F2E7),
                              borderRadius: BorderRadius.circular(24),
                            ),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  entry.role == "user" ? "Vous" : "Assistant Afrilux",
                                  style: const TextStyle(fontWeight: FontWeight.w700),
                                ),
                                const SizedBox(height: 6),
                                Text(entry.message),
                                if (payload != null) ...[
                                  const SizedBox(height: 10),
                                  Wrap(
                                    spacing: 8,
                                    runSpacing: 8,
                                    children: [
                                      _StateChip(
                                        label: (payload["suggested_priority"] ?? "normal").toString(),
                                      ),
                                      _StateChip(
                                        label: (payload["suggested_category"] ?? "breakdown").toString(),
                                      ),
                                    ],
                                  ),
                                  if (matchedArticles.isNotEmpty) ...[
                                    const SizedBox(height: 10),
                                    Text(
                                      "Articles utiles",
                                      style: Theme.of(context)
                                          .textTheme
                                          .titleSmall
                                          ?.copyWith(fontWeight: FontWeight.w700),
                                    ),
                                    const SizedBox(height: 6),
                                    ...matchedArticles.map(
                                      (item) => Padding(
                                        padding: const EdgeInsets.only(bottom: 4),
                                        child: Text("• ${(Map<String, dynamic>.from(item as Map))["title"] ?? "Article"}"),
                                      ),
                                    ),
                                  ],
                                  if (payload["should_create_ticket"] == true) ...[
                                    const SizedBox(height: 12),
                                    FilledButton.icon(
                                      onPressed: () => _openDraftTicket(payload),
                                      icon: const Icon(Icons.confirmation_number_outlined),
                                      label: const Text("Creer un ticket"),
                                    ),
                                  ],
                                ],
                              ],
                            ),
                          ),
                        );
                      }),
                      TextField(
                        controller: _assistantController,
                        minLines: 2,
                        maxLines: 4,
                        decoration: const InputDecoration(
                          hintText: "Ex: mon equipement ne charge plus et affiche une erreur de cablage.",
                        ),
                      ),
                      const SizedBox(height: 12),
                      Row(
                        children: [
                          FilledButton.icon(
                            onPressed: _assistantBusy ? null : _askAssistant,
                            icon: const Icon(Icons.smart_toy_outlined),
                            label: _assistantBusy
                                ? const SizedBox(
                                    height: 16,
                                    width: 16,
                                    child: CircularProgressIndicator(strokeWidth: 2),
                                  )
                                : const Text("Envoyer"),
                          ),
                          const SizedBox(width: 12),
                          OutlinedButton.icon(
                            onPressed: () async {
                              final created = await Navigator.of(context).push<bool>(
                                MaterialPageRoute<bool>(
                                  builder: (_) => TicketCreatePage(
                                    session: widget.session,
                                    initialProductId: _selectedProductId,
                                  ),
                                ),
                              );
                              if (created == true) {
                                await _refresh();
                              }
                            },
                            icon: const Icon(Icons.add),
                            label: const Text("Nouveau ticket"),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 16),
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(20),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text("Mes dossiers", style: Theme.of(context).textTheme.titleLarge),
                      const SizedBox(height: 12),
                      _LineItem("Tickets ouverts", "${openTickets.length}"),
                      if (widget.session.organizationSupportEmail.isNotEmpty)
                        _LineItem("Email SAV", widget.session.organizationSupportEmail),
                      if (widget.session.organizationSupportPhone.isNotEmpty)
                        _LineItem("Telephone / WhatsApp", widget.session.organizationSupportPhone),
                      const SizedBox(height: 14),
                      ...allTickets.map(
                        (ticket) => Padding(
                          padding: const EdgeInsets.only(bottom: 12),
                          child: ListTile(
                            contentPadding: EdgeInsets.zero,
                            title: Text((ticket["title"] ?? "").toString()),
                            subtitle: Text("${ticket["reference"]} · ${ticket["status"] ?? ""}"),
                            trailing: _StateChip(label: (ticket["priority"] ?? "normal").toString()),
                            onTap: () async {
                              await Navigator.of(context).push(
                                MaterialPageRoute<void>(
                                  builder: (_) => TicketDetailPage(
                                    session: widget.session,
                                    ticketId: ticket["id"] as int,
                                  ),
                                ),
                              );
                              await _refresh();
                            },
                          ),
                        ),
                      ),
                      if (allTickets.isEmpty)
                        const Text("Aucun ticket pour le moment. Le chat ci-dessus peut preparer le premier."),
                    ],
                  ),
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}

class TicketsScreen extends StatefulWidget {
  const TicketsScreen({super.key, required this.session});

  final SavSession session;

  @override
  State<TicketsScreen> createState() => _TicketsScreenState();
}

class _TicketsScreenState extends State<TicketsScreen> {
  late Future<List<Map<String, dynamic>>> _future;
  final TextEditingController _assistantController = TextEditingController();
  String _query = "";
  String _focus = "all";
  String _assignmentFocus = "all";
  bool _assistantBusy = false;
  Map<String, dynamic>? _assistantResult;

  @override
  void initState() {
    super.initState();
    _future = widget.session.api.getList("tickets/");
  }

  @override
  void dispose() {
    _assistantController.dispose();
    super.dispose();
  }

  Future<void> _refresh() async {
    setState(() {
      _future = widget.session.api.getList("tickets/");
    });
    await _future;
  }

  Future<void> _askAssistant() async {
    final question = _assistantController.text.trim();
    if (question.isEmpty) {
      return;
    }
    setState(() => _assistantBusy = true);
    try {
      final result = await widget.session.api.post("support/assistant/", {"question": question});
      if (!mounted) {
        return;
      }
      setState(() => _assistantResult = result);
    } catch (exc) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(exc.toString())));
    } finally {
      if (mounted) {
        setState(() => _assistantBusy = false);
      }
    }
  }

  Future<void> _openDraftTicket() async {
    final draft = Map<String, dynamic>.from(_assistantResult?["draft_ticket"] as Map? ?? <String, dynamic>{});
    final created = await Navigator.of(context).push<bool>(
      MaterialPageRoute<bool>(
        builder: (_) => TicketCreatePage(
          session: widget.session,
          initialTitle: (draft["title"] ?? "").toString(),
          initialDescription: (draft["description"] ?? "").toString(),
          initialCategory: (draft["category"] ?? "breakdown").toString(),
          initialPriority: (draft["priority"] ?? "normal").toString(),
        ),
      ),
    );
    if (created == true) {
      await _refresh();
    }
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<List<Map<String, dynamic>>>(
      future: _future,
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done) {
          return const Center(child: CircularProgressIndicator());
        }
        if (snapshot.hasError) {
          return _ErrorView(message: snapshot.error.toString(), onRetry: _refresh);
        }

        final allTickets = snapshot.data ?? <Map<String, dynamic>>[];
        final openTickets = allTickets.where((ticket) {
          final status = (ticket["status"] ?? "").toString();
          return status != "resolved" && status != "closed";
        }).length;
        final tickets = allTickets.where((ticket) {
          final probe = "${ticket["reference"]} ${ticket["title"]} ${ticket["client_name"]}".toLowerCase();
          final matchesQuery = probe.contains(_query.toLowerCase());
          final isUrgent = ticket["priority"] == "high" || ticket["priority"] == "critical";
          final isFraud = ticket["suspected_fraud"] == true;
          final isMine = (ticket["assigned_agent"] ?? 0) == widget.session.userId;
          final isUnassigned = ticket["assigned_agent"] == null;

          if (!matchesQuery) {
            return false;
          }
          if (widget.session.isInternal) {
            if (_assignmentFocus == "mine" && !isMine) {
              return false;
            }
            if (_assignmentFocus == "unassigned" && !isUnassigned) {
              return false;
            }
          }
          if (_focus == "urgent") {
            return isUrgent;
          }
          if (_focus == "fraud") {
            return isFraud;
          }
          return true;
        }).toList();
        final matchedArticles = (_assistantResult?["matched_articles"] as List<dynamic>? ?? []).cast<dynamic>();
        final supportLabel = widget.session.isInternal ? "Tickets" : "Support";

        return RefreshIndicator(
          onRefresh: _refresh,
          child: ListView(
            padding: const EdgeInsets.all(20),
            children: [
              if (!widget.session.isInternal) ...[
                _HeroPanel(
                  title: "Support client",
                  subtitle:
                      "Créez un ticket, suivez l'avancement de chaque incident et joignez des preuves directement depuis votre espace mobile.",
                ),
                const SizedBox(height: 16),
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(20),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text("Acces rapides", style: Theme.of(context).textTheme.titleLarge),
                        const SizedBox(height: 12),
                        _LineItem("Tickets ouverts", "$openTickets"),
                        _LineItem("Compte verifie", widget.session.isVerified ? "Oui" : "En attente"),
                        _LineItem("Solde", "${widget.session.accountBalance} XAF"),
                        if (widget.session.organizationSupportEmail.isNotEmpty)
                          _LineItem("Email SAV", widget.session.organizationSupportEmail),
                        if (widget.session.organizationSupportPhone.isNotEmpty)
                          _LineItem("WhatsApp / Telephone", widget.session.organizationSupportPhone),
                        const SizedBox(height: 12),
                        Text(
                          "Chatbot IA",
                          style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700),
                        ),
                        const SizedBox(height: 8),
                        TextField(
                          controller: _assistantController,
                          minLines: 2,
                          maxLines: 4,
                          decoration: const InputDecoration(
                            hintText: "Ex: mon equipement ne charge plus, que faire ?",
                          ),
                        ),
                        const SizedBox(height: 12),
                        Row(
                          children: [
                            FilledButton.icon(
                              onPressed: _assistantBusy ? null : _askAssistant,
                              icon: const Icon(Icons.smart_toy_outlined),
                              label: _assistantBusy
                                  ? const SizedBox(
                                      height: 16,
                                      width: 16,
                                      child: CircularProgressIndicator(strokeWidth: 2),
                                    )
                                  : const Text("Demander a l'assistant"),
                            ),
                            const SizedBox(width: 12),
                            OutlinedButton.icon(
                              onPressed: () async {
                                final created = await Navigator.of(context).push<bool>(
                                  MaterialPageRoute<bool>(builder: (_) => TicketCreatePage(session: widget.session)),
                                );
                                if (created == true) {
                                  await _refresh();
                                }
                              },
                              icon: const Icon(Icons.add),
                              label: const Text("Nouveau ticket"),
                            ),
                          ],
                        ),
                        if (_assistantResult != null) ...[
                          const SizedBox(height: 16),
                          Container(
                            padding: const EdgeInsets.all(16),
                            decoration: BoxDecoration(
                              color: const Color(0xFFF8F2E7),
                              borderRadius: BorderRadius.circular(20),
                            ),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  (_assistantResult?["answer"] ?? "").toString(),
                                  style: Theme.of(context).textTheme.bodyLarge,
                                ),
                                const SizedBox(height: 12),
                                Wrap(
                                  spacing: 10,
                                  runSpacing: 10,
                                  children: [
                                    _StateChip(label: (_assistantResult?["suggested_priority"] ?? "normal").toString()),
                                    _StateChip(label: (_assistantResult?["suggested_category"] ?? "breakdown").toString()),
                                  ],
                                ),
                                if ((_assistantResult?["recommended_next_step"] ?? "").toString().isNotEmpty) ...[
                                  const SizedBox(height: 12),
                                  Text(
                                    "Prochaine etape: ${(_assistantResult?["recommended_next_step"] ?? "").toString()}",
                                  ),
                                ],
                                if (matchedArticles.isNotEmpty) ...[
                                  const SizedBox(height: 12),
                                  Text(
                                    "Articles utiles",
                                    style: Theme.of(context).textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w700),
                                  ),
                                  const SizedBox(height: 8),
                                  ...matchedArticles.map(
                                    (item) => Padding(
                                      padding: const EdgeInsets.only(bottom: 6),
                                      child: Text("• ${(Map<String, dynamic>.from(item as Map))["title"] ?? "Article"}"),
                                    ),
                                  ),
                                ],
                                if (_assistantResult?["should_create_ticket"] == true) ...[
                                  const SizedBox(height: 12),
                                  FilledButton.icon(
                                    onPressed: _openDraftTicket,
                                    icon: const Icon(Icons.confirmation_number_outlined),
                                    label: const Text("Creer un ticket depuis cette analyse"),
                                  ),
                                ],
                              ],
                            ),
                          ),
                        ],
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 16),
              ],
              Text(
                supportLabel,
                style: Theme.of(context).textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w700),
              ),
              const SizedBox(height: 10),
              TextField(
                decoration: const InputDecoration(
                  prefixIcon: Icon(Icons.search),
                  hintText: "Rechercher un ticket, une reference ou un client",
                ),
                onChanged: (value) => setState(() => _query = value),
              ),
              const SizedBox(height: 12),
              Wrap(
                spacing: 10,
                runSpacing: 10,
                children: [
                  ChoiceChip(label: const Text("Tous"), selected: _focus == "all", onSelected: (_) => setState(() => _focus = "all")),
                  ChoiceChip(
                    label: const Text("Urgents"),
                    selected: _focus == "urgent",
                    onSelected: (_) => setState(() => _focus = "urgent"),
                  ),
                  ChoiceChip(
                    label: const Text("Fraude"),
                    selected: _focus == "fraud",
                    onSelected: (_) => setState(() => _focus = "fraud"),
                  ),
                  if (widget.session.isInternal)
                    ChoiceChip(
                      label: const Text("Mes tickets"),
                      selected: _assignmentFocus == "mine",
                      onSelected: (_) => setState(() => _assignmentFocus = _assignmentFocus == "mine" ? "all" : "mine"),
                    ),
                  if (widget.session.isInternal)
                    ChoiceChip(
                      label: const Text("Non assignes"),
                      selected: _assignmentFocus == "unassigned",
                      onSelected: (_) => setState(() => _assignmentFocus = _assignmentFocus == "unassigned" ? "all" : "unassigned"),
                    ),
                ],
              ),
              const SizedBox(height: 16),
              ...tickets.map(
                (ticket) => Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: Card(
                    child: ListTile(
                      title: Text((ticket["title"] ?? "").toString()),
                      subtitle: Text("${ticket["reference"]} · ${ticket["client_name"] ?? ""}"),
                      trailing: Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          _StateChip(label: (ticket["status"] ?? "").toString()),
                          const SizedBox(height: 6),
                          Text((ticket["priority"] ?? "").toString()),
                          if (ticket["suspected_fraud"] == true) ...[
                            const SizedBox(height: 6),
                            const _StateChip(label: "fraude"),
                          ],
                        ],
                      ),
                      onTap: () async {
                        await Navigator.of(context).push(
                          MaterialPageRoute<void>(
                            builder: (_) => TicketDetailPage(session: widget.session, ticketId: ticket["id"] as int),
                          ),
                        );
                        await _refresh();
                      },
                    ),
                  ),
                ),
              ),
              if (tickets.isEmpty)
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(24),
                    child: Text(
                      widget.session.isInternal
                          ? "Aucun ticket visible sur votre perimetre."
                          : "Aucun ticket pour le moment. Utilisez le bouton ci-dessus pour ouvrir un dossier de support.",
                    ),
                  ),
                ),
            ],
          ),
        );
      },
    );
  }
}

class TicketDetailPage extends StatefulWidget {
  const TicketDetailPage({super.key, required this.session, required this.ticketId});

  final SavSession session;
  final int ticketId;

  @override
  State<TicketDetailPage> createState() => _TicketDetailPageState();
}

class _TicketDetailPageState extends State<TicketDetailPage> {
  late Future<Map<String, dynamic>> _future;
  final TextEditingController _messageController = TextEditingController();
  final ImagePicker _imagePicker = ImagePicker();
  bool _busy = false;
  String _messageChannel = "portal";

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  @override
  void dispose() {
    _messageController.dispose();
    super.dispose();
  }

  Future<Map<String, dynamic>> _load() async {
    final ticket = await widget.session.api.getMap("tickets/${widget.ticketId}/");
    Map<String, dynamic>? insight;
    final clientId = ticket["client"] as int?;
    if (widget.session.isInternal && clientId != null) {
      try {
        insight = await widget.session.api.getMap("users/$clientId/insights/");
      } catch (_) {
        insight = null;
      }
    }
    return {
      "ticket": ticket,
      "insight": insight,
    };
  }

  Future<void> _refresh() async {
    setState(() {
      _future = _load();
    });
    await _future;
  }

  Future<void> _runAgenticResolution() async {
    setState(() => _busy = true);
    try {
      final result = await widget.session.api.post("tickets/${widget.ticketId}/agentic_resolution/", {});
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text((result["resolution_summary"] ?? "Analyse terminee.").toString())),
      );
      await _refresh();
    } catch (exc) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(exc.toString())));
    } finally {
      if (mounted) {
        setState(() => _busy = false);
      }
    }
  }

  Future<void> _takeOwnership() async {
    setState(() => _busy = true);
    try {
      await widget.session.api.post("tickets/${widget.ticketId}/take_ownership/", {});
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text("Le ticket vous est maintenant assigne.")),
      );
      await _refresh();
    } catch (exc) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(exc.toString())));
    } finally {
      if (mounted) {
        setState(() => _busy = false);
      }
    }
  }

  Future<void> _reopenTicket() async {
    setState(() => _busy = true);
    try {
      await widget.session.api.post("tickets/${widget.ticketId}/reopen/", {});
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text("Le ticket a ete rouvert.")),
      );
      await _refresh();
    } catch (exc) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(exc.toString())));
    } finally {
      if (mounted) {
        setState(() => _busy = false);
      }
    }
  }

  Future<void> _showFeedbackDialog() async {
    final commentController = TextEditingController();
    double rating = 5;
    try {
      final submitted = await showDialog<bool>(
        context: context,
        builder: (context) => StatefulBuilder(
          builder: (context, setDialogState) => AlertDialog(
            title: const Text("Noter le support"),
            content: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text("Note: ${rating.toInt()}/5"),
                  Slider(
                    min: 1,
                    max: 5,
                    divisions: 4,
                    label: rating.toInt().toString(),
                    value: rating,
                    onChanged: (value) => setDialogState(() => rating = value),
                  ),
                  TextField(
                    controller: commentController,
                    minLines: 2,
                    maxLines: 4,
                    decoration: const InputDecoration(labelText: "Commentaire"),
                  ),
                ],
              ),
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.of(context).pop(false),
                child: const Text("Annuler"),
              ),
              FilledButton(
                onPressed: () => Navigator.of(context).pop(true),
                child: const Text("Envoyer"),
              ),
            ],
          ),
        ),
      );

      if (submitted != true) {
        return;
      }

      setState(() => _busy = true);
      await widget.session.api.post("ticket-feedbacks/", {
        "ticket": widget.ticketId,
        "rating": rating.toInt(),
        "comment": commentController.text.trim(),
      });
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text("Merci pour votre retour.")),
      );
      await _refresh();
    } catch (exc) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(exc.toString())));
    } finally {
      commentController.dispose();
      if (mounted) {
        setState(() => _busy = false);
      }
    }
  }

  Future<void> _sendMessage() async {
    final content = _messageController.text.trim();
    if (content.isEmpty) return;
    setState(() => _busy = true);
    try {
      await widget.session.api.post("messages/", {
        "ticket": widget.ticketId,
        "content": content,
        "channel": widget.session.isInternal ? _messageChannel : "portal",
      });
      _messageController.clear();
      await _refresh();
    } catch (exc) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(exc.toString())));
    } finally {
      if (mounted) {
        setState(() => _busy = false);
      }
    }
  }

  Future<void> _uploadAttachment(ImageSource source, String kind, String note) async {
    setState(() => _busy = true);
    try {
      final picked = await _imagePicker.pickImage(source: source, imageQuality: 88);
      if (picked == null) {
        return;
      }
      await widget.session.api.postMultipart(
        "ticket-attachments/",
        fields: {
          "ticket": widget.ticketId.toString(),
          "kind": kind,
          "note": note,
        },
        filePath: picked.path,
        filename: picked.name,
      );
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text("Preuve ajoutee au ticket.")));
      await _refresh();
    } catch (exc) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(exc.toString())));
    } finally {
      if (mounted) {
        setState(() => _busy = false);
      }
    }
  }

  Future<void> _showAttachmentOptions() async {
    await showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      builder: (context) => SafeArea(
        child: Wrap(
          children: [
            ListTile(
              leading: const Icon(Icons.photo_library_outlined),
              title: const Text("Ajouter une capture"),
              subtitle: const Text("Depuis la galerie ou vos captures d'ecran"),
              onTap: () {
                Navigator.of(context).pop();
                unawaited(_uploadAttachment(ImageSource.gallery, "screenshot", "Capture ecran client"));
              },
            ),
            ListTile(
              leading: const Icon(Icons.receipt_long_outlined),
              title: const Text("Photographier un recu"),
              subtitle: const Text("Camera mobile"),
              onTap: () {
                Navigator.of(context).pop();
                unawaited(_uploadAttachment(ImageSource.camera, "receipt", "Recu ou justificatif client"));
              },
            ),
            ListTile(
              leading: const Icon(Icons.verified_outlined),
              title: const Text("Ajouter une preuve"),
              subtitle: const Text("Photo generale depuis la galerie"),
              onTap: () {
                Navigator.of(context).pop();
                unawaited(_uploadAttachment(ImageSource.gallery, "proof", "Preuve de transaction ou incident"));
              },
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _showCreditAccountDialog() async {
    final amountController = TextEditingController();
    final reasonController = TextEditingController(text: "Avoir commercial");
    final noteController = TextEditingController();
    final externalReferenceController = TextEditingController();
    try {
      final submitted = await showDialog<bool>(
        context: context,
        builder: (context) => AlertDialog(
          title: const Text("Crediter le compte"),
          content: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                TextField(
                  controller: amountController,
                  keyboardType: const TextInputType.numberWithOptions(decimal: true),
                  decoration: const InputDecoration(labelText: "Montant"),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: reasonController,
                  decoration: const InputDecoration(labelText: "Motif"),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: noteController,
                  minLines: 2,
                  maxLines: 4,
                  decoration: const InputDecoration(labelText: "Note"),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: externalReferenceController,
                  decoration: const InputDecoration(labelText: "Reference externe"),
                ),
              ],
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(false),
              child: const Text("Annuler"),
            ),
            FilledButton(
              onPressed: () => Navigator.of(context).pop(true),
              child: const Text("Crediter"),
            ),
          ],
        ),
      );

      if (submitted != true) {
        return;
      }

      setState(() => _busy = true);
      await widget.session.api.post("tickets/${widget.ticketId}/credit_account/", {
        "amount": amountController.text.trim(),
        "currency": "XAF",
        "reason": reasonController.text.trim(),
        "note": noteController.text.trim(),
        "external_reference": externalReferenceController.text.trim(),
      });
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text("Le compte client a ete credite.")),
      );
      await _refresh();
    } catch (exc) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(exc.toString())));
    } finally {
      amountController.dispose();
      reasonController.dispose();
      noteController.dispose();
      externalReferenceController.dispose();
      if (mounted) {
        setState(() => _busy = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text("Detail ticket")),
      body: FutureBuilder<Map<String, dynamic>>(
        future: _future,
        builder: (context, snapshot) {
          if (snapshot.connectionState != ConnectionState.done) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snapshot.hasError) {
            return _ErrorView(message: snapshot.error.toString(), onRetry: _refresh);
          }

          final payload = snapshot.data ?? <String, dynamic>{};
          final ticket = Map<String, dynamic>.from(payload["ticket"] as Map? ?? <String, dynamic>{});
          final insight = payload["insight"] is Map ? Map<String, dynamic>.from(payload["insight"] as Map) : null;
          final messages = (ticket["messages"] as List<dynamic>? ?? []).cast<Map<String, dynamic>>();
          final attachments = (ticket["attachments"] as List<dynamic>? ?? []).cast<Map<String, dynamic>>();
          final interventions = (ticket["interventions"] as List<dynamic>? ?? []).cast<Map<String, dynamic>>();
          final sessions = (ticket["support_sessions"] as List<dynamic>? ?? []).cast<Map<String, dynamic>>();
          final accountCredits = (ticket["account_credits"] as List<dynamic>? ?? []).cast<Map<String, dynamic>>();
          final feedback = ticket["feedback"] is Map
              ? Map<String, dynamic>.from(ticket["feedback"] as Map)
              : null;
          final canReopen = const {"resolved", "closed"}.contains((ticket["status"] ?? "").toString());
          final canTakeOwnership =
              widget.session.isInternal && (ticket["assigned_agent"] ?? 0) != widget.session.userId;

          return RefreshIndicator(
            onRefresh: _refresh,
            child: ListView(
              padding: const EdgeInsets.all(20),
              children: [
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(20),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text((ticket["title"] ?? "").toString(), style: Theme.of(context).textTheme.headlineSmall),
                        const SizedBox(height: 10),
                        Wrap(
                          spacing: 10,
                          runSpacing: 10,
                          children: [
                            _StateChip(label: (ticket["status"] ?? "").toString()),
                            _StateChip(label: (ticket["priority"] ?? "").toString()),
                            _StateChip(label: (ticket["channel"] ?? "").toString()),
                            if (ticket["suspected_fraud"] == true) const _StateChip(label: "fraude"),
                          ],
                        ),
                        const SizedBox(height: 12),
                        Text((ticket["description"] ?? "").toString()),
                        const SizedBox(height: 12),
                        _LineItem("Reference", (ticket["reference"] ?? "").toString()),
                        _LineItem("Client", (ticket["client_name"] ?? "").toString()),
                        _LineItem("Produit", (ticket["product_name"] ?? "Sans produit").toString()),
                        if ((ticket["related_transaction_reference"] ?? "").toString().isNotEmpty)
                          _LineItem(
                            "Transaction",
                            "${ticket["related_transaction_reference"]} · ${ticket["related_transaction_amount"] ?? ""} ${ticket["related_transaction_currency"] ?? ""}",
                          ),
                        if ((ticket["resolution_summary"] ?? "").toString().isNotEmpty)
                          Padding(
                            padding: const EdgeInsets.only(top: 12),
                            child: Text(
                              (ticket["resolution_summary"] ?? "").toString(),
                              style: const TextStyle(fontWeight: FontWeight.w600),
                            ),
                          ),
                        const SizedBox(height: 16),
                        FilledButton.icon(
                          onPressed: _busy ? null : _runAgenticResolution,
                          icon: const Icon(Icons.auto_awesome_outlined),
                          label: const Text("Resolution agentique"),
                        ),
                        if (canTakeOwnership) ...[
                          const SizedBox(height: 12),
                          OutlinedButton.icon(
                            onPressed: _busy ? null : _takeOwnership,
                            icon: const Icon(Icons.assignment_ind_outlined),
                            label: const Text("Prendre le ticket"),
                          ),
                        ],
                        if (widget.session.isManager) ...[
                          const SizedBox(height: 12),
                          OutlinedButton.icon(
                            onPressed: _busy ? null : _showCreditAccountDialog,
                            icon: const Icon(Icons.account_balance_wallet_outlined),
                            label: const Text("Crediter le compte"),
                          ),
                        ],
                        if (!widget.session.isInternal && canReopen) ...[
                          const SizedBox(height: 12),
                          OutlinedButton.icon(
                            onPressed: _busy ? null : _reopenTicket,
                            icon: const Icon(Icons.restart_alt_outlined),
                            label: const Text("Rouvrir le ticket"),
                          ),
                        ],
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 16),
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(20),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text("Actions metier", style: Theme.of(context).textTheme.titleLarge),
                        const SizedBox(height: 12),
                        ...accountCredits.map(
                          (item) => _LineItem(
                            "${item["amount"] ?? "0"} ${item["currency"] ?? "XAF"}",
                            "${item["reason"] ?? ""} · ${item["executed_by_name"] ?? "Systeme"}",
                          ),
                        ),
                        if (feedback != null) ...[
                          const SizedBox(height: 12),
                          _LineItem(
                            "Feedback client",
                            "${feedback["rating"] ?? "?"}/5 · ${(feedback["comment"] ?? "Aucun commentaire").toString()}",
                          ),
                        ],
                        if (accountCredits.isEmpty) const Text("Aucun credit compte execute sur ce ticket."),
                        if (feedback == null && !widget.session.isInternal && canReopen) ...[
                          const SizedBox(height: 12),
                          FilledButton.icon(
                            onPressed: _busy ? null : _showFeedbackDialog,
                            icon: const Icon(Icons.star_outline),
                            label: const Text("Noter le support"),
                          ),
                        ],
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 16),
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(20),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text("Suivi du processus", style: Theme.of(context).textTheme.titleLarge),
                        const SizedBox(height: 12),
                        _ProcessStep(
                          title: "Ticket cree",
                          subtitle: (ticket["created_at"] ?? "").toString(),
                          isDone: true,
                        ),
                        _ProcessStep(
                          title: "Prise en charge",
                          subtitle: (ticket["first_response_at"] ?? "En attente d'une premiere reponse").toString(),
                          isDone: (ticket["first_response_at"] ?? "").toString().isNotEmpty,
                        ),
                        _ProcessStep(
                          title: "Traitement",
                          subtitle: (ticket["status"] ?? "").toString(),
                          isDone: const {
                            "assigned",
                            "in_progress",
                            "waiting",
                            "resolved",
                            "closed",
                          }.contains((ticket["status"] ?? "").toString()),
                        ),
                        _ProcessStep(
                          title: "Ticket resolu",
                          subtitle: (ticket["resolved_at"] ?? "Pas encore resolu").toString(),
                          isDone: (ticket["resolved_at"] ?? "").toString().isNotEmpty,
                        ),
                        _ProcessStep(
                          title: "Ticket ferme",
                          subtitle: (ticket["closed_at"] ?? "Dossier encore actif").toString(),
                          isDone: (ticket["closed_at"] ?? "").toString().isNotEmpty,
                          isLast: true,
                        ),
                      ],
                    ),
                  ),
                ),
                if (insight != null) ...[
                  const SizedBox(height: 16),
                  Card(
                    child: Padding(
                      padding: const EdgeInsets.all(20),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text("Intelligence client", style: Theme.of(context).textTheme.titleLarge),
                          const SizedBox(height: 12),
                          Wrap(
                            spacing: 10,
                            runSpacing: 10,
                            children: [
                              _StateChip(label: "Risque ${insight["risk_level"] ?? "low"}"),
                              _StateChip(label: "${insight["open_tickets"] ?? 0} ticket(s) ouverts"),
                              _StateChip(label: "Sentiment ${insight["average_sentiment"] ?? "0.00"}"),
                              _StateChip(label: "Verifie ${insight["is_verified"] == true ? "oui" : "non"}"),
                            ],
                          ),
                          const SizedBox(height: 12),
                          Text((insight["summary"] ?? "").toString()),
                          const SizedBox(height: 12),
                          _LineItem("Solde client", "${insight["account_balance"] ?? "0.00"} XAF"),
                          _LineItem("Transactions contestees", "${insight["disputed_transactions"] ?? 0}"),
                          if ((insight["recent_transactions"] as List<dynamic>? ?? []).isNotEmpty) ...[
                            const SizedBox(height: 12),
                            Text("Transactions recentes", style: Theme.of(context).textTheme.titleMedium),
                            const SizedBox(height: 8),
                            ...((insight["recent_transactions"] as List<dynamic>? ?? []).take(4).map(
                              (item) {
                                final transaction = Map<String, dynamic>.from(item as Map);
                                return Padding(
                                  padding: const EdgeInsets.only(bottom: 6),
                                  child: Text(
                                    "• ${transaction["external_reference"] ?? "TX"} · ${transaction["amount"] ?? "0"} ${transaction["currency"] ?? "XAF"} · ${transaction["status"] ?? ""}",
                                  ),
                                );
                              },
                            )),
                          ],
                          if ((insight["suggested_actions"] as List<dynamic>? ?? []).isNotEmpty) ...[
                            const SizedBox(height: 12),
                            Text("Actions suggerees", style: Theme.of(context).textTheme.titleMedium),
                            const SizedBox(height: 8),
                            ...((insight["suggested_actions"] as List<dynamic>? ?? []).map(
                              (item) => Padding(
                                padding: const EdgeInsets.only(bottom: 6),
                                child: Text("• ${item.toString()}"),
                              ),
                            )),
                          ],
                          if ((insight["recommended_offers"] as List<dynamic>? ?? []).isNotEmpty) ...[
                            const SizedBox(height: 12),
                            Text("Opportunites commerciales", style: Theme.of(context).textTheme.titleMedium),
                            const SizedBox(height: 8),
                            ...((insight["recommended_offers"] as List<dynamic>? ?? []).map(
                              (item) => Padding(
                                padding: const EdgeInsets.only(bottom: 6),
                                child: Text("• ${(Map<String, dynamic>.from(item as Map))["title"] ?? "Offre"}"),
                              ),
                            )),
                          ],
                        ],
                      ),
                    ),
                  ),
                ],
                const SizedBox(height: 16),
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(20),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            Expanded(child: Text("Pieces jointes", style: Theme.of(context).textTheme.titleLarge)),
                            FilledButton.icon(
                              onPressed: _busy ? null : _showAttachmentOptions,
                              icon: const Icon(Icons.attach_file),
                              label: const Text("Joindre"),
                            ),
                          ],
                        ),
                        const SizedBox(height: 12),
                        ...attachments.map(
                          (attachment) => Padding(
                            padding: const EdgeInsets.only(bottom: 12),
                            child: _LineItem(
                              (attachment["original_name"] ?? "Fichier").toString(),
                              "${attachment["kind"] ?? "proof"} · ${attachment["note"] ?? ""}",
                            ),
                          ),
                        ),
                        if (attachments.isEmpty)
                          const Text("Aucune preuve chargee. Ajoutez une capture, un recu ou une photo du probleme."),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 16),
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(20),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text("Messages", style: Theme.of(context).textTheme.titleLarge),
                        const SizedBox(height: 12),
                        ...messages.map(
                          (message) => Container(
                            margin: const EdgeInsets.only(bottom: 12),
                            padding: const EdgeInsets.all(14),
                            decoration: BoxDecoration(
                              color: const Color(0xFFF8F2E7),
                              borderRadius: BorderRadius.circular(20),
                            ),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Row(
                                  children: [
                                    Expanded(
                                      child: Text(
                                        (message["sender_name"] ?? "").toString(),
                                        style: const TextStyle(fontWeight: FontWeight.w700),
                                      ),
                                    ),
                                    _StateChip(label: (message["channel"] ?? "portal").toString()),
                                  ],
                                ),
                                const SizedBox(height: 4),
                                Text((message["content"] ?? "").toString()),
                              ],
                            ),
                          ),
                        ),
                        if (widget.session.isInternal) ...[
                          const SizedBox(height: 8),
                          DropdownButtonFormField<String>(
                            initialValue: _messageChannel,
                            decoration: const InputDecoration(labelText: "Canal de reponse"),
                            items: const [
                              DropdownMenuItem(value: "portal", child: Text("Portail / in-app")),
                              DropdownMenuItem(value: "email", child: Text("Email")),
                              DropdownMenuItem(value: "whatsapp", child: Text("WhatsApp")),
                              DropdownMenuItem(value: "sms", child: Text("SMS")),
                            ],
                            onChanged: (value) => setState(() => _messageChannel = value ?? "portal"),
                          ),
                          const SizedBox(height: 12),
                        ],
                        TextField(
                          controller: _messageController,
                          minLines: 2,
                          maxLines: 4,
                          decoration: const InputDecoration(hintText: "Ajouter un message"),
                        ),
                        const SizedBox(height: 12),
                        FilledButton(onPressed: _busy ? null : _sendMessage, child: const Text("Envoyer")),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 16),
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(20),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text("Interventions", style: Theme.of(context).textTheme.titleLarge),
                        const SizedBox(height: 12),
                        ...interventions.map(
                          (item) => _LineItem(
                            (item["action_taken"] ?? "").toString(),
                            "${item["agent_name"] ?? ""} · ${item["status"] ?? ""}",
                          ),
                        ),
                        if (interventions.isEmpty) const Text("Aucune intervention rattachee."),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 16),
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(20),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text("Sessions support", style: Theme.of(context).textTheme.titleLarge),
                        const SizedBox(height: 12),
                        ...sessions.map(
                          (item) => _LineItem(
                            (item["session_type"] ?? "").toString(),
                            "${item["status"] ?? ""} · ${item["scheduled_for"] ?? ""}",
                          ),
                        ),
                        if (sessions.isEmpty) const Text("Aucune session support."),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          );
        },
      ),
    );
  }
}

class _DraftAttachment {
  const _DraftAttachment({
    required this.file,
    required this.kind,
    required this.note,
  });

  final XFile file;
  final String kind;
  final String note;
}

class TicketCreatePage extends StatefulWidget {
  const TicketCreatePage({
    super.key,
    required this.session,
    this.initialTitle = "",
    this.initialDescription = "",
    this.initialCategory = "breakdown",
    this.initialPriority = "normal",
    this.initialProductId,
  });

  final SavSession session;
  final String initialTitle;
  final String initialDescription;
  final String initialCategory;
  final String initialPriority;
  final int? initialProductId;

  @override
  State<TicketCreatePage> createState() => _TicketCreatePageState();
}

class _TicketCreatePageState extends State<TicketCreatePage> {
  late final TextEditingController _titleController;
  late final TextEditingController _descriptionController;
  final ImagePicker _imagePicker = ImagePicker();

  List<Map<String, dynamic>> _users = [];
  List<Map<String, dynamic>> _products = [];
  List<Map<String, dynamic>> _transactions = [];
  List<_DraftAttachment> _draftAttachments = [];
  bool _loading = true;
  bool _saving = false;
  int? _selectedClientId;
  int? _selectedProductId;
  int? _selectedTransactionId;
  late String _category;
  late String _priority;
  bool _suspectedFraud = false;

  @override
  void initState() {
    super.initState();
    _titleController = TextEditingController(text: widget.initialTitle);
    _descriptionController = TextEditingController(text: widget.initialDescription);
    _category = widget.initialCategory;
    _priority = widget.initialPriority;
    unawaited(_bootstrap());
  }

  @override
  void dispose() {
    _titleController.dispose();
    _descriptionController.dispose();
    super.dispose();
  }

  Future<void> _bootstrap() async {
    try {
      final users = widget.session.isInternal
          ? await widget.session.api.getList("users/")
          : [await widget.session.api.getMap("users/me/")];
      final products = await widget.session.api.getList("products/");
      final transactions = await widget.session.api.getList("financial-transactions/");
      final clientUsers = users.where((user) => (user["role"] ?? "client") == "client").toList();
      if (!mounted) return;
      setState(() {
        _users = clientUsers;
        _products = products;
        _transactions = transactions;
        _selectedClientId = clientUsers.isNotEmpty ? clientUsers.first["id"] as int : widget.session.userId;
        final visibleProducts = _visibleProducts();
        final visibleTransactions = _visibleTransactions();
        final matchingInitial = widget.initialProductId != null &&
                visibleProducts.any((product) => product["id"] == widget.initialProductId)
            ? widget.initialProductId
            : null;
        _selectedProductId = matchingInitial ?? (visibleProducts.isNotEmpty ? visibleProducts.first["id"] as int : null);
        _selectedTransactionId = visibleTransactions.isNotEmpty ? visibleTransactions.first["id"] as int : null;
        _loading = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() => _loading = false);
    }
  }

  List<Map<String, dynamic>> _visibleProducts() {
    if (_selectedClientId == null) return _products;
    return _products.where((product) => product["client"] == _selectedClientId).toList();
  }

  List<Map<String, dynamic>> _visibleTransactions() {
    if (_selectedClientId == null) return _transactions;
    return _transactions.where((item) => item["client"] == _selectedClientId).toList();
  }

  Future<void> _pickAttachment({
    required ImageSource source,
    required String kind,
    required String note,
  }) async {
    final picked = await _imagePicker.pickImage(source: source, imageQuality: 88);
    if (picked == null || !mounted) {
      return;
    }
    setState(() {
      _draftAttachments = [
        ..._draftAttachments,
        _DraftAttachment(file: picked, kind: kind, note: note),
      ];
    });
  }

  Future<void> _showAttachmentOptions() async {
    await showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      builder: (context) => SafeArea(
        child: Wrap(
          children: [
            ListTile(
              leading: const Icon(Icons.photo_library_outlined),
              title: const Text("Ajouter une capture"),
              subtitle: const Text("Galerie ou capture d'ecran"),
              onTap: () {
                Navigator.of(context).pop();
                unawaited(
                  _pickAttachment(
                    source: ImageSource.gallery,
                    kind: "screenshot",
                    note: "Capture ajoutee a la creation du ticket",
                  ),
                );
              },
            ),
            ListTile(
              leading: const Icon(Icons.receipt_long_outlined),
              title: const Text("Photographier un recu"),
              subtitle: const Text("Camera mobile"),
              onTap: () {
                Navigator.of(context).pop();
                unawaited(
                  _pickAttachment(
                    source: ImageSource.camera,
                    kind: "receipt",
                    note: "Recu ajoute a la creation du ticket",
                  ),
                );
              },
            ),
            ListTile(
              leading: const Icon(Icons.verified_outlined),
              title: const Text("Ajouter une preuve"),
              subtitle: const Text("Photo du produit ou de l'incident"),
              onTap: () {
                Navigator.of(context).pop();
                unawaited(
                  _pickAttachment(
                    source: ImageSource.gallery,
                    kind: "proof",
                    note: "Preuve ajoutee a la creation du ticket",
                  ),
                );
              },
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _save() async {
    if (_titleController.text.trim().isEmpty || _descriptionController.text.trim().isEmpty) return;
    setState(() => _saving = true);
    try {
      final payload = <String, dynamic>{
        "client": _selectedClientId ?? widget.session.userId,
        "product": _selectedProductId,
        "related_transaction": _selectedTransactionId,
        "title": _titleController.text.trim(),
        "description": _descriptionController.text.trim(),
        "category": _category,
        "channel": "web",
        "priority": _priority,
      };
      if (widget.session.isInternal) {
        payload["suspected_fraud"] = _suspectedFraud;
      }
      final createdTicket = await widget.session.api.post("tickets/", payload);
      final ticketId = createdTicket["id"] as int?;
      if (ticketId != null) {
        for (final attachment in _draftAttachments) {
          await widget.session.api.postMultipart(
            "ticket-attachments/",
            fields: {
              "ticket": ticketId.toString(),
              "kind": attachment.kind,
              "note": attachment.note,
            },
            filePath: attachment.file.path,
            filename: attachment.file.name,
          );
        }
      }
      if (!mounted) return;
      Navigator.of(context).pop(true);
    } catch (exc) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(exc.toString())));
    } finally {
      if (mounted) {
        setState(() => _saving = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text("Nouveau ticket")),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              padding: const EdgeInsets.all(20),
              children: [
                if (widget.session.isInternal)
                  DropdownButtonFormField<int>(
                    initialValue: _selectedClientId,
                    decoration: const InputDecoration(labelText: "Client"),
                    items: _users
                        .map((user) => DropdownMenuItem<int>(
                              value: user["id"] as int,
                              child: Text((user["username"] ?? "").toString()),
                            ))
                        .toList(),
                    onChanged: (value) {
                      setState(() {
                        _selectedClientId = value;
                        final products = _visibleProducts();
                        final transactions = _visibleTransactions();
                        _selectedProductId = products.isNotEmpty ? products.first["id"] as int : null;
                        _selectedTransactionId = transactions.isNotEmpty ? transactions.first["id"] as int : null;
                      });
                    },
                  ),
                const SizedBox(height: 14),
                DropdownButtonFormField<int?>(
                  initialValue: _selectedProductId,
                  decoration: const InputDecoration(labelText: "Produit"),
                  items: _visibleProducts()
                      .map((product) => DropdownMenuItem<int?>(
                            value: product["id"] as int,
                            child: Text("${product["name"]} · ${product["serial_number"]}"),
                          ))
                      .toList(),
                  onChanged: (value) => setState(() => _selectedProductId = value),
                ),
                const SizedBox(height: 14),
                DropdownButtonFormField<int?>(
                  initialValue: _selectedTransactionId,
                  decoration: const InputDecoration(labelText: "Transaction liee"),
                  items: [
                    const DropdownMenuItem<int?>(value: null, child: Text("Aucune")),
                    ..._visibleTransactions().map(
                      (item) => DropdownMenuItem<int?>(
                        value: item["id"] as int,
                        child: Text(
                          "${item["external_reference"] ?? item["provider_reference"] ?? "Transaction"} · ${item["amount"] ?? "0"} ${item["currency"] ?? "XAF"}",
                        ),
                      ),
                    ),
                  ],
                  onChanged: (value) => setState(() => _selectedTransactionId = value),
                ),
                const SizedBox(height: 14),
                TextField(controller: _titleController, decoration: const InputDecoration(labelText: "Titre")),
                const SizedBox(height: 14),
                TextField(
                  controller: _descriptionController,
                  minLines: 4,
                  maxLines: 6,
                  decoration: const InputDecoration(labelText: "Description"),
                ),
                const SizedBox(height: 14),
                DropdownButtonFormField<String>(
                  initialValue: _category,
                  decoration: const InputDecoration(labelText: "Categorie"),
                  items: const [
                    DropdownMenuItem(value: "breakdown", child: Text("Panne")),
                    DropdownMenuItem(value: "installation", child: Text("Installation")),
                    DropdownMenuItem(value: "maintenance", child: Text("Maintenance")),
                    DropdownMenuItem(value: "return", child: Text("Retour")),
                    DropdownMenuItem(value: "refund", child: Text("Remboursement")),
                    DropdownMenuItem(value: "payment", child: Text("Paiement")),
                    DropdownMenuItem(value: "withdrawal", child: Text("Retrait")),
                    DropdownMenuItem(value: "bug", child: Text("Bug")),
                    DropdownMenuItem(value: "account", child: Text("Compte")),
                    DropdownMenuItem(value: "complaint", child: Text("Reclamation")),
                  ],
                  onChanged: (value) => setState(() => _category = value ?? "breakdown"),
                ),
                const SizedBox(height: 14),
                DropdownButtonFormField<String>(
                  initialValue: _priority,
                  decoration: const InputDecoration(labelText: "Priorite"),
                  items: const [
                    DropdownMenuItem(value: "low", child: Text("Faible")),
                    DropdownMenuItem(value: "normal", child: Text("Normale")),
                    DropdownMenuItem(value: "high", child: Text("Haute")),
                    DropdownMenuItem(value: "critical", child: Text("Critique")),
                  ],
                  onChanged: (value) => setState(() => _priority = value ?? "normal"),
                ),
                const SizedBox(height: 14),
                Card(
                  margin: EdgeInsets.zero,
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            Expanded(
                              child: Text(
                                "Preuves / captures / recus",
                                style: Theme.of(context)
                                    .textTheme
                                    .titleMedium
                                    ?.copyWith(fontWeight: FontWeight.w700),
                              ),
                            ),
                            TextButton.icon(
                              onPressed: _saving ? null : _showAttachmentOptions,
                              icon: const Icon(Icons.attach_file),
                              label: const Text("Ajouter"),
                            ),
                          ],
                        ),
                        const SizedBox(height: 8),
                        if (_draftAttachments.isEmpty)
                          const Text("Aucune piece jointe. Vous pourrez aussi en ajouter plus tard depuis le detail ticket."),
                        ..._draftAttachments.asMap().entries.map(
                          (entry) => Padding(
                            padding: const EdgeInsets.only(bottom: 8),
                            child: Row(
                              children: [
                                Expanded(
                                  child: _LineItem(
                                    entry.value.file.name,
                                    "${entry.value.kind} · ${entry.value.note}",
                                  ),
                                ),
                                IconButton(
                                  icon: const Icon(Icons.close),
                                  onPressed: _saving
                                      ? null
                                      : () {
                                          setState(() {
                                            _draftAttachments = _draftAttachments
                                                .where((attachment) => attachment != entry.value)
                                                .toList();
                                          });
                                        },
                                ),
                              ],
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
                if (widget.session.isInternal) ...[
                  const SizedBox(height: 14),
                  SwitchListTile(
                    value: _suspectedFraud,
                    contentPadding: EdgeInsets.zero,
                    title: const Text("Fraude suspectee"),
                    subtitle: const Text("Active un suivi renforce sur ce dossier."),
                    onChanged: (value) => setState(() => _suspectedFraud = value),
                  ),
                ],
                const SizedBox(height: 22),
                FilledButton(
                  onPressed: _saving ? null : _save,
                  child: _saving ? const CircularProgressIndicator() : const Text("Creer le ticket"),
                ),
              ],
            ),
    );
  }
}

class ProductsScreen extends StatefulWidget {
  const ProductsScreen({super.key, required this.session});

  final SavSession session;

  @override
  State<ProductsScreen> createState() => _ProductsScreenState();
}

class _ProductsScreenState extends State<ProductsScreen> {
  late Future<List<Map<String, dynamic>>> _future;

  @override
  void initState() {
    super.initState();
    _future = widget.session.api.getList("products/");
  }

  Future<void> _refresh() async {
    setState(() => _future = widget.session.api.getList("products/"));
    await _future;
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<List<Map<String, dynamic>>>(
      future: _future,
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done) {
          return const Center(child: CircularProgressIndicator());
        }
        if (snapshot.hasError) {
          return _ErrorView(message: snapshot.error.toString(), onRetry: _refresh);
        }

        final products = snapshot.data ?? <Map<String, dynamic>>[];
        return RefreshIndicator(
          onRefresh: _refresh,
          child: ListView(
            padding: const EdgeInsets.all(20),
            children: products
                .map(
                  (product) => Padding(
                    padding: const EdgeInsets.only(bottom: 12),
                    child: Card(
                      child: ListTile(
                        title: Text((product["name"] ?? "").toString()),
                        subtitle: Text("${product["serial_number"]} · ${product["client_name"] ?? ""}"),
                        trailing: Text("Sante ${product["health_score"]}"),
                        onTap: () => Navigator.of(context).push(
                          MaterialPageRoute<void>(
                            builder: (_) => ProductDetailPage(session: widget.session, product: product),
                          ),
                        ),
                      ),
                    ),
                  ),
                )
                .toList(),
          ),
        );
      },
    );
  }
}

class ProductDetailPage extends StatefulWidget {
  const ProductDetailPage({super.key, required this.session, required this.product});

  final SavSession session;
  final Map<String, dynamic> product;

  @override
  State<ProductDetailPage> createState() => _ProductDetailPageState();
}

class _ProductDetailPageState extends State<ProductDetailPage> {
  late Future<Map<String, dynamic>> _future;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<Map<String, dynamic>> _load() async {
    final alerts = await widget.session.api.getList("predictive-alerts/");
    final tickets = await widget.session.api.getList("tickets/");
    return {
      "alerts": alerts.where((item) => item["product"] == widget.product["id"]).toList(),
      "tickets": tickets.where((item) => item["product"] == widget.product["id"]).toList(),
    };
  }

  Future<void> _runPredictive() async {
    setState(() => _busy = true);
    try {
      await widget.session.api.post("products/${widget.product["id"]}/predictive_analysis/", {});
      await _refresh();
    } catch (exc) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(exc.toString())));
    } finally {
      if (mounted) {
        setState(() => _busy = false);
      }
    }
  }

  Future<void> _refresh() async {
    setState(() => _future = _load());
    await _future;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text((widget.product["name"] ?? "").toString())),
      body: FutureBuilder<Map<String, dynamic>>(
        future: _future,
        builder: (context, snapshot) {
          if (snapshot.connectionState != ConnectionState.done) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snapshot.hasError) {
            return _ErrorView(message: snapshot.error.toString(), onRetry: _refresh);
          }

          final alerts = (snapshot.data?["alerts"] as List<dynamic>? ?? []).cast<Map<String, dynamic>>();
          final tickets = (snapshot.data?["tickets"] as List<dynamic>? ?? []).cast<Map<String, dynamic>>();

          return ListView(
            padding: const EdgeInsets.all(20),
            children: [
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(20),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text((widget.product["serial_number"] ?? "").toString()),
                      const SizedBox(height: 8),
                      Text("Sante ${widget.product["health_score"]}/100", style: Theme.of(context).textTheme.titleLarge),
                      const SizedBox(height: 8),
                      Text("Garantie jusqu'au ${widget.product["warranty_end"] ?? "N/A"}"),
                      if (widget.session.isInternal) ...[
                        const SizedBox(height: 16),
                        FilledButton.icon(
                          onPressed: _busy ? null : _runPredictive,
                          icon: const Icon(Icons.sensors),
                          label: const Text("Analyse predictive"),
                        ),
                      ],
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 16),
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(20),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text("Alertes", style: Theme.of(context).textTheme.titleLarge),
                      const SizedBox(height: 12),
                      ...alerts.map((alert) => _LineItem((alert["title"] ?? "").toString(), (alert["severity"] ?? "").toString())),
                      if (alerts.isEmpty) const Text("Aucune alerte predictive."),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 16),
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(20),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text("Tickets lies", style: Theme.of(context).textTheme.titleLarge),
                      const SizedBox(height: 12),
                      ...tickets.map((ticket) => _LineItem((ticket["reference"] ?? "").toString(), (ticket["title"] ?? "").toString())),
                      if (tickets.isEmpty) const Text("Aucun ticket rattache."),
                    ],
                  ),
                ),
              ),
            ],
          );
        },
      ),
    );
  }
}

class KnowledgeScreen extends StatefulWidget {
  const KnowledgeScreen({super.key, required this.session});

  final SavSession session;

  @override
  State<KnowledgeScreen> createState() => _KnowledgeScreenState();
}

class OffersScreen extends StatefulWidget {
  const OffersScreen({super.key, required this.session});

  final SavSession session;

  @override
  State<OffersScreen> createState() => _OffersScreenState();
}

class _OffersScreenState extends State<OffersScreen> {
  late Future<List<Map<String, dynamic>>> _future;

  @override
  void initState() {
    super.initState();
    _future = widget.session.api.getList("offers/");
  }

  Future<void> _refresh() async {
    setState(() => _future = widget.session.api.getList("offers/"));
    await _future;
  }

  Future<void> _updateOffer(int id, String decision) async {
    await widget.session.api.post("offers/$id/$decision/", {});
    await _refresh();
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<List<Map<String, dynamic>>>(
      future: _future,
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done) {
          return const Center(child: CircularProgressIndicator());
        }
        if (snapshot.hasError) {
          return _ErrorView(message: snapshot.error.toString(), onRetry: _refresh);
        }

        final offers = snapshot.data ?? <Map<String, dynamic>>[];
        return RefreshIndicator(
          onRefresh: _refresh,
          child: ListView(
            padding: const EdgeInsets.all(20),
            children: [
              if (offers.isEmpty)
                const Card(
                  child: Padding(
                    padding: EdgeInsets.all(24),
                    child: Text("Aucune offre disponible pour le perimetre courant."),
                  ),
                ),
              ...offers.map(
                (offer) => Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: Card(
                    child: Padding(
                      padding: const EdgeInsets.all(18),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Wrap(
                            spacing: 10,
                            runSpacing: 10,
                            crossAxisAlignment: WrapCrossAlignment.center,
                            children: [
                              Text(
                                (offer["title"] ?? "").toString(),
                                style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700),
                              ),
                              _StateChip(label: (offer["status"] ?? "proposed").toString()),
                            ],
                          ),
                          const SizedBox(height: 8),
                          Text((offer["description"] ?? "").toString()),
                          const SizedBox(height: 10),
                          _LineItem("Client", (offer["client_name"] ?? "").toString()),
                          _LineItem("Produit", (offer["product_name"] ?? "N/A").toString()),
                          _LineItem("Prix", "${offer["price"] ?? "0"} FCFA"),
                          if ((offer["rationale"] ?? "").toString().isNotEmpty)
                            Padding(
                              padding: const EdgeInsets.only(top: 8),
                              child: Text(
                                (offer["rationale"] ?? "").toString(),
                                style: const TextStyle(color: Colors.black54),
                              ),
                            ),
                          if (!widget.session.isInternal && offer["status"] == "proposed") ...[
                            const SizedBox(height: 14),
                            Row(
                              children: [
                                Expanded(
                                  child: FilledButton(
                                    onPressed: () => _updateOffer(offer["id"] as int, "accept"),
                                    child: const Text("Accepter"),
                                  ),
                                ),
                                const SizedBox(width: 12),
                                Expanded(
                                  child: OutlinedButton(
                                    onPressed: () => _updateOffer(offer["id"] as int, "reject"),
                                    child: const Text("Refuser"),
                                  ),
                                ),
                              ],
                            ),
                          ],
                        ],
                      ),
                    ),
                  ),
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}

class _KnowledgeScreenState extends State<KnowledgeScreen> {
  late Future<List<Map<String, dynamic>>> _future;

  @override
  void initState() {
    super.initState();
    _future = widget.session.api.getList("knowledge-articles/");
  }

  Future<void> _refresh() async {
    setState(() => _future = widget.session.api.getList("knowledge-articles/"));
    await _future;
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<List<Map<String, dynamic>>>(
      future: _future,
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done) {
          return const Center(child: CircularProgressIndicator());
        }
        if (snapshot.hasError) {
          return _ErrorView(message: snapshot.error.toString(), onRetry: _refresh);
        }

        final articles = snapshot.data ?? <Map<String, dynamic>>[];
        return RefreshIndicator(
          onRefresh: _refresh,
          child: ListView(
            padding: const EdgeInsets.all(20),
            children: articles
                .map(
                  (article) => Padding(
                    padding: const EdgeInsets.only(bottom: 12),
                    child: Card(
                      child: ListTile(
                        title: Text((article["title"] ?? "").toString()),
                        subtitle: Text((article["summary"] ?? article["category"] ?? "").toString()),
                        onTap: () => Navigator.of(context).push(
                          MaterialPageRoute<void>(
                            builder: (_) => KnowledgeDetailPage(article: article),
                          ),
                        ),
                      ),
                    ),
                  ),
                )
                .toList(),
          ),
        );
      },
    );
  }
}

class KnowledgeDetailPage extends StatelessWidget {
  const KnowledgeDetailPage({super.key, required this.article});

  final Map<String, dynamic> article;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text((article["title"] ?? "").toString())),
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          Card(
            child: Padding(
              padding: const EdgeInsets.all(20),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text((article["title"] ?? "").toString(), style: Theme.of(context).textTheme.headlineSmall),
                  const SizedBox(height: 10),
                  Text((article["summary"] ?? "").toString()),
                  const SizedBox(height: 20),
                  Text((article["content"] ?? "").toString()),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class NotificationsScreen extends StatefulWidget {
  const NotificationsScreen({super.key, required this.session});

  final SavSession session;

  @override
  State<NotificationsScreen> createState() => _NotificationsScreenState();
}

class _NotificationsScreenState extends State<NotificationsScreen> {
  late Future<List<Map<String, dynamic>>> _future;

  @override
  void initState() {
    super.initState();
    _future = widget.session.api.getList("notifications/");
  }

  Future<void> _refresh() async {
    setState(() => _future = widget.session.api.getList("notifications/"));
    await _future;
  }

  Future<void> _markRead(int id) async {
    await widget.session.api.post("notifications/$id/mark_read/", {});
    await _refresh();
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<List<Map<String, dynamic>>>(
      future: _future,
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done) {
          return const Center(child: CircularProgressIndicator());
        }
        if (snapshot.hasError) {
          return _ErrorView(message: snapshot.error.toString(), onRetry: _refresh);
        }

        final notifications = snapshot.data ?? <Map<String, dynamic>>[];
        return RefreshIndicator(
          onRefresh: _refresh,
          child: ListView(
            padding: const EdgeInsets.all(20),
            children: notifications
                .map(
                  (item) => Padding(
                    padding: const EdgeInsets.only(bottom: 12),
                    child: Card(
                      child: ListTile(
                        title: Text((item["subject"] ?? "").toString()),
                        subtitle: Text((item["message"] ?? "").toString()),
                        trailing: item["status"] == "read"
                            ? const Icon(Icons.done_all, color: Colors.green)
                            : TextButton(
                                onPressed: () => _markRead(item["id"] as int),
                                child: const Text("Lu"),
                              ),
                      ),
                    ),
                  ),
                )
                .toList(),
          ),
        );
      },
    );
  }
}

class AnalyticsSheet extends StatefulWidget {
  const AnalyticsSheet({super.key, required this.session});

  final SavSession session;

  @override
  State<AnalyticsSheet> createState() => _AnalyticsSheetState();
}

class _AnalyticsSheetState extends State<AnalyticsSheet> {
  final TextEditingController _controller = TextEditingController(text: "Combien de tickets critiques avons-nous ?");
  bool _loading = false;
  Map<String, dynamic>? _result;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    setState(() => _loading = true);
    try {
      final result = await widget.session.api.post("analytics/ask/", {"question": _controller.text.trim()});
      if (!mounted) return;
      setState(() => _result = result);
    } catch (exc) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(exc.toString())));
    } finally {
      if (mounted) {
        setState(() => _loading = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(
        left: 20,
        right: 20,
        top: 12,
        bottom: MediaQuery.of(context).viewInsets.bottom + 24,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text("BI conversationnelle", style: Theme.of(context).textTheme.headlineSmall),
          const SizedBox(height: 12),
          TextField(
            controller: _controller,
            minLines: 2,
            maxLines: 4,
            decoration: const InputDecoration(hintText: "Posez une question metier au SAV"),
          ),
          const SizedBox(height: 12),
          FilledButton(onPressed: _loading ? null : _submit, child: const Text("Analyser")),
          if (_result != null) ...[
            const SizedBox(height: 14),
            Text((_result!["answer"] ?? "").toString(), style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 10),
            Text((_result!["data"] ?? {}).toString()),
            if ((_result!["highlights"] as List<dynamic>? ?? []).isNotEmpty) ...[
              const SizedBox(height: 12),
              ...((_result!["highlights"] as List<dynamic>).map(
                (item) => Padding(
                  padding: const EdgeInsets.only(bottom: 6),
                  child: Text("• ${item.toString()}"),
                ),
              )),
            ],
          ],
        ],
      ),
    );
  }
}

class _ProcessStep extends StatelessWidget {
  const _ProcessStep({
    required this.title,
    required this.subtitle,
    required this.isDone,
    this.isLast = false,
  });

  final String title;
  final String subtitle;
  final bool isDone;
  final bool isLast;

  @override
  Widget build(BuildContext context) {
    final activeColor = Theme.of(context).colorScheme.primary;
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Column(
          children: [
            Container(
              width: 18,
              height: 18,
              decoration: BoxDecoration(
                color: isDone ? activeColor : Colors.transparent,
                borderRadius: BorderRadius.circular(999),
                border: Border.all(color: activeColor, width: 2),
              ),
              child: isDone
                  ? const Icon(Icons.check, size: 12, color: Colors.white)
                  : null,
            ),
            if (!isLast)
              Container(
                width: 2,
                height: 34,
                color: activeColor.withValues(alpha: 0.35),
              ),
          ],
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Padding(
            padding: const EdgeInsets.only(bottom: 14),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: const TextStyle(fontWeight: FontWeight.w700)),
                const SizedBox(height: 4),
                Text(subtitle, style: const TextStyle(color: Colors.black54)),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

class _HeroPanel extends StatelessWidget {
  const _HeroPanel({required this.title, required this.subtitle});

  final String title;
  final String subtitle;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(30),
        gradient: const LinearGradient(
          colors: [Color(0xFFD5671D), Color(0xFFF4B45B)],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: Theme.of(context).textTheme.headlineSmall?.copyWith(color: Colors.white, fontWeight: FontWeight.w700)),
          const SizedBox(height: 10),
          Text(subtitle, style: Theme.of(context).textTheme.bodyLarge?.copyWith(color: Colors.white.withValues(alpha: 0.92), height: 1.5)),
        ],
      ),
    );
  }
}

class _MetricCard extends StatelessWidget {
  const _MetricCard({required this.label, required this.value, required this.icon});

  final String label;
  final String value;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(icon),
            const SizedBox(height: 12),
            Text(value, style: Theme.of(context).textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w700)),
            const SizedBox(height: 4),
            Text(label, style: const TextStyle(color: Colors.black54)),
          ],
        ),
      ),
    );
  }
}

class _StateChip extends StatelessWidget {
  const _StateChip({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    final lowered = label.toLowerCase();
    final color = lowered.contains("critical") || lowered.contains("failed")
        ? const Color(0xFFA33728)
        : lowered.contains("high") || lowered.contains("warning") || lowered.contains("progress")
            ? const Color(0xFFBE7C17)
            : lowered.contains("resolved") || lowered.contains("read")
                ? const Color(0xFF2F7A55)
                : const Color(0xFF1C7A6A);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(label, style: TextStyle(color: color, fontWeight: FontWeight.w600)),
    );
  }
}

class _LineItem extends StatelessWidget {
  const _LineItem(this.label, this.value);

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(child: Text(label, style: const TextStyle(fontWeight: FontWeight.w600))),
          const SizedBox(width: 16),
          Expanded(child: Text(value, textAlign: TextAlign.right)),
        ],
      ),
    );
  }
}

class _LabeledField extends StatelessWidget {
  const _LabeledField({required this.label, required this.child});

  final String label;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: Theme.of(context).textTheme.labelLarge),
        const SizedBox(height: 8),
        child,
      ],
    );
  }
}

class _ErrorView extends StatelessWidget {
  const _ErrorView({required this.message, required this.onRetry});

  final String message;
  final Future<void> Function() onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.error_outline, size: 42, color: Color(0xFFA33728)),
            const SizedBox(height: 12),
            Text(message, textAlign: TextAlign.center),
            const SizedBox(height: 12),
            FilledButton(onPressed: onRetry, child: const Text("Reessayer")),
          ],
        ),
      ),
    );
  }
}
