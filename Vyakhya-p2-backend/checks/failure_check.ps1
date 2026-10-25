# (1) Raw 4xx bodies via HttpClient. (2) Flask down: stop it, call /score, time it, restart is done by the caller.
$ProgressPreference = 'SilentlyContinue'
Add-Type -AssemblyName System.Net.Http
$hc = New-Object System.Net.Http.HttpClient; $hc.Timeout = [TimeSpan]::FromSeconds(15)
function Post($json) {
  $sw = [Diagnostics.Stopwatch]::StartNew()
  $c = New-Object System.Net.Http.StringContent($json, [Text.Encoding]::UTF8, 'application/json')
  try { $r = $hc.PostAsync('http://localhost:3000/score', $c).Result; "HTTP $([int]$r.StatusCode) $([int]$sw.Elapsed.TotalMilliseconds) ms  $($r.Content.ReadAsStringAsync().Result)" }
  catch { "NO RESPONSE after $([int]$sw.Elapsed.TotalMilliseconds) ms: $($_.Exception.InnerException.Message)" }
}
"=== 4xx bodies"
"missing fields : " + (Post '{"session_id":"ic-bad","redacted_text":"hi"}')
"invalid JSON   : " + (Post '{"session_id": "ic-bad", oops')
"wrong types    : " + (Post '{"session_id":"ic-bad","redacted_text":5,"context":{"new_device":"yes","new_geo":false,"screen_share":false,"call_active":false},"payment":{"payee_vpa":"bad","amount":-3,"payee_age_days":1,"user_avg_amount":1}}')
"bad optionals  : " + (Post '{"session_id":"ic-bad","redacted_text":"x","context":{"new_device":false,"new_geo":false,"screen_share":false,"call_active":false},"payment":{"payee_vpa":"a.b@ybl","amount":5,"payee_age_days":1,"user_avg_amount":1,"hour":25,"direction":"sideways"}}')

"=== 6. Flask stopped"
$flask = Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue | Select-Object -First 1
if ($flask) { Stop-Process -Id $flask.OwningProcess -Force; Start-Sleep 1; "stopped Flask pid $($flask.OwningProcess)" } else { "Flask was not listening on :8000" }
"port 8000 listening after stop: " + [bool](Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue)
$scam = '{"session_id":"ic-flaskdown","redacted_text":"Your KYC expired, share OTP now","context":{"new_device":false,"new_geo":false,"screen_share":false,"call_active":false},"payment":{"payee_vpa":"x.y@ybl","amount":500,"payee_age_days":1,"user_avg_amount":800}}'
"/score with Flask down #1: " + (Post $scam)
"/score with Flask down #2: " + (Post $scam)
try { "API /health while Flask down: " + $hc.GetStringAsync('http://localhost:3000/health').Result } catch { "API /health failed" }
$hc.Dispose()
"DONE"
