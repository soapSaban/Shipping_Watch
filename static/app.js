// Frontend application logic for FreightTiger Shipping Watch
document.addEventListener("DOMContentLoaded", () => {
    loadDashboardData();
    loadContextNotes();
    setupEventListeners();
});

let allRecords = [];

async function loadDashboardData() {
    try {
        const res = await fetch("/api/data");
        const data = await res.json();
        allRecords = data.records || [];

        updateKpis(allRecords, data.telemetry);
        populateRouteFilter(data.available_routes);
        renderTable(allRecords);
    } catch (err) {
        console.error("Failed to load dashboard data:", err);
    }
}

function updateKpis(records, telemetry) {
    const unexplained = records.filter(r => r.flagged === "Yes").length;
    const justified = records.filter(r => r.flagged && r.flagged.startsWith("No (justified)")).length;

    document.getElementById("kpi-unjustified").textContent = unexplained;
    document.getElementById("kpi-justified").textContent = justified;

    if (telemetry) {
        document.getElementById("kpi-tokens").textContent = (telemetry.total_tokens || 0).toLocaleString();
        document.getElementById("kpi-calls").textContent = `${telemetry.total_llm_calls || 0} LLM Calls ($0.00 Free Tier)`;
    }
}

function populateRouteFilter(routes) {
    const select = document.getElementById("filter-route");
    if (!select || !routes) return;
    
    // Clear existing except first
    select.innerHTML = '<option value="">All Corridors</option>';
    routes.forEach(r => {
        const opt = document.createElement("option");
        opt.value = r;
        opt.textContent = r;
        select.appendChild(opt);
    });
}

function renderTable(records) {
    const tbody = document.getElementById("table-body");
    if (!tbody) return;

    if (records.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" class="text-center py-8 text-muted">No matching cost anomalies found.</td></tr>';
        return;
    }

    tbody.innerHTML = records.map(r => {
        const isJustified = r.flagged && r.flagged.startsWith("No (justified)");
        const badgeClass = isJustified ? "status-justified" : "status-unjustified";
        const badgeText = isJustified ? "No (justified)" : "Yes (Unexplained)";
        const noteBadge = r.matched_note_id ? `<span class="badge-note">${r.matched_note_id}</span>` : '<span class="text-muted">—</span>';

        return `
            <tr>
                <td><strong>${escapeHtml(r.route)}</strong></td>
                <td class="font-mono">${escapeHtml(r.week_of)}</td>
                <td class="font-mono">₹${escapeHtml(r.cost_per_tonne_km)}</td>
                <td><span class="font-mono text-muted">${escapeHtml(r.vs_own_history)}</span></td>
                <td><span class="font-mono text-muted">${escapeHtml(r.vs_similar_routes)}</span></td>
                <td><span class="badge-status ${badgeClass}">${badgeText}</span></td>
                <td>${noteBadge}</td>
                <td class="explanation-cell">${escapeHtml(r.reason)}</td>
            </tr>
        `;
    }).join("");
}

async function loadContextNotes() {
    try {
        const res = await fetch("/api/notes");
        const data = await res.json();
        const container = document.getElementById("notes-list");
        if (!container || !data.notes) return;

        document.getElementById("notes-count").textContent = `${data.notes.length} notes`;

        container.innerHTML = data.notes.map(n => `
            <div class="note-card">
                <div class="note-header">
                    <span class="note-badge-id">${n.note_id}</span>
                    <span class="note-date font-mono">${n.date}</span>
                </div>
                <div class="note-applies">${escapeHtml(n.applies_to)}</div>
                <div class="note-text">${escapeHtml(n.note)}</div>
            </div>
        `).join("");
    } catch (err) {
        console.error("Failed to load notes:", err);
    }
}

function setupEventListeners() {
    // Filters
    const routeFilter = document.getElementById("filter-route");
    const statusFilter = document.getElementById("filter-status");

    function applyFilters() {
        const selRoute = routeFilter.value;
        const selStatus = statusFilter.value;

        let filtered = allRecords;
        if (selRoute) filtered = filtered.filter(r => r.route === selRoute);
        if (selStatus) filtered = filtered.filter(r => r.flagged === selStatus);

        renderTable(filtered);
    }

    if (routeFilter) routeFilter.addEventListener("change", applyFilters);
    if (statusFilter) statusFilter.addEventListener("change", applyFilters);

    // Re-run pipeline button
    const btnRerun = document.getElementById("btn-run-pipeline");
    if (btnRerun) {
        btnRerun.addEventListener("click", async () => {
            btnRerun.disabled = true;
            btnRerun.innerHTML = '<span>Processing...</span>';
            try {
                await fetch("/api/pipeline/run", { method: "POST" });
                await loadDashboardData();
            } finally {
                btnRerun.disabled = false;
                btnRerun.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.19"/></svg><span>Re-run Pipeline</span>';
            }
        });
    }

    // Chat form submission
    const chatForm = document.getElementById("chat-form");
    const chatInput = document.getElementById("chat-input");
    const btnSend = document.getElementById("btn-send-chat");

    if (chatForm) {
        chatForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const msg = chatInput.value.trim();
            if (!msg) return;

            // 1. Append User Message
            appendChatMessage("user", msg);
            chatInput.value = "";
            chatInput.disabled = true;
            if (btnSend) btnSend.disabled = true;

            // 2. Display AI Thinking & Framing Spinner
            const spinnerId = showChatSpinner();

            try {
                const res = await fetch("/api/chat", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ message: msg })
                });
                const data = await res.json();
                
                // 3. Remove spinner and append assistant response
                removeChatSpinner(spinnerId);
                appendChatMessage("assistant", data.response || "No response received.");
            } catch (err) {
                removeChatSpinner(spinnerId);
                appendChatMessage("assistant", "Error connecting to AI assistant.");
            } finally {
                chatInput.disabled = false;
                if (btnSend) btnSend.disabled = false;
                chatInput.focus();
            }
        });
    }
}

function showChatSpinner() {
    const container = document.getElementById("chat-messages");
    if (!container) return null;

    const spinnerDiv = document.createElement("div");
    const spinnerId = "spinner-" + Date.now();
    spinnerDiv.id = spinnerId;
    spinnerDiv.className = "message msg-assistant msg-loading";
    spinnerDiv.innerHTML = `
        <div class="spinner-dots">
            <span></span>
            <span></span>
            <span></span>
        </div>
        <span class="framing-text">Framing grounded answer...</span>
    `;
    container.appendChild(spinnerDiv);
    container.scrollTop = container.scrollHeight;
    return spinnerId;
}

function removeChatSpinner(spinnerId) {
    if (!spinnerId) return;
    const el = document.getElementById(spinnerId);
    if (el) el.remove();
}

function appendChatMessage(sender, text) {
    const container = document.getElementById("chat-messages");
    if (!container) return;

    const div = document.createElement("div");
    div.className = `message msg-${sender}`;
    div.textContent = text;
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
}

function askPreset(question) {
    const input = document.getElementById("chat-input");
    if (input) {
        input.value = question;
        document.getElementById("chat-form").dispatchEvent(new Event("submit"));
    }
}

function escapeHtml(str) {
    if (!str) return "";
    return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}
