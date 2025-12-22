let currentEmailIndex = 0;
let emails = [];
// Removed duplicate listener


async function fetchEmails(excludeId = null) {
    try {
        let url = '/api/emails';
        if (excludeId) {
            url += `?exclude_id=${excludeId}`;
        }
        const response = await fetch(url);

        if (response.status === 401) {
            const errData = await response.json();
            const msg = errData.error || "Please login to continue.";
            showLoginModal(msg);
            document.querySelector('.loading').innerHTML = "<p>Waiting for login...</p>";
            return;
        }

        const data = await response.json();

        // Handle response with emails array (current backend)
        if (data && data.emails && Array.isArray(data.emails)) {
            emails = data.emails;
        }
        // Fallback: Handle single email object response (legacy/alternative)
        else if (data && data.id) {
            emails = [data];
        } else {
            emails = [];
        }

        currentEmailIndex = 0;
        renderCurrentEmail();

    } catch (e) {
        console.error("Error fetching emails", e);
    }
}

async function fetchLogs() {
    try {
        const response = await fetch('/api/logs');
        if (response.ok) {
            const logs = await response.json();
            renderLogs(logs);
        }
    } catch (e) {
        console.error("Error fetching logs", e);
    }
}

function renderLogs(logs) {
    const consoleBody = document.getElementById('console-body');
    consoleBody.innerHTML = '';

    logs.forEach(entry => {
        const div = document.createElement('div');
        div.className = 'log-entry';

        const timeStr = new Date(entry.timestamp * 1000).toLocaleTimeString();

        let content = "";
        if (entry.action === 'SKIPPED') {
            div.classList.add('log-skipped');
            content = `[${timeStr}] SKIPPED: ${entry.subject} (Reason: ${entry.reason})`;
        } else if (entry.action === 'READ') {
            div.classList.add('log-read');
            content = `[${timeStr}] READ: ${entry.subject}`;
        } else {
            content = `[${timeStr}] ${entry.action}: ${entry.subject}`;
        }

        div.innerText = content;
        consoleBody.appendChild(div);
    });
}

function renderCurrentEmail() {
    const feed = document.getElementById('email-feed');
    feed.innerHTML = '';

    if (emails.length === 0) {
        feed.innerHTML = `
            <div class="empty-state">
                <h2>No Unread Emails</h2>
                <p>You are all caught up!</p>
                <button class="btn btn-outline" onclick="fetchEmails()">Refresh</button>
            </div>`;

        document.getElementById('sidebar-content').classList.add('hidden');
        document.getElementById('sidebar-placeholder').style.display = 'block';
        return;
    }

    // We always only have 1 email now [0]
    const email = emails[0];

    // Render Email Card
    const card = document.createElement('div');
    card.className = 'email-reader';
    card.innerHTML = `
        <div class="email-reader-header">
            <h1>${email.subject}</h1>
            <div class="meta">
                <span class="sender">${email.sender}</span>
                <span class="date">${email.date}</span>
                <span class="category-tag">${email.category}</span>
            </div>
        </div>
        <div class="email-reader-body">
            ${formatBody(email.body)}
        </div>
    `;
    feed.appendChild(card);

    // Update Sidebar
    document.getElementById('sidebar-placeholder').style.display = 'none';
    const content = document.getElementById('sidebar-content');
    content.classList.remove('hidden');
    content.style.display = 'block';

    document.getElementById('summary-text').innerText = email.summary || "No summary available.";

    // Show AI Reason if available, or just hide importance badge logic
    const impBadge = document.getElementById('importance-badge');
    impBadge.style.display = 'none'; // logic removed

    document.getElementById('memory-input').value = "";

    // Autofill Logic
    const autofillContainer = document.getElementById('autofill-container');
    const dontBtn = document.getElementById('btn-autofill-dont');
    const alwaysBtn = document.getElementById('btn-autofill-always');

    if (email.dont_show_rule || email.always_show_rule) {
        autofillContainer.classList.remove('hidden');
        autofillContainer.style.display = 'block';

        if (email.dont_show_rule) {
            dontBtn.style.display = 'block';
            dontBtn.dataset.rule = email.dont_show_rule;
        } else {
            dontBtn.style.display = 'none';
        }

        if (email.always_show_rule) {
            alwaysBtn.style.display = 'block';
            alwaysBtn.dataset.rule = email.always_show_rule;
        } else {
            alwaysBtn.style.display = 'none';
        }
    } else {
        autofillContainer.classList.add('hidden');
        autofillContainer.style.display = 'none';
    }
}

function applyAutofill(type) {
    const input = document.getElementById('memory-input');
    const btn = document.getElementById(type === 'dont' ? 'btn-autofill-dont' : 'btn-autofill-always');
    if (btn && btn.dataset.rule) {
        input.value = btn.dataset.rule;
    }
}

function formatBody(text) {
    if (!text) return "";
    return text;
}

// Removed local nextEmail function, we fetch from server now

// Just one main action: Done/Next
async function markRead() {
    const email = emails[0];
    if (!email) return;

    document.getElementById('email-feed').innerHTML = '<div class="loading"><div class="spinner"></div><p>Processing...</p></div>';

    // Update memory if user typed something
    updateMemory();

    // Mark as done (Pop from buffer & Mark Read)
    // Fire and forget (don't await)
    fetch('/api/mark_done', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: email.id })
    }).catch(e => console.error("Error marking done:", e));

    // Immediately fetch next email (excluding current one to prevent race)
    fetchEmails(email.id);
}
async function updateMemory() {
    const text = document.getElementById('memory-input').value;
    if (!text.trim()) return;

    await fetch('/api/memory', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: text })
    });
}

function showLoginModal(msg = "") {
    const modal = document.getElementById('login-modal');
    modal.classList.remove('hidden');
    if (msg) {
        document.getElementById('login-error').innerText = msg;
    }
}

function saveCredentials() {
    const user = document.getElementById('email-user').value;
    const pass = document.getElementById('email-pass').value;

    if (!user || !pass) {
        document.getElementById('login-error').innerText = "Please fill in all fields";
        return;
    }

    document.cookie = `email_user=${encodeURIComponent(user)}; path=/; max-age=31536000`;
    document.cookie = `email_pass=${encodeURIComponent(pass)}; path=/; max-age=31536000`;

    document.getElementById('login-modal').classList.add('hidden');
    document.querySelector('.loading').innerHTML = `<div class="spinner"></div><p>Robert is checking your mail...</p>`;
    fetchEmails();
    fetchLogs();
}

function logout() {
    document.cookie = "email_user=; path=/; max-age=0";
    document.cookie = "email_pass=; path=/; max-age=0";
    location.reload();
}

function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return decodeURIComponent(parts.pop().split(';').shift());
}

document.addEventListener('DOMContentLoaded', () => {
    const user = getCookie('email_user');
    if (user) {
        document.getElementById('user-email-display').innerText = user;
    }
    fetchEmails();
    fetchLogs();

    // Poll logs every 5 seconds
    setInterval(fetchLogs, 5000);
});

function toggleConsole() {
    const drawer = document.getElementById('console-drawer');
    drawer.classList.toggle('expanded');
    const icon = drawer.querySelector('.toggle-icon');
    icon.style.transform = drawer.classList.contains('expanded') ? 'rotate(180deg)' : 'rotate(0deg)';
}
