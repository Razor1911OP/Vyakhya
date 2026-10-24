# Vyakhya: project context
AI scam-pattern detector for Indian UPI payments (2-day hackathon).
Flow: browser redacts text -> Node/Express API (MongoDB) -> Python Flask
scoring service (text classifier + risk fusion) -> tier -> soft-hold before
debit -> analyst console.
Tiers by risk score R (0-100): LOW <40, MEDIUM 40-69, HIGH 70-84, CRITICAL >=85.

POST /score
in:  { session_id, redacted_text, context:{new_device,new_geo,screen_share,
       call_active}, payment:{payee_vpa, amount, payee_age_days, user_avg_amount} }
out: { R, tier, reasons:[string], hold:bool, case_id }

Folders: ml/ (training), ml_service/ (Flask), api/ (Node), web/ (UI).
Rules: only synthetic or public data, no real PII. Raw text is never stored.
Every decision gets an append-only audit record. Write simple, commented code
a team member can explain to a judge. One file at a time, with tests.