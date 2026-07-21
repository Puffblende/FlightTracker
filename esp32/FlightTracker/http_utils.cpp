#include "http_utils.h"
#include <WiFi.h>
#include <WiFiClient.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>

bool ensureWiFi(const char* tag) {
    if (WiFi.status() == WL_CONNECTED) return true;
    Serial.println("[WiFi] Disconnected, reconnecting...");
    WiFi.reconnect();
    delay(3000);
    if (WiFi.status() == WL_CONNECTED) return true;
    Serial.printf("[%s] WiFi reconnect failed\n", tag);
    return false;
}

int fetchUrlPlain(const char* url, String& result) {
    if (!ensureWiFi("HTTP")) return -1;

    WiFiClient* client = new WiFiClient;
    if (!client) { Serial.println("[HTTP] client alloc failed"); return -1; }

    HTTPClient http;
    http.begin(*client, url);
    http.useHTTP10(true);
    http.setTimeout(10000);
    http.addHeader("User-Agent", "FlightTracker/1.0");

    int code = http.GET();
    if (code < 0)
        Serial.printf("[HTTP] Error: %s\n", http.errorToString(code).c_str());
    else
        Serial.printf("[HTTP] %d %s\n", code, url);

    if (code == 200)
        result = http.getString();

    http.end();
    // http.end() already stops the client, but the heap-allocated WiFiClient's
    // own destructor (below) redundantly tears down the same lwIP socket —
    // without this stop()+delay(), that second teardown can race the first
    // and free an already-freed pbuf ("assert failed: pbuf_free ... p->ref > 0").
    client->stop();
    delay(10);
    delete client;
    return code;
}

// ---------------------------------------------------------------------------
// Shared response reader for raw TCP/SSL WiFiClient connections.
// Waits for the first byte, parses status code, skips headers, reads body.
// Returns HTTP status code, or -1 on timeout.
// ---------------------------------------------------------------------------
int readHttpResponse(WiFiClient& conn, String& result) {
    unsigned long t0 = millis();
    while (conn.available() == 0) {
        if (millis() - t0 > 10000) { Serial.println("[HTTP] Response timeout"); return -1; }
        delay(10);
    }

    String statusLine = conn.readStringUntil('\n');
    Serial.printf("[HTTP] Status: %s\n", statusLine.c_str());
    int code = (statusLine.length() > 9) ? statusLine.substring(9, 12).toInt() : 0;

    while (conn.connected() || conn.available()) {
        String line = conn.readStringUntil('\n');
        if (line == "\r" || line.length() == 0) break;
    }

    if (code != 200) return code;

    result = "";
    result.reserve(16384);
    while (conn.connected() || conn.available()) {
        if (conn.available()) result += (char)conn.read();
    }
    Serial.printf("[HTTP] Body: %d bytes\n", result.length());
    return 200;
}

int fetchHTTPS(const char* host, const char* path, String& result) {
    if (!ensureWiFi("SSL")) return -1;

    IPAddress ip;
    if (!WiFi.hostByName(host, ip)) {
        Serial.printf("[DNS] Failed to resolve: %s\n", host);
        return -1;
    }
    Serial.printf("[DNS] %s = %s\n", host, ip.toString().c_str());

    // HTTP/1.0 request shared by both attempts — avoids chunked encoding
    String req = String("GET ") + path + " HTTP/1.0\r\n"
               + "Host: " + host + "\r\n"
               + "User-Agent: FlightTracker/1.0\r\n"
               + "Accept: application/json\r\n"
               + "Connection: close\r\n\r\n";

    // ── Attempt 1: plain HTTP on port 80 ─────────────────────────────────────
    {
        WiFiClient plainClient;
        Serial.printf("[HTTP] Trying %s:80\n", ip.toString().c_str());
        if (plainClient.connect(ip, 80)) {
            plainClient.print(req);
            int code = readHttpResponse(plainClient, result);
            plainClient.stop();
            delay(10);
            if (code == 200) {
                Serial.println("[HTTP] Plain HTTP worked!");
                return 200;
            }
            Serial.printf("[HTTP] Port 80 returned %d\n", code);
        } else {
            Serial.println("[HTTP] Port 80 connect failed");
        }
    }

    // ── Attempt 2: HTTPS on port 443 ─────────────────────────────────────────
    {
        WiFiClientSecure sslClient;
        sslClient.setInsecure();
        sslClient.setHandshakeTimeout(30);  // seconds
        Serial.printf("[SSL] Trying %s:443\n", ip.toString().c_str());
        if (!sslClient.connect(ip, 443)) {
            Serial.printf("[SSL] Connect failed to %s (%s)\n", host, ip.toString().c_str());
            return -1;
        }
        sslClient.print(req);
        int code = readHttpResponse(sslClient, result);
        sslClient.stop();
        delay(10);
        return code;
    }
}

int fetchUrl(const char* url, String& result,
             const char* user, const char* pass) {
    if (!ensureWiFi("HTTP")) return -1;

    // Heap-allocate the TLS client so its buffers come from PSRAM (when
    // enabled) rather than from the limited stack.  Stack-allocated
    // WiFiClientSecure can exhaust the stack or fail to negotiate TLS
    // when PSRAM changes the memory layout.
    WiFiClientSecure* client = new WiFiClientSecure;
    if (!client) {
        Serial.println("[HTTP] client alloc failed");
        return -1;
    }
    client->setInsecure();
    client->setHandshakeTimeout(30);  // seconds

    HTTPClient http;
    http.begin(*client, url);
    http.useHTTP10(true);           // disable chunked transfer; getString() works reliably
    http.setTimeout(10000);
    http.addHeader("User-Agent", "FlightTracker/1.0");

    if (user && user[0])
        http.setAuthorization(user, pass ? pass : "");

    int code = http.GET();
    if (code < 0)
        Serial.printf("[HTTP] Error: %s\n", http.errorToString(code).c_str());
    else
        Serial.printf("[HTTP] %d %s\n", code, url);

    if (code == 200)
        result = http.getString();

    http.end();
    // See fetchUrlPlain() above: stop the client explicitly (and let lwIP
    // settle) before its destructor runs, to avoid a double pbuf free.
    client->stop();
    delay(10);
    delete client;
    return code;
}
