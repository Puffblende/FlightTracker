#include "provisioning.h"
#include "display.h"
#include "font.h"
#include "config.h"

#include <WiFi.h>
#include <WebServer.h>
#include <DNSServer.h>
#include <LittleFS.h>
#include <ArduinoJson.h>
#include <string.h>

#define WIFI_JSON_PATH "/wifi.json"
#define AP_SSID        "FlightTracker-Setup"

static const IPAddress AP_IP(192, 168, 4, 1);
static const IPAddress AP_MASK(255, 255, 255, 0);

static WebServer provServer(80);
static DNSServer dnsServer;
static volatile bool shouldRestart = false;

// ---------------------------------------------------------------------------
// Credential persistence
// ---------------------------------------------------------------------------

bool wifiCredsLoad(char* outSsid, int ssidLen, char* outPass, int passLen) {
    outSsid[0] = outPass[0] = '\0';
    if (!LittleFS.exists(WIFI_JSON_PATH)) return false;
    File f = LittleFS.open(WIFI_JSON_PATH, "r");
    if (!f) return false;

    DynamicJsonDocument doc(512);
    auto err = deserializeJson(doc, f);
    f.close();
    if (err) return false;

    const char* s = doc["ssid"] | "";
    const char* p = doc["pass"] | "";
    if (!s[0]) return false;

    strncpy(outSsid, s, ssidLen - 1);
    strncpy(outPass, p, passLen - 1);
    return true;
}

static bool wifiCredsSave(const char* ssid, const char* pass) {
    DynamicJsonDocument doc(512);
    doc["ssid"] = ssid;
    doc["pass"] = pass;
    File f = LittleFS.open(WIFI_JSON_PATH, "w");
    if (!f) {
        Serial.println("[WiFi] ERROR: cannot open wifi.json for write");
        return false;
    }
    serializeJson(doc, f);
    f.close();

    // Immediate read-back verify — confirms the write survived a crash/power loss
    char testSsid[64] = {0}, testPass[64] = {0};
    bool ok = wifiCredsLoad(testSsid, sizeof(testSsid), testPass, sizeof(testPass));
    Serial.printf("[WiFi] Credentials save verified=%d ssid='%s'\n", ok, testSsid);
    return ok;
}

void wifiCredsClear() {
    LittleFS.remove(WIFI_JSON_PATH);
}

// ---------------------------------------------------------------------------
// Provisioning display — 4 message lines + AP IP
// ---------------------------------------------------------------------------
static void showProvDisplay() {
    displayClear();

    auto ctr = [](const char* t) -> int {
        int w = fontTextWidth(t);
        return (TOTAL_WIDTH - w) / 2;
    };

    // Dim yellow header
    fontDrawText(ctr("Setup"), 2, "Setup", 100, 180, 255);

    fontDrawText(ctr("Connect to"), 12, "Connect to", 160, 160, 160);

    // Bright yellow AP name split across lines as requested
    fontDrawText(ctr("FlightTracker"), 22, "FlightTracker", 255, 220, 0);
    fontDrawText(ctr("-Setup"), 32, "-Setup", 255, 220, 0);

    // Faint green IP hint at bottom
    fontDrawText(ctr(AP_IP.toString().c_str()), 48,
                 AP_IP.toString().c_str(), 60, 200, 80);

    displayFlush();
}

// ---------------------------------------------------------------------------
// HTML helpers
// ---------------------------------------------------------------------------
static String htmlEscape(const String& s) {
    String o;
    o.reserve(s.length() + 8);
    for (char c : s) {
        if      (c == '&')  o += "&amp;";
        else if (c == '<')  o += "&lt;";
        else if (c == '>')  o += "&gt;";
        else if (c == '"')  o += "&quot;";
        else if (c == '\'') o += "&#39;";
        else                o += c;
    }
    return o;
}

// Build <option> elements from current WiFi scan results.
static String buildNetworkOptions() {
    int n = WiFi.scanComplete();
    if (n < 0) n = 0;

    String opts;
    if (n == 0) {
        opts = "<option disabled value=''>No networks found \xe2\x80\x94 press ↻ Scan</option>";
        return opts;
    }
    for (int i = 0; i < n; i++) {
        String ssid = htmlEscape(WiFi.SSID(i));
        bool   lock = WiFi.encryptionType(i) != WIFI_AUTH_OPEN;
        opts += "<option value=\"" + ssid + "\">";
        opts += ssid + " (" + String(WiFi.RSSI(i)) + "dBm" + (lock ? " \xf0\x9f\x94\x92" : "") + ")";
        opts += "</option>\n";
    }
    return opts;
}

// ---------------------------------------------------------------------------
// Setup page HTML — split at the <option> injection point
// ---------------------------------------------------------------------------
static const char HTML_HEAD[] = R"HTML(<!DOCTYPE html><html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">
<meta name="theme-color" content="#070d1a">
<title>FlightTracker Setup</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#070d1a;color:#e2e8f0;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:16px}
.card{background:#0f172a;border:1px solid #1e3a5f;border-radius:20px;padding:28px 24px;width:100%;max-width:400px;box-shadow:0 8px 40px rgba(37,99,235,.2)}
.hd{font-size:1.4rem;font-weight:700;color:#60a5fa;display:flex;align-items:center;gap:10px;margin-bottom:4px}
.sub{font-size:.85rem;color:#64748b;margin-bottom:20px}
hr{border:none;border-top:1px solid #1e3a5f;margin-bottom:20px}
.lbl{display:block;font-size:.72rem;font-weight:600;color:#94a3b8;text-transform:uppercase;letter-spacing:.08em;margin-bottom:7px}
.row{display:flex;gap:8px;align-items:flex-end;margin-bottom:16px}
.row .sel-wrap{flex:1}
select,input[type=password],input[type=text]{padding:12px 14px;background:#1e293b;border:1px solid #334155;border-radius:10px;color:#e2e8f0;font-size:.95rem;-webkit-appearance:none;appearance:none;outline:none;width:100%;display:block}
select:focus,input:focus{border-color:#3b82f6;box-shadow:0 0 0 3px rgba(59,130,246,.15)}
.scan{padding:12px 14px;background:#1e293b;border:1px solid #334155;border-radius:10px;color:#94a3b8;font-size:.9rem;cursor:pointer;white-space:nowrap;height:46px;line-height:1}
.scan:hover{border-color:#3b82f6;color:#60a5fa}
.pw-grp{position:relative;margin-bottom:20px}
.pw-grp input{padding-right:50px}
.eye{position:absolute;right:0;top:0;bottom:0;width:46px;background:none;border:none;cursor:pointer;color:#64748b;font-size:1.1rem;display:flex;align-items:center;justify-content:center}
.eye:hover{color:#94a3b8}
.go{width:100%;padding:13px;background:#2563eb;border:none;border-radius:10px;color:#fff;font-size:1rem;font-weight:600;cursor:pointer}
.go:hover{background:#1d4ed8}
.go:disabled{background:#1e3a5f;cursor:default}
.st{min-height:20px;text-align:center;font-size:.82rem;color:#f59e0b;margin-top:10px}
.note{font-size:.78rem;color:#475569;text-align:center;margin-top:12px}
</style></head>
<body><div class="card">
<div class="hd">
<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="#60a5fa" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 16.92v3a2 2 0 01-2.18 2 19.8 19.8 0 01-8.63-3.07A19.5 19.5 0 013.07 9.8 19.8 19.8 0 01.06 1.18 2 2 0 012 0h3a2 2 0 012 1.72 12.8 12.8 0 00.7 2.81 2 2 0 01-.45 2.11L6.09 7.91a16 16 0 006 6l1.27-1.27a2 2 0 012.11-.45 12.8 12.8 0 002.81.7A2 2 0 0122 14z"/></svg>
FlightTracker</div>
<div class="sub">WiFi Network Setup</div><hr>
<form id="f" method="POST" action="/connect">
<label class="lbl">Network</label>
<div class="row">
<div class="sel-wrap"><select name="ssid" id="net">
)HTML";

static const char HTML_TAIL[] = R"HTML(</select></div>
<button type="button" class="scan" id="sb" onclick="sc(this)" title="Scan for networks">&#8635; Scan</button>
</div>
<label class="lbl">Password</label>
<div class="pw-grp">
<input type="password" name="pass" id="pw" placeholder="WiFi password" autocomplete="current-password">
<button type="button" class="eye" onclick="tp()" title="Show/hide password">&#128065;</button>
</div>
<button type="submit" class="go" id="gb">Connect</button>
<div class="st" id="st"></div>
<div class="note">The device will restart and join your network.</div>
</form></div>
<script>
function tp(){var i=document.getElementById('pw');i.type=i.type==='password'?'text':'password';}
function sc(b){var t=b.textContent;b.textContent='…';b.disabled=true;
document.getElementById('st').textContent='Scanning…';
fetch('/scan').then(function(r){return r.json();}).then(function(d){
var s=document.getElementById('net'),c=s.value;s.innerHTML='';
if(!d.length){s.innerHTML='<option disabled>No networks found</option>';}
else{d.forEach(function(n){var o=document.createElement('option');o.value=n.ssid;
o.textContent=n.ssid+' ('+n.rssi+'dBm'+(n.secure?' 🔒':'')+')';
if(n.ssid===c)o.selected=true;s.appendChild(o);});}
document.getElementById('st').textContent=d.length+' network'+(d.length===1?'':'s')+' found';
}).catch(function(){document.getElementById('st').textContent='Scan failed — try again';
}).finally(function(){b.textContent=t;b.disabled=false;});}
document.getElementById('f').addEventListener('submit',function(e){
var v=document.getElementById('net').value;
if(!v||v===''){e.preventDefault();document.getElementById('st').textContent='Select a network first';return;}
document.getElementById('gb').disabled=true;
document.getElementById('st').textContent='Saving credentials, restarting…';});
</script></body></html>
)HTML";

// ---------------------------------------------------------------------------
// HTTP handlers (provisioning server)
// ---------------------------------------------------------------------------

static void serveSetupPage() {
    provServer.setContentLength(CONTENT_LENGTH_UNKNOWN);
    provServer.send(200, "text/html; charset=utf-8", "");
    provServer.sendContent(HTML_HEAD);
    provServer.sendContent(buildNetworkOptions());
    provServer.sendContent(HTML_TAIL);
}

static void handleProvRoot() {
    serveSetupPage();
}

static void handleScan() {
    // Blocking re-scan (~3 s) — called asynchronously from browser JS
    WiFi.scanDelete();
    int n = WiFi.scanNetworks(false, true);  // blocking, include hidden

    DynamicJsonDocument doc(4096);
    JsonArray arr = doc.to<JsonArray>();
    for (int i = 0; i < n; i++) {
        JsonObject o = arr.createNestedObject();
        o["ssid"]   = WiFi.SSID(i);
        o["rssi"]   = WiFi.RSSI(i);
        o["secure"] = WiFi.encryptionType(i) != WIFI_AUTH_OPEN;
    }
    String json;
    serializeJson(doc, json);
    provServer.send(200, "application/json", json);
}

static void handleConnect() {
    String ssid = provServer.arg("ssid");
    String pass = provServer.arg("pass");
    ssid.trim();

    if (ssid.isEmpty()) {
        provServer.send(400, "text/html",
            "<html><body style='font-family:sans-serif;padding:20px'>"
            "<h2 style='color:#f59e0b'>No network selected.</h2>"
            "<a href='/'>Go back</a></body></html>");
        return;
    }

    wifiCredsSave(ssid.c_str(), pass.c_str());

    provServer.send(200, "text/html",
        "<html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<style>body{font-family:-apple-system,sans-serif;background:#070d1a;"
        "color:#e2e8f0;display:flex;align-items:center;justify-content:center;"
        "min-height:100vh;padding:20px}.card{background:#0f172a;border:1px solid "
        "#1e3a5f;border-radius:20px;padding:28px;max-width:360px;text-align:center}"
        "h2{color:#34d399;margin-bottom:12px}p{color:#94a3b8;font-size:.9rem}</style>"
        "</head><body><div class='card'>"
        "<h2>&#10003; Credentials saved</h2>"
        "<p>Restarting and connecting to <strong style='color:#e2e8f0'>" +
        htmlEscape(ssid) +
        "</strong>&hellip;<br><br>This page will close. "
        "Find the device IP on your router or serial monitor.</p>"
        "</div></body></html>");

    shouldRestart = true;
}

// Captive-portal redirect — catches all unmatched requests.
// iOS / Android detect the portal when they get a redirect instead of their
// expected success response.
static void handleCaptiveRedirect() {
    String host = provServer.hostHeader();
    // If the request is already going to our AP IP, serve the page
    if (host == AP_IP.toString() || host.isEmpty()) {
        serveSetupPage();
        return;
    }
    provServer.sendHeader("Location", "http://" + AP_IP.toString() + "/", true);
    provServer.send(302, "text/plain", "");
}

// ---------------------------------------------------------------------------
// Public: enter provisioning mode
// ---------------------------------------------------------------------------
void provisionStart() {
    // AP + STA so WiFi scan works while hosting the AP
    WiFi.mode(WIFI_AP_STA);
    WiFi.softAPConfig(AP_IP, AP_IP, AP_MASK);
    WiFi.softAP(AP_SSID);
    delay(300);

    showProvDisplay();

    // Initial scan (blocking, ~3 s) so the first page load is instant
    WiFi.scanNetworks(false, true);

    // DNS: redirect every domain to our AP IP (captive portal)
    dnsServer.setErrorReplyCode(DNSReplyCode::NoError);
    dnsServer.start(53, "*", AP_IP);

    // Provisioning HTTP server
    provServer.on("/",             HTTP_GET,  handleProvRoot);
    provServer.on("/scan",         HTTP_GET,  handleScan);
    provServer.on("/connect",      HTTP_POST, handleConnect);
    // Common captive-portal detection paths
    provServer.on("/generate_204",              HTTP_GET, handleCaptiveRedirect);
    provServer.on("/hotspot-detect.html",       HTTP_GET, handleCaptiveRedirect);
    provServer.on("/library/test/success.html", HTTP_GET, handleCaptiveRedirect);
    provServer.on("/ncsi.txt",                  HTTP_GET, handleCaptiveRedirect);
    provServer.on("/connecttest.txt",           HTTP_GET, handleCaptiveRedirect);
    provServer.onNotFound(handleCaptiveRedirect);
    provServer.begin();

    Serial.print("Provisioning AP started: ");
    Serial.println(AP_SSID);
    Serial.print("Portal: http://");
    Serial.println(AP_IP.toString());

    while (!shouldRestart) {
        dnsServer.processNextRequest();
        provServer.handleClient();
        delay(5);
    }

    provServer.stop();
    delay(1500);   // let browser receive the response before we vanish
    ESP.restart();
}
