import os
import re
import json
import sqlite3
import traceback
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from groq import Groq

app = FastAPI(title="InboxPilot - Full Suite")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    print("\n[ERROR] GROQ_API_KEY is not set!")
    print("Run: export GROQ_API_KEY='gsk_...'\n")

client = Groq(api_key=GROQ_API_KEY or "dummy_key")

def find_working_model() -> str:
    print("\nProbing active Groq models...")
    blacklist = ["guard", "safeguard", "whisper", "vision", "embed", "orpheus", "moderation", "distil"]
    try:
        models_data = client.models.list().data
        available_ids = [m.id for m in models_data if not any(b in m.id.lower() for b in blacklist)]
        for model_id in available_ids:
            try:
                test_resp = client.chat.completions.create(
                    model=model_id,
                    messages=[{"role": "user", "content": "hi"}],
                    max_tokens=2
                )
                if test_resp and test_resp.choices:
                    print(f"Verified model: >>> {model_id} <<<\n")
                    return model_id
            except Exception:
                continue
    except Exception as e:
        print(f"Model probe warning: {e}")
    return "llama-3.1-8b-instant"

ACTIVE_MODEL = find_working_model()

def extract_json_from_text(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?", "", text, flags=re.MULTILINE)
    text = re.sub(r"```$", "", text, flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    bracket_match = re.search(r"(\{[\s\S]*\})", text)
    if bracket_match:
        try:
            return json.loads(bracket_match.group(1).strip())
        except Exception:
            pass
    return {"items": []}

# --- Database ---
DB_FILE = "inboxpilot.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_name TEXT, role_title TEXT, status TEXT,
            deadline_or_date TEXT, summary TEXT, action_required TEXT,
            email_subject TEXT, sender TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS essentials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT, provider TEXT, subject TEXT,
            summary TEXT, due_date TEXT, urgency TEXT,
            sender TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

init_db()

# --- Schemas ---
class ScanInboxRequest(BaseModel):
    emails: list[dict]

class GenerateFollowUpRequest(BaseModel):
    company_name: str
    role_title: Optional[str] = "Applicant"
    last_status: str

class ChatQueryRequest(BaseModel):
    question: str

# --- Endpoints ---

@app.post("/api/scan-inbox")
async def scan_inbox(req: ScanInboxRequest):
    try:
        total_emails = req.emails[:100]
        total_count = len(total_emails)
        if total_count == 0:
            return {"summary": {}, "total_applications": 0, "total_scanned": 0, "irrelevant_skipped": 0}

        print(f"\n[Scan] Processing {total_count} emails for applications...")
        BATCH_SIZE = 25
        all_apps = []

        for i in range(0, total_count, BATCH_SIZE):
            batch = total_emails[i:i + BATCH_SIZE]
            email_list = ""
            for idx, em in enumerate(batch, 1):
                sender = em.get("sender", "?")[:30].replace("\n", " ")
                subj = em.get("subject", "?")[:60].replace("\n", " ")
                email_list += f"{idx}. From: {sender} | Subj: {subj}\n"

            prompt = f"""
Extract job/internship/academic application emails. Ignore everything else.

EMAILS:
{email_list}

Respond ONLY with valid JSON:
{{
  "applications": [
    {{
      "company_name": "Company Name",
      "role_title": "Role or null",
      "status": "One of: Application Submitted, Assessment Pending, Interview Scheduled, Offer Received, Rejected, Awaiting Response",
      "last_response": "1-sentence summary of last update",
      "date_detected": "Any date mentioned or null"
    }}
  ]
}}
"""
            try:
                response = client.chat.completions.create(
                    model=ACTIVE_MODEL,
                    messages=[
                        {"role": "system", "content": "Return strict JSON."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.1
                )
                data = extract_json_from_text(response.choices[0].message.content)
                all_apps.extend(data.get("applications", []))
            except Exception as e:
                print(f"Batch error: {e}")
                continue

        STATUS_PRIORITY = {
            "Offer Received": 6, "Interview Scheduled": 5,
            "Assessment Pending": 4, "Application Submitted": 3,
            "Awaiting Response": 2, "Rejected": 1,
        }

        deduped = {}
        for app in all_apps:
            comp = (app.get("company_name") or "").strip().title()
            if not comp or comp.lower() in ["unknown", "none", "null"]:
                continue
            status = app.get("status", "Application Submitted")
            role = app.get("role_title")
            last_resp = app.get("last_response", "Awaiting next steps")
            date_det = app.get("date_detected")

            if comp not in deduped:
                deduped[comp] = {"status": status, "role": role, "last_response": last_resp, "date_detected": date_det}
            else:
                if STATUS_PRIORITY.get(status, 0) >= STATUS_PRIORITY.get(deduped[comp]["status"], 0):
                    deduped[comp] = {"status": status, "role": role, "last_response": last_resp, "date_detected": date_det or deduped[comp]["date_detected"]}

        grouped = {}
        for comp, info in deduped.items():
            s = info["status"]
            if s not in grouped:
                grouped[s] = []
            grouped[s].append({
                "company_name": comp, "role_title": info["role"] or "Applicant",
                "last_response": info["last_response"], "date_detected": info["date_detected"]
            })

        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        for comp, info in deduped.items():
            c.execute("INSERT INTO applications (company_name, role_title, status, summary, deadline_or_date) VALUES (?,?,?,?,?)",
                      (comp, info["role"], info["status"], info["last_response"], info["date_detected"]))
        conn.commit()
        conn.close()

        return {"summary": grouped, "total_applications": len(deduped), "total_scanned": total_count, "irrelevant_skipped": max(0, total_count - len(all_apps))}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/scan-essentials")
async def scan_essentials(req: ScanInboxRequest):
    """Scans inbox for critical life-admin emails: bills, insurance, tax, bank, medical, legal."""
    try:
        total_emails = req.emails[:100]
        total_count = len(total_emails)
        if total_count == 0:
            return {"summary": {}, "total_found": 0, "total_scanned": 0}

        print(f"\n[Essentials] Scanning {total_count} emails for critical life-admin items...")
        BATCH_SIZE = 25
        all_items = []

        for i in range(0, total_count, BATCH_SIZE):
            batch = total_emails[i:i + BATCH_SIZE]
            email_list = ""
            for idx, em in enumerate(batch, 1):
                sender = em.get("sender", "?")[:35].replace("\n", " ")
                subj = em.get("subject", "?")[:65].replace("\n", " ")
                snippet = em.get("snippet", "")[:80].replace("\n", " ")
                email_list += f"{idx}. From: {sender} | Subj: {subj} | Info: {snippet}\n"

            prompt = f"""
You are a life-admin email classifier. Identify CRITICAL personal and financial emails that must not be missed.

VALID CATEGORIES (use exactly one):
- "Utility Bill" (electricity, water, gas, internet, phone bills)
- "Insurance" (health, car, home, life insurance renewal, expiry, claims)
- "Tax & Government" (tax returns, IRS/government notices, filing deadlines)
- "Banking & Finance" (bank statements, loan payments, credit card bills, EMI due)
- "Medical & Health" (hospital bills, prescriptions, appointment reminders, lab results)
- "Legal & Compliance" (legal notices, court dates, contract renewals, visa/immigration)
- "Rent & Housing" (rent due, lease renewal, maintenance notices)
- "Vehicle & Transport" (car registration, license renewal, insurance, challan/fine)
- "Subscription Renewal" (important paid subscriptions about to expire or auto-renew)
- "Education & Fees" (tuition fees, exam registration, scholarship deadlines)

STRICTLY IGNORE these (do NOT include them):
- Promotional emails, marketing, discounts, sale alerts
- Newsletters, social media notifications
- Order confirmations, shipping updates, delivery notifications
- Job applications (handled separately)
- Spam, phishing, or irrelevant automated messages

EMAILS:
{email_list}

Respond ONLY with valid JSON:
{{
  "items": [
    {{
      "category": "One of the valid categories above",
      "provider": "Company/organization name (e.g. 'State Electricity Board', 'HDFC Bank', 'LIC')",
      "subject": "Brief description of what the email is about",
      "summary": "1-sentence explanation of what action is needed or what the update is",
      "due_date": "Any due date, expiry date, or deadline mentioned, or null",
      "urgency": "One of: Critical, High, Medium, Low"
    }}
  ]
}}
"""
            try:
                response = client.chat.completions.create(
                    model=ACTIVE_MODEL,
                    messages=[
                        {"role": "system", "content": "You classify critical life-admin emails. Return strict JSON. Never include promotions or newsletters."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.1
                )
                data = extract_json_from_text(response.choices[0].message.content)
                all_items.extend(data.get("items", []))
            except Exception as e:
                print(f"Essentials batch error: {e}")
                continue

        # Deduplicate by provider + category
        deduped = {}
        for item in all_items:
            provider = (item.get("provider") or "Unknown").strip().title()
            category = item.get("category", "Other")
            key = f"{provider}_{category}"

            if key not in deduped:
                deduped[key] = item
            else:
                # Keep higher urgency
                urgency_rank = {"Critical": 4, "High": 3, "Medium": 2, "Low": 1}
                if urgency_rank.get(item.get("urgency", "Low"), 0) > urgency_rank.get(deduped[key].get("urgency", "Low"), 0):
                    deduped[key] = item

        # Group by category
        grouped = {}
        for item in deduped.values():
            cat = item.get("category", "Other")
            if cat not in grouped:
                grouped[cat] = []
            grouped[cat].append({
                "provider": item.get("provider", "Unknown"),
                "subject": item.get("subject", ""),
                "summary": item.get("summary", ""),
                "due_date": item.get("due_date"),
                "urgency": item.get("urgency", "Medium")
            })

        # Sort categories by urgency (Critical first)
        urgency_order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
        for cat in grouped:
            grouped[cat].sort(key=lambda x: urgency_order.get(x["urgency"], 9))

        # Save to SQLite
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        for item in deduped.values():
            c.execute("""
                INSERT INTO essentials (category, provider, subject, summary, due_date, urgency, sender)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                item.get("category"), item.get("provider"), item.get("subject"),
                item.get("summary"), item.get("due_date"), item.get("urgency"),
                item.get("provider")
            ))
        conn.commit()
        conn.close()

        print(f"[Essentials] Found {len(deduped)} critical items.")

        return {
            "summary": grouped,
            "total_found": len(deduped),
            "total_scanned": total_count
        }

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/chat")
async def chat_with_inbox(req: ChatQueryRequest):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    apps = conn.cursor().execute("SELECT company_name, role_title, status, summary, deadline_or_date FROM applications ORDER BY id DESC LIMIT 30").fetchall()
    essentials = conn.cursor().execute("SELECT category, provider, summary, due_date, urgency FROM essentials ORDER BY id DESC LIMIT 30").fetchall()
    conn.close()

    app_context = "\n".join([f"- {r['company_name']} | {r['role_title']} | {r['status']} | {r['summary']} | Date: {r['deadline_or_date']}" for r in apps]) or "No applications tracked."
    ess_context = "\n".join([f"- [{r['urgency']}] {r['category']}: {r['provider']} | {r['summary']} | Due: {r['due_date']}" for r in essentials]) or "No essentials tracked."

    prompt = f"""
You are InboxPilot's intelligent life assistant. Answer the user's question using the data below.

APPLICATIONS:
{app_context}

ESSENTIALS (Bills, Insurance, Tax, etc.):
{ess_context}

USER QUESTION: "{req.question}"

Give a direct, concise answer (2-4 sentences). Highlight key names in bold.
"""
    try:
        response = client.chat.completions.create(
            model=ACTIVE_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )
        return {"answer": response.choices[0].message.content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/generate-draft")
async def generate_draft(req: GenerateFollowUpRequest):
    prompt = f"""
Write a polite, professional follow-up email to '{req.company_name}' about '{req.role_title}'.
Context: '{req.last_status}'.
Include Subject line and Body (3-4 sentences).
"""
    try:
        response = client.chat.completions.create(
            model=ACTIVE_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.6
        )
        return {"draft": response.choices[0].message.content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/applications")
async def get_applications():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    rows = conn.cursor().execute("SELECT * FROM applications ORDER BY id DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)