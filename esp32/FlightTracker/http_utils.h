#pragma once
#ifndef FT_HTTP_UTILS_H
#define FT_HTTP_UTILS_H

#include <Arduino.h>
#include <WiFiClient.h>

// Verify WiFi is connected; attempt one reconnect with a 3-second wait if not.
// Returns true if connected after the check.
bool ensureWiFi(const char* tag);

// HTTPS GET using a heap-allocated WiFiClientSecure (avoids stack overflow
// with PSRAM enabled).  Returns the HTTP status code; `result` is populated
// only when the return value is 200.  Negative return codes are connection
// errors — pass them to HTTPClient::errorToString() for a readable message.
// Optional user/pass enables HTTP Basic Auth.
int fetchUrl(const char* url, String& result,
             const char* user = nullptr, const char* pass = nullptr);

// Plain HTTP GET (no TLS) — for diagnostic testing or APIs that don't
// support HTTPS.  Same return-value contract as fetchUrl().
int fetchUrlPlain(const char* url, String& result);

// Raw TLS GET using a stack-allocated WiFiClientSecure and manual HTTP/1.1
// framing — bypasses HTTPClient entirely.  Use when HTTPClient's SSL
// negotiation fails with "connection refused" on ESP32-S3 + PSRAM.
// Returns HTTP status code; result is populated only on 200.
int fetchHTTPS(const char* host, const char* path, String& result);

// Read an HTTP/1.0 response from an already-open WiFiClient (plain or SSL).
// Waits for the first byte, parses the status line, skips headers, reads body.
// Returns HTTP status code, or -1 on timeout.  result is populated on 200.
int readHttpResponse(WiFiClient& conn, String& result);

#endif // FT_HTTP_UTILS_H
