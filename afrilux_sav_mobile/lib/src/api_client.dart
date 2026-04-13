import 'dart:convert';
import 'dart:io';

class ApiException implements Exception {
  const ApiException(this.statusCode, this.message);

  final int statusCode;
  final String message;

  @override
  String toString() => "ApiException($statusCode): $message";
}

class SavApiClient {
  SavApiClient({required this.baseUrl});

  final String baseUrl;
  String? _accessToken;
  String? _refreshToken;

  Future<void> authenticate({
    required String identifier,
    required String password,
  }) async {
    final payload = await _requestRaw(
      "POST",
      "token/",
      body: {
        "username": identifier.trim(),
        "password": password,
      },
      authenticated: false,
      allowRefresh: false,
    );
    final tokens = Map<String, dynamic>.from(payload as Map);
    final accessToken = (tokens["access"] ?? "").toString();
    final refreshToken = (tokens["refresh"] ?? "").toString();
    if (accessToken.isEmpty || refreshToken.isEmpty) {
      throw const ApiException(500, "Impossible d'ouvrir une session JWT.");
    }
    _accessToken = accessToken;
    _refreshToken = refreshToken;
  }

  void clearTokens() {
    _accessToken = null;
    _refreshToken = null;
  }

  Future<Map<String, dynamic>> getMap(String path) async {
    final dynamic data = await _request("GET", path);
    return Map<String, dynamic>.from(data as Map);
  }

  Future<List<Map<String, dynamic>>> getList(String path) async {
    final dynamic data = await _request("GET", path);
    final list = data as List<dynamic>;
    return list.map((item) => Map<String, dynamic>.from(item as Map)).toList();
  }

  Future<Map<String, dynamic>> post(String path, Map<String, dynamic> body) async {
    final dynamic data = await _request("POST", path, body: body);
    return Map<String, dynamic>.from(data as Map);
  }

  Future<Map<String, dynamic>> patch(String path, Map<String, dynamic> body) async {
    final dynamic data = await _request("PATCH", path, body: body);
    return Map<String, dynamic>.from(data as Map);
  }

  Future<Map<String, dynamic>> postMultipart(
    String path, {
    required Map<String, String> fields,
    required String filePath,
    String fileField = "file",
    String? filename,
    String? contentType,
    bool allowRefresh = true,
  }) async {
    final client = HttpClient();
    final uri = Uri.parse("$baseUrl${normalizedPath(path)}");
    final request = await client.postUrl(uri);
    final boundary = "----afrilux-${DateTime.now().microsecondsSinceEpoch}";
    if ((_accessToken ?? "").isNotEmpty) {
      request.headers.set(HttpHeaders.authorizationHeader, "Bearer ${_accessToken!}");
    }
    request.headers.set(HttpHeaders.acceptHeader, "application/json");
    request.headers.set(HttpHeaders.contentTypeHeader, "multipart/form-data; boundary=$boundary");

    void writeText(String value) => request.add(utf8.encode(value));

    for (final entry in fields.entries) {
      writeText("--$boundary\r\n");
      writeText('Content-Disposition: form-data; name="${entry.key}"\r\n\r\n');
      writeText(entry.value);
      writeText("\r\n");
    }

    final file = File(filePath);
    final resolvedFilename = filename ?? file.uri.pathSegments.last;
    final resolvedContentType = contentType ?? _inferContentType(resolvedFilename);
    final fileBytes = await file.readAsBytes();

    writeText("--$boundary\r\n");
    writeText('Content-Disposition: form-data; name="$fileField"; filename="$resolvedFilename"\r\n');
    writeText("Content-Type: $resolvedContentType\r\n\r\n");
    request.add(fileBytes);
    writeText("\r\n--$boundary--\r\n");

    final response = await request.close();
    final responseText = await utf8.decoder.bind(response).join();
    client.close(force: true);
    final dynamic decoded = responseText.isEmpty ? <String, dynamic>{} : jsonDecode(responseText);
    if (response.statusCode == 401 && allowRefresh && (_refreshToken ?? "").isNotEmpty) {
      await _refreshAccessToken();
      return postMultipart(
        path,
        fields: fields,
        filePath: filePath,
        fileField: fileField,
        filename: filename,
        contentType: contentType,
        allowRefresh: false,
      );
    }
    if (response.statusCode >= 400) {
      throw ApiException(response.statusCode, _extractMessage(decoded));
    }
    return Map<String, dynamic>.from(decoded as Map);
  }

  String normalizedPath(String path) {
    final trimmed = path.startsWith("/") ? path.substring(1) : path;
    return trimmed;
  }

  Future<dynamic> _request(String method, String path, {Map<String, dynamic>? body}) async {
    return _requestRaw(method, path, body: body, authenticated: true, allowRefresh: true);
  }

  Future<dynamic> _requestRaw(
    String method,
    String path, {
    Map<String, dynamic>? body,
    required bool authenticated,
    required bool allowRefresh,
  }) async {
    final client = HttpClient();
    final uri = Uri.parse("$baseUrl${normalizedPath(path)}");
    final request = await client.openUrl(method, uri);
    request.headers.set(HttpHeaders.acceptHeader, "application/json");
    if (authenticated && (_accessToken ?? "").isNotEmpty) {
      request.headers.set(HttpHeaders.authorizationHeader, "Bearer ${_accessToken!}");
    }
    if (body != null) {
      request.headers.set(HttpHeaders.contentTypeHeader, "application/json");
      request.write(jsonEncode(body));
    }

    final response = await request.close();
    final responseText = await utf8.decoder.bind(response).join();
    client.close(force: true);
    final dynamic decoded = responseText.isEmpty ? <String, dynamic>{} : jsonDecode(responseText);

    final normalizedPathValue = normalizedPath(path);
    final canRefresh = authenticated &&
        allowRefresh &&
        response.statusCode == 401 &&
        (_refreshToken ?? "").isNotEmpty &&
        normalizedPathValue != "token/" &&
        normalizedPathValue != "token/refresh/";
    if (canRefresh) {
      await _refreshAccessToken();
      return _requestRaw(
        method,
        path,
        body: body,
        authenticated: authenticated,
        allowRefresh: false,
      );
    }

    if (response.statusCode >= 400) {
      throw ApiException(response.statusCode, _extractMessage(decoded));
    }

    return decoded;
  }

  Future<void> _refreshAccessToken() async {
    final refreshToken = (_refreshToken ?? "").trim();
    if (refreshToken.isEmpty) {
      clearTokens();
      throw const ApiException(401, "Session expiree. Reconnectez-vous.");
    }

    final payload = await _requestRaw(
      "POST",
      "token/refresh/",
      body: {"refresh": refreshToken},
      authenticated: false,
      allowRefresh: false,
    );
    final tokens = Map<String, dynamic>.from(payload as Map);
    final nextAccessToken = (tokens["access"] ?? "").toString();
    if (nextAccessToken.isEmpty) {
      clearTokens();
      throw const ApiException(401, "Session expiree. Reconnectez-vous.");
    }
    _accessToken = nextAccessToken;
    final nextRefreshToken = (tokens["refresh"] ?? "").toString();
    if (nextRefreshToken.isNotEmpty) {
      _refreshToken = nextRefreshToken;
    }
  }

  String _inferContentType(String filename) {
    final lower = filename.toLowerCase();
    if (lower.endsWith(".png")) {
      return "image/png";
    }
    if (lower.endsWith(".jpg") || lower.endsWith(".jpeg")) {
      return "image/jpeg";
    }
    if (lower.endsWith(".pdf")) {
      return "application/pdf";
    }
    return "application/octet-stream";
  }

  String _extractMessage(dynamic decoded) {
    if (decoded is Map && decoded["detail"] is String) {
      return decoded["detail"] as String;
    }
    return decoded.toString();
  }
}

class SavPublicApiClient {
  SavPublicApiClient({required this.baseUrl});

  final String baseUrl;

  Future<List<Map<String, dynamic>>> getList(String path) async {
    final dynamic data = await _request("GET", path);
    final list = data as List<dynamic>;
    return list.map((item) => Map<String, dynamic>.from(item as Map)).toList();
  }

  Future<Map<String, dynamic>> post(String path, Map<String, dynamic> body) async {
    final dynamic data = await _request("POST", path, body: body);
    return Map<String, dynamic>.from(data as Map);
  }

  Future<dynamic> _request(String method, String path, {Map<String, dynamic>? body}) async {
    final client = HttpClient();
    final trimmed = path.startsWith("/") ? path.substring(1) : path;
    final uri = Uri.parse("$baseUrl$trimmed");
    final request = await client.openUrl(method, uri);
    request.headers.set(HttpHeaders.acceptHeader, "application/json");
    if (body != null) {
      request.headers.set(HttpHeaders.contentTypeHeader, "application/json");
      request.write(jsonEncode(body));
    }

    final response = await request.close();
    final responseText = await utf8.decoder.bind(response).join();
    client.close(force: true);
    final dynamic decoded = responseText.isEmpty ? <String, dynamic>{} : jsonDecode(responseText);
    if (response.statusCode >= 400) {
      throw ApiException(response.statusCode, _extractMessage(decoded));
    }
    return decoded;
  }

  String _extractMessage(dynamic decoded) {
    if (decoded is Map && decoded["detail"] is String) {
      return decoded["detail"] as String;
    }
    return decoded.toString();
  }
}
