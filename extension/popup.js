const API_BASE = "http://127.0.0.1:8000/api";
let currentDashboardData = null;

// --- Tabs ---
const tabMap = { dashboard: "Dashboard", essentials: "Essentials", chat: "Chat", pipeline: "Pipeline" };
Object.keys(tabMap).forEach(t => {
  document.getElementById("tab" + tabMap[t]).addEventListener("click", () => {
    switchTab(t);
    if (t === "pipeline") loadHistory();
  });
});

function switchTab(tab) {
  Object.keys(tabMap).forEach(t => {
    document.getElementById("view" + tabMap[t]).classList.toggle("hidden", t !== tab);
    document.getElementById("tab" + tabMap[t]).classList.toggle("active", t === tab);
  });
}

// --- TAB 1: Applications Scan ---
document.getElementById("btnScan").addEventListener("click", async () => {
  const btn = document.getElementById("btnScan");
  btn.disabled = true;
  document.getElementById("scanLoading").classList.remove("hidden");
  document.getElementById("dashboardResult").classList.add("hidden");
  document.getElementById("dashboardEmpty").classList.add("hidden");

  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab.url?.includes("mail.google.com")) { alert("Open Gmail first."); return; }

    const [{ result: emails }] = await chrome.scripting.executeScript({ target: { tabId: tab.id }, function: scrapeGmail100Emails });
    if (!emails?.length) { alert("No emails found."); return; }

    const res = await fetch(`${API_BASE}/scan-inbox`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ emails }) });
    if (!res.ok) throw new Error("Server: " + res.status);
    const data = await res.json();
    currentDashboardData = data;
    renderDashboard(data.summary || {});
    document.getElementById("scanMeta").textContent = `${data.total_scanned} scanned / ${data.irrelevant_skipped} filtered`;
    document.getElementById("dashboardResult").classList.remove("hidden");
  } catch (e) { alert("Error: " + e.message); document.getElementById("dashboardEmpty").classList.remove("hidden"); }
  finally { btn.disabled = false; document.getElementById("scanLoading").classList.add("hidden"); }
});

function renderDashboard(summary) {
  const c = document.getElementById("accordionContainer"); c.innerHTML = "";
  const cfgs = {
    "Offer Received": { label: "Offers", css: "cat-offer" },
    "Interview Scheduled": { label: "Interviews", css: "cat-interview" },
    "Assessment Pending": { label: "Assessments", css: "cat-assessment" },
    "Application Submitted": { label: "Submitted", css: "cat-submitted" },
    "Awaiting Response": { label: "Awaiting", css: "cat-awaiting" },
    "Rejected": { label: "Rejected", css: "cat-rejected" }
  };
  if (!Object.keys(summary).length) { c.innerHTML = `<div class="empty-state">No applications detected.</div>`; return; }

  for (const [status, companies] of Object.entries(summary)) {
    if (!companies.length) continue;
    const cfg = cfgs[status] || { label: status, css: "" };
    const g = document.createElement("div"); g.className = "category-group";
    const h = document.createElement("div"); h.className = `category-header ${cfg.css}`;
    h.innerHTML = `<span>${cfg.label}</span><span class="counter">${companies.length}</span>`;
    const ct = document.createElement("div"); ct.className = "category-content";

    companies.forEach(co => {
      const d = document.createElement("div"); d.className = "company-card";
      let cal = co.date_detected ? `<button class="btn-secondary" onclick="addToCal('${co.company_name}','${co.last_response}')">Calendar</button>` : "";
      d.innerHTML = `<div class="comp-title">${co.company_name}</div><div class="comp-role">${co.role_title}</div><div class="comp-last-update">${co.last_response}</div><div class="card-actions"><button class="btn-secondary" onclick="genDraft('${co.company_name}','${co.role_title}','${co.last_response}')">Draft Follow-Up</button>${cal}</div>`;
      ct.appendChild(d);
    });
    ct.style.display = "block";
    h.onclick = () => ct.style.display = ct.style.display === "none" ? "block" : "none";
    g.append(h, ct); c.appendChild(g);
  }
}

document.getElementById("searchBar").addEventListener("input", e => {
  if (!currentDashboardData) return;
  const t = e.target.value.toLowerCase();
  const orig = currentDashboardData.summary || {};
  if (!t) { renderDashboard(orig); return; }
  const f = {};
  for (const [s, cos] of Object.entries(orig)) { const m = cos.filter(c => c.company_name.toLowerCase().includes(t) || c.role_title?.toLowerCase().includes(t)); if (m.length) f[s] = m; }
  renderDashboard(f);
});

document.getElementById("btnExport").addEventListener("click", () => {
  if (!currentDashboardData?.summary) return;
  let csv = "Company,Role,Status,Last Update,Date\n";
  for (const [s, cos] of Object.entries(currentDashboardData.summary)) cos.forEach(c => { csv += `"${c.company_name}","${c.role_title}","${s}","${(c.last_response||"").replace(/"/g,'""')}","${c.date_detected||""}"\n`; });
  const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" })); a.download = `inboxpilot_${new Date().toISOString().slice(0,10)}.csv`; a.click();
});

// --- TAB 2: Essentials Scan ---
document.getElementById("btnScanEssentials").addEventListener("click", async () => {
  const btn = document.getElementById("btnScanEssentials");
  btn.disabled = true;
  document.getElementById("essLoading").classList.remove("hidden");
  document.getElementById("essResult").classList.add("hidden");
  document.getElementById("essEmpty").classList.add("hidden");

  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab.url?.includes("mail.google.com")) { alert("Open Gmail first."); return; }

    const [{ result: emails }] = await chrome.scripting.executeScript({ target: { tabId: tab.id }, function: scrapeGmail100Emails });
    if (!emails?.length) { alert("No emails found."); return; }

    const res = await fetch(`${API_BASE}/scan-essentials`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ emails }) });
    if (!res.ok) throw new Error("Server: " + res.status);
    const data = await res.json();
    renderEssentials(data.summary || {});
    document.getElementById("essMeta").textContent = `${data.total_scanned} emails scanned / ${data.total_found} critical items found`;
    document.getElementById("essResult").classList.remove("hidden");
  } catch (e) { alert("Error: " + e.message); document.getElementById("essEmpty").classList.remove("hidden"); }
  finally { btn.disabled = false; document.getElementById("essLoading").classList.add("hidden"); }
});

function renderEssentials(summary) {
  const c = document.getElementById("essContainer"); c.innerHTML = "";
  const cfgs = {
    "Utility Bill":       { label: "Utility Bills",        css: "ess-utility" },
    "Insurance":          { label: "Insurance",            css: "ess-insurance" },
    "Tax & Government":   { label: "Tax & Government",     css: "ess-tax" },
    "Banking & Finance":  { label: "Banking & Finance",    css: "ess-banking" },
    "Medical & Health":   { label: "Medical & Health",     css: "ess-medical" },
    "Legal & Compliance": { label: "Legal & Compliance",   css: "ess-legal" },
    "Rent & Housing":     { label: "Rent & Housing",       css: "ess-rent" },
    "Vehicle & Transport":{ label: "Vehicle & Transport",  css: "ess-vehicle" },
    "Subscription Renewal":{ label: "Subscriptions",       css: "ess-subscription" },
    "Education & Fees":   { label: "Education & Fees",     css: "ess-education" }
  };

  if (!Object.keys(summary).length) { c.innerHTML = `<div class="empty-state">No critical bills, insurance, or admin emails detected in this scan.</div>`; return; }

  for (const [cat, items] of Object.entries(summary)) {
    if (!items.length) continue;
    const cfg = cfgs[cat] || { label: cat, css: "" };
    const g = document.createElement("div"); g.className = "category-group";
    const h = document.createElement("div"); h.className = `category-header ${cfg.css}`;
    h.innerHTML = `<span>${cfg.label}</span><span class="counter">${items.length}</span>`;
    const ct = document.createElement("div"); ct.className = "category-content";

    items.forEach(item => {
      const d = document.createElement("div"); d.className = "company-card";
      const urgClass = "urgency-" + (item.urgency || "medium").toLowerCase();
      let dueHtml = item.due_date ? `<div class="ess-due">Due: ${item.due_date}</div>` : "";
      d.innerHTML = `
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <div class="comp-title">${item.provider}</div>
          <span class="urgency-badge ${urgClass}">${item.urgency || "Medium"}</span>
        </div>
        <div class="comp-role">${item.subject}</div>
        <div class="comp-last-update" style="border-left-color:#f59e0b;">${item.summary}</div>
        ${dueHtml}
      `;
      ct.appendChild(d);
    });
    ct.style.display = "block";
    h.onclick = () => ct.style.display = ct.style.display === "none" ? "block" : "none";
    g.append(h, ct); c.appendChild(g);
  }
}

// --- TAB 3: Chat ---
document.getElementById("btnSendChat").addEventListener("click", sendChat);
document.getElementById("chatInput").addEventListener("keypress", e => { if (e.key === "Enter") sendChat(); });

async function sendChat() {
  const input = document.getElementById("chatInput");
  const box = document.getElementById("chatBox");
  const text = input.value.trim(); if (!text) return;
  box.innerHTML += `<div class="chat-bubble chat-user">${text}</div>`;
  input.value = ""; box.scrollTop = box.scrollHeight;
  const lid = "ai-" + Date.now();
  box.innerHTML += `<div id="${lid}" class="chat-bubble chat-ai">Thinking...</div>`;
  box.scrollTop = box.scrollHeight;
  try {
    const r = await fetch(`${API_BASE}/chat`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question: text }) });
    const d = await r.json();
    document.getElementById(lid).innerHTML = d.answer.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
  } catch (e) { document.getElementById(lid).textContent = "Error: " + e.message; }
  box.scrollTop = box.scrollHeight;
}

// --- TAB 4: History ---
async function loadHistory() {
  const c = document.getElementById("trackerList"); c.innerHTML = "Loading...";
  try {
    const r = await fetch(`${API_BASE}/applications`); const apps = await r.json();
    if (!apps.length) { c.innerHTML = `<div class="empty-state">No history yet.</div>`; return; }
    c.innerHTML = apps.slice(0, 30).map(a => `<div class="category-group" style="padding:8px 10px;"><span style="font-size:9px;font-weight:600;background:#f3f4f6;padding:2px 6px;border-radius:3px;text-transform:uppercase;">${a.status}</span><div class="comp-title" style="margin-top:4px;">${a.company_name}</div><div class="comp-role">${a.role_title||""}</div>${a.summary?`<div style="font-size:10.5px;color:#6b7280;margin-top:3px;">${a.summary}</div>`:""}</div>`).join("");
  } catch { c.innerHTML = `<div class="empty-state" style="color:#ef4444;">Failed to load.</div>`; }
}

// --- Helpers ---
window.genDraft = async function(comp, role, status) {
  const m = document.getElementById("draftModal"), o = document.getElementById("draftOutput");
  o.value = "Generating..."; m.classList.remove("hidden");
  try { const r = await fetch(`${API_BASE}/generate-draft`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ company_name: comp, role_title: role, last_status: status }) }); const d = await r.json(); o.value = d.draft; }
  catch (e) { o.value = "Error: " + e.message; }
};
document.getElementById("btnCloseDraft").onclick = () => document.getElementById("draftModal").classList.add("hidden");
window.addToCal = (t, d) => window.open(`https://calendar.google.com/calendar/render?action=TEMPLATE&text=${encodeURIComponent(t+" Interview")}&details=${encodeURIComponent(d)}`, "_blank");

// --- Gmail Scraper ---
async function scrapeGmail100Emails() {
  const emails = [], seen = new Set();
  function collect() {
    document.querySelectorAll("tr.zA, [role='row']").forEach(row => {
      const sEl = row.querySelector("span.bA4") || row.querySelector("span[email]") || row.querySelector("span.zF");
      const subEl = row.querySelector("span.bog") || row.querySelector("a.xT span") || row.querySelector("span.bqe");
      const snipEl = row.querySelector("span.y2");
      const sender = sEl ? (sEl.getAttribute("email") || sEl.innerText) : "";
      const subject = subEl ? subEl.innerText : "";
      const snippet = snipEl ? snipEl.innerText : "";
      const key = `${sender}_${subject}`;
      if ((subject || sender) && !seen.has(key)) { seen.add(key); emails.push({ sender, subject, snippet }); }
    });
  }
  collect();
  const sc = document.querySelector("div.AO, div.ae4, div[role='main']") || window;
  for (let i = 0; i < 4; i++) { if (emails.length >= 100) break; sc.scrollBy(0, 1200); await new Promise(r => setTimeout(r, 450)); collect(); }
  sc.scrollTo(0, 0);
  return emails.slice(0, 100);
}