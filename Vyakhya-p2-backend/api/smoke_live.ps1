# Live smoke test of the running stack: API :3000 -> Flask :8000 -> Atlas.
# Prints scores, tiers and counts only (no message text). Run: powershell -File smoke_live.ps1
$ErrorActionPreference = 'Stop'
$api = 'http://localhost:3000'
function Post($path, $body, $token) {
  $h = @{}; if ($token) { $h.Authorization = "Bearer $token" }
  Invoke-RestMethod -Method Post -Uri "$api$path" -ContentType 'application/json; charset=utf-8' -Headers $h `
    -Body ([Text.Encoding]::UTF8.GetBytes(($body | ConvertTo-Json -Depth 5 -Compress)))
}

"1. GET /health          -> " + (Invoke-RestMethod "$api/health" | ConvertTo-Json -Compress)

$ctx = @{ new_device = $false; new_geo = $false; screen_share = $true; call_active = $true }
$scam = @{ session_id = 'smoke-scam'; context = $ctx
  redacted_text = 'Congratulations! Cashback of Rs 1,499 is waiting. Approve the collect request and enter your UPI PIN to receive it.'
  payment = @{ payee_vpa = 'rewards.desk@okhdfc'; amount = 1499; payee_age_days = 1; user_avg_amount = 900; direction = 'collect'; hour = 21 } }
$t0 = Get-Date; $s = Post '/score' $scam; $ms = ((Get-Date) - $t0).TotalMilliseconds
"2. POST /score (scam)   -> R=$($s.R) tier=$($s.tier) hold=$($s.hold) case=$([bool]$s.case_id) model=$($s.model_version)/$($s.rules_version) round-trip=$([int]$ms) ms"
"   reasons=$($s.reasons -join ',')  context_flags=$($s.context_flags -join ',')"
"   why[0]=$($s.why[0])"
"   disclaimer set=$([bool]$s.disclaimer)  ask_user set=$([bool]$s.ask_user)  hold_expires_at=$($s.hold_expires_at)"

$ok = @{ session_id = 'smoke-benign'; redacted_text = ''
  context = @{ new_device = $false; new_geo = $false; screen_share = $false; call_active = $false }
  payment = @{ payee_vpa = 'kirana@okaxis'; amount = 640; payee_age_days = 400; user_avg_amount = 700; payee_prior_txns = 85; hour = 18 } }
$t0 = Get-Date; $b = Post '/score' $ok; $ms = ((Get-Date) - $t0).TotalMilliseconds
"3. POST /score (benign) -> R=$($b.R) tier=$($b.tier) hold=$($b.hold) case=$([bool]$b.case_id) round-trip=$([int]$ms) ms"

$ev = Invoke-RestMethod "$api/events"
"4. GET /events          -> $($ev.Count) events; newest: R=$($ev[0].R) tier=$($ev[0].tier); text in feed: $([bool]((($ev | ConvertTo-Json -Depth 4) -match 'Cashback|rewards\.desk|smoke-scam')))"
$st = Invoke-RestMethod "$api/stats"
"5. GET /stats           -> total=$($st.total) tiers=$($st.tiers | ConvertTo-Json -Compress) zero_friction_pct=$($st.zero_friction_pct)"
$m = Invoke-RestMethod "$api/metrics"
"6. GET /metrics         -> files: $(($m.PSObject.Properties.Name | Sort-Object) -join ', ')"

$tok = (Post '/login' @{ username = 'analyst'; password = 'analyst123' }).token
$cases = Invoke-RestMethod "$api/cases" -Headers @{ Authorization = "Bearer $tok" }
"7. GET /cases (analyst) -> $($cases.Count) cases; top: R=$($cases[0].R) tier=$($cases[0].tier) status=$($cases[0].status)"
$aud = Invoke-RestMethod "$api/audit" -Headers @{ Authorization = "Bearer $tok" }
$last = $aud | Where-Object { $_.action -eq 'score' } | Select-Object -First 1
"8. GET /audit (analyst) -> $($aud.Count) records; latest score record model_version=$($last.model_version) rules_version=$($last.rules_version)"
try { Invoke-RestMethod "$api/cases" | Out-Null; "9. GET /cases (no token) -> NOT PROTECTED" }
catch { "9. GET /cases (no token) -> HTTP $($_.Exception.Response.StatusCode.value__) (expected 401)" }
