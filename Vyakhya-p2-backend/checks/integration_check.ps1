# Integration check of the running stack (API :3000 -> Flask :8000 -> Atlas). Read-only except for the
# /score calls it makes. Never prints .env values. Usage: powershell -File integration_check.ps1 > log
$ProgressPreference = 'SilentlyContinue'
$api = 'http://localhost:3000'
$tag = (Get-Date).ToString('HHmmss')

function Call($method, $url, $body = $null, $headers = @{}, $raw = $null) {
  $sw = [Diagnostics.Stopwatch]::StartNew()
  $p = @{ Method = $method; Uri = $url; UseBasicParsing = $true; Headers = $headers; TimeoutSec = 15 }
  if ($raw -ne $null) { $p.Body = [Text.Encoding]::UTF8.GetBytes($raw); $p.ContentType = 'application/json; charset=utf-8' }
  elseif ($body -ne $null) { $p.Body = [Text.Encoding]::UTF8.GetBytes(($body | ConvertTo-Json -Depth 6 -Compress)); $p.ContentType = 'application/json; charset=utf-8' }
  try { $r = Invoke-WebRequest @p; $code = [int]$r.StatusCode; $content = $r.Content; $hdr = $r.Headers }
  catch {
    $resp = $_.Exception.Response
    if ($resp) { $code = [int]$resp.StatusCode; $content = (New-Object IO.StreamReader($resp.GetResponseStream())).ReadToEnd(); $hdr = $resp.Headers }
    else { $code = 0; $content = "NO RESPONSE: $($_.Exception.Message)"; $hdr = @{} }
  }
  [pscustomobject]@{ code = $code; ms = [int]$sw.Elapsed.TotalMilliseconds; content = $content; headers = $hdr }
}
function J($s) { try { $s | ConvertFrom-Json } catch { $null } }
function Section($t) { ""; "=" * 100; $t; "=" * 100 }

Section "2. HEALTH (tag $tag)"
$f = Call GET 'http://127.0.0.1:8000/health'; "Flask GET /health        -> HTTP $($f.code) $($f.ms) ms  $($f.content)"
$h = Call GET "$api/health"; "API   GET /health        -> HTTP $($h.code) $($h.ms) ms  $($h.content)"
$st0 = J (Call GET "$api/stats").content; "API   GET /stats (before) -> total=$($st0.total) tiers=$($st0.tiers | ConvertTo-Json -Compress)"
$ev0 = J (Call GET "$api/events").content; "API   GET /events (before)-> $(@($ev0).Count) events (route caps at 100)"
$m0 = J (Call GET "$api/metrics").content; "API   GET /metrics        -> $(@($m0.PSObject.Properties).Count) files: $(($m0.PSObject.Properties.Name | Sort-Object) -join ', ')"
$fe = Call GET 'http://localhost:5173/'; "Frontend :5173            -> HTTP $($fe.code) $($fe.content.Substring(0, [Math]::Min(80, $fe.content.Length)))"
$tok = (J (Call POST "$api/login" @{ username = 'analyst'; password = 'analyst123' }).content).token
$auth = @{ Authorization = "Bearer $tok" }
$aud0 = J (Call GET "$api/audit" $null $auth).content; "API   GET /audit (before) -> $(@($aud0).Count) records (route caps at 500)"

Section "3. END-TO-END SCORING (full responses)"
# Payloads live in UTF-8 JSON (PowerShell 5 would misread Devanagari inside a BOM-less .ps1).
$rawPayloads = [IO.File]::ReadAllText((Join-Path $PSScriptRoot 'payloads.json'), [Text.Encoding]::UTF8).Replace('TAG', $tag)
$obj = $rawPayloads | ConvertFrom-Json
$cases = [ordered]@{}; foreach ($p in $obj.PSObject.Properties) { $cases[$p.Name] = ($p.Value | ConvertTo-Json -Depth 6 -Compress) }
$scored = @{}
foreach ($name in $cases.Keys) {
  $r = Call POST "$api/score" $null @{} $cases[$name]
  $scored[$name] = J $r.content
  ""; "--- $name"; "HTTP $($r.code), round-trip $($r.ms) ms"; $r.content
}
""; "--- d) malformed bodies"
$bad = @(
  @('missing payment + context', '{"session_id":"ic-bad","redacted_text":"hi"}'),
  @('invalid JSON', '{"session_id": "ic-bad", oops'),
  @('wrong types', '{"session_id":"ic-bad","redacted_text":5,"context":{"new_device":"yes","new_geo":false,"screen_share":false,"call_active":false},"payment":{"payee_vpa":"bad","amount":-3,"payee_age_days":1,"user_avg_amount":1}}'),
  @('bad optional fields', '{"session_id":"ic-bad","redacted_text":"x","context":{"new_device":false,"new_geo":false,"screen_share":false,"call_active":false},"payment":{"payee_vpa":"a.b@ybl","amount":5,"payee_age_days":1,"user_avg_amount":1,"hour":25,"direction":"sideways"}}')
)
foreach ($b in $bad) { $r = Call POST "$api/score" $null @{} $b[1]; "$($b[0]): HTTP $($r.code) $($r.ms) ms  $($r.content)" }
$h2 = Call GET "$api/health"; "API still up after malformed bodies: HTTP $($h2.code) $($h2.content)"

Section "4. PERSISTENCE + REDACTION"
$st1 = J (Call GET "$api/stats").content
"stats total: $($st0.total) -> $($st1.total)  (expected +$($cases.Count))   tiers now $($st1.tiers | ConvertTo-Json -Compress)"
$ev1 = J (Call GET "$api/events").content
$mine = @($ev1 | Where-Object { $_.created_at -and ($scored.Values.R -contains $_.R) } | Select-Object -First $cases.Count)
"events: newest $($cases.Count): " + ((@($ev1)[0..($cases.Count - 1)] | ForEach-Object { "R=$($_.R)/$($_.tier)" }) -join ', ')
"event keys exposed by /events: " + ((@($ev1)[0].PSObject.Properties.Name) -join ', ')
$evJson = $ev1 | ConvertTo-Json -Depth 5
"raw identifiers in /events feed? phone=$($evJson -match '9876543210')  vpa=$($evJson -match 'kyc\.verify@ybl|refund\.desk')  acct=$($evJson -match '123456789012')  text=$($evJson -match 'KYC has expired')"
$m1 = J (Call GET "$api/metrics").content; "metrics files: $(@($m0.PSObject.Properties).Count) -> $(@($m1.PSObject.Properties).Count) (file-based; scoring does not change them)"
$aud1 = J (Call GET "$api/audit" $null $auth).content
$myAudit = @($aud1 | Where-Object { $_.session_id -like "ic-*-$tag" })
"audit: $(@($aud0).Count) -> $(@($aud1).Count) records; records for this run: $($myAudit.Count) -> " + (($myAudit | ForEach-Object { "$($_.action)/$($_.session_id)/R=$($_.R)/$($_.tier)/model=$($_.model_version)/rules=$($_.rules_version)/redaction=$($_.redaction_counts | ConvertTo-Json -Compress)" }) -join ' | ')
$cs = J (Call GET "$api/cases" $null $auth).content
foreach ($c in @($cs | Where-Object { $_.session_id -like "ic-*-$tag" })) {
  $t = $c.redacted_text
  "stored case text [$($c.session_id)] status=$($c.status): $t"
  "   leaks? phone=$($t -match '9876543210') vpa=$($t -match '@ybl|@okicici|@okbank') acct=$($t -match '123456789012')  payment.payee_vpa stored=$($c.payment.payee_vpa)"
}
$unauth = Call GET "$api/cases"; "GET /cases without token -> HTTP $($unauth.code)"

Section "5. FRONTEND CONTRACT (CORS, SSE)"
$o = @{ Origin = 'http://localhost:5173' }
foreach ($u in "$api/health", "$api/events", "$api/stats", "$api/metrics") { $r = Call GET $u $null $o; "GET $u  Origin:5173 -> HTTP $($r.code)  Access-Control-Allow-Origin=$($r.headers['Access-Control-Allow-Origin'])" }
$pre = Call OPTIONS "$api/score" $null @{ Origin = 'http://localhost:5173'; 'Access-Control-Request-Method' = 'POST'; 'Access-Control-Request-Headers' = 'content-type,authorization' }
"OPTIONS /score preflight -> HTTP $($pre.code)  Allow-Origin=$($pre.headers['Access-Control-Allow-Origin'])  Allow-Methods=$($pre.headers['Access-Control-Allow-Methods'])  Allow-Headers=$($pre.headers['Access-Control-Allow-Headers'])"
$pre2 = Call OPTIONS "$api/cases/x/decision" $null @{ Origin = 'http://localhost:5173'; 'Access-Control-Request-Method' = 'POST'; 'Access-Control-Request-Headers' = 'content-type,authorization' }
"OPTIONS /cases/:id/decision preflight -> HTTP $($pre2.code)  Allow-Headers=$($pre2.headers['Access-Control-Allow-Headers'])"
$fl = Call GET 'http://127.0.0.1:8000/health' $null $o; "Flask direct with Origin:5173 -> Allow-Origin=$($fl.headers['Access-Control-Allow-Origin']) (Flask allows only CORS_ORIGINS, default :3000; browser should not call Flask)"

# SSE: open /stream, trigger one /score, read until a data: line or 8 s
Add-Type -AssemblyName System.Net.Http
$hc = New-Object System.Net.Http.HttpClient; $hc.Timeout = [TimeSpan]::FromSeconds(20)
$req = New-Object System.Net.Http.HttpRequestMessage([System.Net.Http.HttpMethod]::Get, "$api/stream"); $req.Headers.Add('Origin', 'http://localhost:5173')
$resp = $hc.SendAsync($req, [System.Net.Http.HttpCompletionOption]::ResponseHeadersRead).Result
"GET /stream -> HTTP $([int]$resp.StatusCode) content-type=$($resp.Content.Headers.ContentType) Allow-Origin=$(($resp.Headers.GetValues('Access-Control-Allow-Origin')) -join ',')"
$reader = New-Object IO.StreamReader($resp.Content.ReadAsStreamAsync().Result)
$null = Call POST "$api/score" $null @{} $cases['b) benign: dinner split to a known contact']
$deadline = (Get-Date).AddSeconds(8); $got = $null
while ((Get-Date) -lt $deadline -and -not $got) { $t = $reader.ReadLineAsync(); if ($t.Wait(1000) -and $t.Result -like 'data:*') { $got = $t.Result } }
"SSE event after a /score: " + $(if ($got) { $got } else { 'NONE within 8 s' })
$hc.Dispose()
"DONE"
