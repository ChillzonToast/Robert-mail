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

        renderEmailsList();
        
        // Hide loading
        document.getElementById('list-loading').style.display = 'none';

    } catch (e) {
        console.error("Error fetching emails", e);
        document.getElementById('list-loading').innerHTML = "<p>Error loading emails.</p>";
    }
}

async function fetchLogs() {
    try {
        const response = await fetch('/api/logs');
        if (response.ok) {
            const data = await response.json();
            // Handle both legacy (array) and new (object) formats for safety
            const logs = Array.isArray(data) ? data : (data.logs || []);
            const stats = data.stats || {};

            renderLogs(logs);
            renderStats(stats);
        }
    } catch (e) {
        console.error("Error fetching logs", e);
    }
}

function renderStats(stats) {
    const badge = document.getElementById('skipped-badge');
    if (stats.skipped_total !== undefined && stats.skipped_total > 0) {
        badge.innerText = `(${stats.skipped_total} Skipped)`;
        badge.style.display = 'inline';
    } else {
        badge.style.display = 'none';
    }
}

async function loadEmail(id) {
    if (!id) return;

    // UI Feedback
    showListView();
    document.getElementById('list-loading').style.display = 'block';
    document.getElementById('email-list-content').innerHTML = '';

    try {
        const response = await fetch(`/api/email/${id}`);
        if (!response.ok) throw new Error("Failed to fetch");

        const email = await response.json();

        // Override current emails list to show this one
        emails = [email];
        renderEmailsList();
        document.getElementById('list-loading').style.display = 'none';
        
        // Automatically open it since user clicked a log
        showReaderView(email.id);

    } catch (e) {
        console.error("Error loading email", e);
        document.getElementById('list-loading').style.display = 'none';
        document.getElementById('email-list-content').innerHTML = `<div class="empty-state"><h2>Error</h2><p>Could not load email details.</p></div>`;
    }
}

function renderLogs(logs) {
    const consoleBody = document.getElementById('console-body');
    consoleBody.innerHTML = '';

    logs.forEach(entry => {
        const div = document.createElement('div');
        div.className = 'log-entry';

        // Add click handler if ID exists
        if (entry.id) {
            div.onclick = () => loadEmail(entry.id);
            div.title = "Click to view email";
        }

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

function renderEmailsList() {
    const listContent = document.getElementById('email-list-content');
    listContent.innerHTML = '';
    
    if (emails.length === 0) {
        listContent.innerHTML = `
            <div class="empty-state">
                <h2>No Unread Emails</h2>
                <p>You are all caught up!</p>
            </div>`;
        return;
    }
    
    emails.forEach(email => {
        const row = document.createElement('div');
        row.className = 'email-row';
        row.onclick = () => showReaderView(email.id);
        
        const summarySnippet = email.summary || email.body.substring(0, 50) + '...';
        
        row.innerHTML = `
            <div class="sender">${email.sender}</div>
            <div class="subject-snippet">
                <span class="subject">${email.subject}</span>
                <span class="snippet">- ${summarySnippet}</span>
            </div>
            <div class="date">${email.date || ''}</div>
        `;
        listContent.appendChild(row);
    });
}

function showListView() {
    document.getElementById('email-list-content').classList.remove('hidden');
    document.getElementById('email-reader-view').classList.add('hidden');
    
    // Reset Sidebar
    const content = document.getElementById('sidebar-content');
    content.classList.add('hidden');
    content.style.display = ''; // Clear any inline block style
    document.getElementById('sidebar-placeholder').style.display = 'block';
}

function showReaderView(emailId) {
    const email = emails.find(e => e.id === emailId);
    if (!email) return;
    
    document.getElementById('email-list-content').classList.add('hidden');
    document.getElementById('email-reader-view').classList.remove('hidden');
    
    const readerContent = document.getElementById('email-reader-content');
    readerContent.innerHTML = `
        <div class="email-reader-scroll">
            <div class="email-reader">
                <div class="email-reader-header">
                    <h1>${email.subject}</h1>
                    <div class="meta">
                        <span class="sender">${email.sender}</span>
                        <span class="date">${email.date || ''}</span>
                        <span class="category-tag">${email.category || 'General'}</span>
                    </div>
                </div>
                <div class="email-reader-body" style="padding: 0;">
                    <iframe id="email-iframe" scrolling="no" style="width: 100%; border: none; overflow: hidden; min-height: 200px;" sandbox="allow-same-origin allow-popups"></iframe>
                </div>
            </div>
        </div>
    `;
    
    // Set srcdoc and auto-resize iframe to avoid inner scrollbars
    const iframe = document.getElementById('email-iframe');
    iframe.onload = function() {
        if (iframe.contentWindow && iframe.contentWindow.document) {
            // Set height to scrollHeight + a little padding
            iframe.style.height = (iframe.contentWindow.document.documentElement.scrollHeight + 20) + 'px';
        }
    };
    iframe.srcdoc = formatBody(email.body);
    
    // Store current email globally for actions
    window.currentViewingEmail = email;

    // Update Sidebar
    document.getElementById('sidebar-placeholder').style.display = 'none';
    const content = document.getElementById('sidebar-content');
    content.classList.remove('hidden');
    content.style.display = ''; // Clear any inline none style

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
    const email = window.currentViewingEmail;
    if (!email) return;

    document.getElementById('email-reader-content').innerHTML = '<div class="loading"><div class="spinner"></div><p>Processing...</p></div>';

    // Update memory if user typed something
    updateMemory();

    // Mark as done (Pop from buffer & Mark Read)
    // Fire and forget
    fetch('/api/mark_done', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: email.id })
    }).catch(e => console.error("Error marking done:", e));

    // Remove the current email from the local list
    emails = emails.filter(e => e.id !== email.id);

    // Replenish the list in the background
    fetchEmails();

    // If there is another email in the list, automatically open it
    if (emails.length > 0) {
        showReaderView(emails[0].id);
    } else {
        // Otherwise return to the list view
        showListView();
    }
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

function showLoginModal(message) {
    const modal = document.getElementById('login-modal');
    const msgEl = document.getElementById('login-error');
    if (message) {
        msgEl.innerText = message;
    } else {
        msgEl.innerText = "";
    }
    modal.classList.remove('hidden');
}

function logout() {
    window.location.href = '/auth/logout';
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
    // Poll emails every 10 seconds
    setInterval(fetchEmails, 10000);
});

function toggleConsole() {
    const drawer = document.getElementById('console-drawer');
    drawer.classList.toggle('expanded');
    const icon = drawer.querySelector('.toggle-icon');
    icon.style.transform = drawer.classList.contains('expanded') ? 'rotate(180deg)' : 'rotate(0deg)';
}
