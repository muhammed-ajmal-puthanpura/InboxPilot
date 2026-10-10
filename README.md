# InboxPilot ✈️

InboxPilot is an AI-powered Chrome Extension and local FastAPI backend that turns your Gmail inbox into a structured life & career dashboard.

## 🌟 Key Features
- **Application Tracker:** Scans your last 100 emails and groups applications by status (*Offer Received*, *Interview Scheduled*, *Assessment Pending*, *Awaiting Response*, *Rejected*).
- **Life Essentials Scanner:** Automatically detects critical emails (Utility Bills, Insurance, Banking, Tax, Medical, Legal) while filtering out promotional emails and spam.
- **Natural Language Assistant:** Ask questions about your applications and critical deadlines in natural language.
- **1-Click Actions:** Generate context-aware follow-up email drafts and add interview dates directly to Google Calendar.
- **Privacy First:** Runs locally with your own Groq API key and local SQLite storage.

## 🛠️ Architecture
- **Frontend:** Chrome Extension (Manifest V3, HTML5, Vanilla JavaScript)
- **Backend:** FastAPI, SQLite, Groq Cloud API (`llama-3.1-8b-instant` / `llama-3.3-70b-versatile`)

---

## 🚀 Getting Started

### 1. Backend Setup
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Set your Groq API Key
export GROQ_API_KEY="your_groq_api_key_here"

# Start the server
python3 server.py


2. Chrome Extension Setup

    Open Google Chrome and go to chrome://extensions/
    Enable Developer mode (top-right toggle).
    Click Load unpacked (top-left button).
    Select the extension/ folder in this repository.
    Open Gmail and click the InboxPilot extension icon.
