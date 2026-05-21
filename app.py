from flask import Flask, render_template, jsonify, request, redirect, session, url_for
from email_client import EmailClient
from robert import Robert
from urllib.parse import unquote
import logging
import threading
import time
import json
import os
import pathlib
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from config import Config

app = Flask(__name__)
app.secret_key = 'somesecretkeyforrobert' # Fixed key for dev stability
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1' # For local testing (HTTP)

logging.basicConfig(level=logging.INFO)

# Global Manager for connected users
class UserManager:
    def __init__(self, email, credentials=None):
        self.email = email
        self.credentials = credentials
        # Ensure data directory exists for user-specific files
        os.makedirs(f"data/{email}", exist_ok=True)
        self.robert = Robert(email)
        self.client = EmailClient()
        self.buffer = []
        self.buffer_file = f"data/{email}/buffer.json"
        self.logs_file = f"data/{email}/logs.json"
        self.token_file = f"data/{email}/token.json"
        self.stats_file = f"data/{email}/stats.json"
        self.lock = threading.Lock()
        self.running = True
        self.stats = {"skipped_total": 0}
        self.load_stats()
        
        self.needs_reevaluation = False

        
        # Load credentials if not provided
        if not self.credentials:
            self.load_credentials()

        # Load buffer from disk
        self.load_buffer()
        
        # Start background worker
        self.thread = threading.Thread(target=self.background_worker)
        self.thread.daemon = True
        self.thread.start()

    def load_stats(self):
        if os.path.exists(self.stats_file):
            try:
                with open(self.stats_file, 'r') as f:
                    self.stats = json.load(f)
            except:
                pass

    def save_stats(self):
        try:
            with open(self.stats_file, 'w') as f:
                json.dump(self.stats, f)
        except Exception as e:
            logging.error(f"Failed to save stats: {e}")

    def load_credentials(self):
        if os.path.exists(self.token_file):
            self.credentials = Credentials.from_authorized_user_file(self.token_file, Config.SCOPES)

    def save_credentials(self):
        if self.credentials:
            with open(self.token_file, 'w') as token:
                token.write(self.credentials.to_json())

    def load_buffer(self):
        if os.path.exists(self.buffer_file):
            try:
                with open(self.buffer_file, 'r') as f:
                    self.buffer = json.load(f)
                    
                # Deduplicate buffer (One-time cleanup for existing users)
                unique_buffer = []
                seen_ids = set()
                for email in self.buffer:
                    # Filter out duplicates AND emails with empty bodies (to fix cached bad data)
                    if email['id'] not in seen_ids and email.get('body', '').strip():
                        unique_buffer.append(email)
                        seen_ids.add(email['id'])
                
                if len(unique_buffer) != len(self.buffer):
                    logging.info(f"Removed {len(self.buffer) - len(unique_buffer)} items (duplicates or empty bodies) from buffer for {self.email}")
                    self.buffer = unique_buffer
                    self.save_buffer()
                    
            except Exception as e:
                logging.error(f"Error loading buffer for {self.email}: {e}")
                self.buffer = []

    def save_buffer(self):
        # Ensure directory exists before saving
        os.makedirs(os.path.dirname(self.buffer_file), exist_ok=True)
        with open(self.buffer_file, 'w') as f:
            json.dump(self.buffer, f)

    def log_action(self, action, email_data):
        """Append an action log entry to logs.json"""
        if action == "SKIPPED":
            self.stats["skipped_total"] = self.stats.get("skipped_total", 0) + 1
            self.save_stats()

        entry = {
            "timestamp": time.time(),
            "action": action,
            "id": email_data.get('id'),
            "subject": email_data.get('subject'),
            "sender": email_data.get('sender'),
            "reason": email_data.get('reason') if action == "SKIPPED" else None
        }
        
        logs = []
        if os.path.exists(self.logs_file):
            try:
                with open(self.logs_file, 'r') as f:
                    logs = json.load(f)
            except:
                pass
        
        # Keep last 100 logs
        logs.insert(0, entry)
        logs = logs[:100]
        
        try:
            with open(self.logs_file, 'w') as f:
                json.dump(logs, f)
        except Exception as e:
            logging.error(f"Failed to save log: {e}")

    def background_worker(self):
        logging.info(f"Background worker started for {self.email}")
        while self.running:
            try:
                # Refresh creds if needed
                if self.credentials and self.credentials.expired and self.credentials.refresh_token:
                    self.credentials.refresh(Request())
                    self.save_credentials()

                if not self.credentials or not self.credentials.valid:
                    logging.warning(f"Credentials invalid for {self.email}, pausing worker.")
                    time.sleep(60)
                    continue

                if getattr(self, 'needs_reevaluation', False):
                    self.needs_reevaluation = False
                    logging.info(f"Re-evaluating buffer for {self.email} due to memory update")
                    with self.lock:
                        items_to_check = list(self.buffer)
                        self.buffer = []
                    
                    for email in items_to_check:
                        analysis = self.robert.process_email(email)
                        email.update(analysis)
                        if email.get('skip', False):
                            logging.info(f"Skipping {email['subject']} (Reason: {email.get('reason')}) after re-eval")
                            self.log_action("SKIPPED", email)
                            try:
                                self.client.mark_as_read(email['id'], self.credentials)
                            except Exception as e:
                                logging.error(f"Failed to mark as read: {e}")
                        else:
                            with self.lock:
                                self.buffer.append(email)
                    
                    with self.lock:
                        self.save_buffer()
                    
                    continue

                # Maintain buffer size of 30
                if len(self.buffer) < 30:
                    with self.lock:
                        current_ids = [e['id'] for e in self.buffer]
                        
                    # Fetch batch of 10, excluding what we already have
                    # Pass credentials instead of password
                    new_emails = self.client.fetch_unread_emails(
                        self.credentials, 
                        limit=30, 
                        exclude_ids=current_ids
                    )
                    
                    if new_emails:
                        added_count = 0
                        for email in new_emails:
                            if len(self.buffer) >= 30:
                                break
                                
                            # Double check duplicate
                            with self.lock:
                                if any(e['id'] == email['id'] for e in self.buffer):
                                    continue
                            
                            # Process
                            analysis = self.robert.process_email(email)
                            email.update(analysis)
                            
                            # Check Skip Logic
                            if email.get('skip', False):
                                logging.info(f"Skipping {email['subject']} (Reason: {email.get('reason')})")
                                self.log_action("SKIPPED", email)
                                self.client.mark_as_read(email['id'], self.credentials)
                            else:
                                with self.lock:
                                    if not any(e['id'] == email['id'] for e in self.buffer):
                                        self.buffer.append(email)
                                        added_count += 1
                        
                        if added_count > 0:
                            with self.lock:
                                self.save_buffer()
                    else:
                        # No new emails found, wait a bit longer
                        time.sleep(10) 
                        
                else:
                    # Buffer full, chill
                    time.sleep(5)
                    
            except Exception as e:
                logging.error(f"Worker Error for {self.email}: {e}")
                time.sleep(10)
            
            # Small delay between loops
            time.sleep(1)

    def get_current_email(self):
        """Peek at the current email (persistent until done)"""
        with self.lock:
            if self.buffer:
                return self.buffer[0]
            return None

    def mark_done(self, email_id):
        """Consumes the email and marks as read"""
        with self.lock:
            if self.buffer and self.buffer[0]['id'] == email_id:
                email = self.buffer.pop(0)
                self.save_buffer()
                self.log_action("READ", email)
                
                # Mark as read in Gmail
                try:
                    self.client.mark_as_read(email['id'], self.credentials)
                except Exception as e:
                    logging.error(f"Failed to mark as read in Gmail: {e}")
            else:
                logging.warning(f"Attempted to mark done email {email_id} but top is {self.buffer[0]['id'] if self.buffer else 'None'}")


# Store user managers by email
active_users = {}
users_lock = threading.Lock()

def get_user_manager(email):
    with users_lock:
        if email not in active_users:
            active_users[email] = UserManager(email)
    return active_users[email]

@app.route('/')
def index():
    if 'email' not in session:
        return render_template('index.html', user=None)
    return render_template('index.html', user=session['email'])

@app.route('/auth/google')
def login():
    # prompt='consent' is critical to force Google to return a refresh_token every time.
    # Without it, we only get it on the very first authorization.
    authorization_url, state = _get_flow().authorization_url(
        access_type='offline',
        prompt='consent',
        include_granted_scopes='true')
    session['state'] = state
    return redirect(authorization_url)

@app.route('/oauth2callback')
def oauth2callback():
    state = session['state']
    flow = _get_flow()
    flow.fetch_token(authorization_response=request.url)

    credentials = flow.credentials
    
    # Get user email
    # We need to build a service temporarily to get the profile
    from googleapiclient.discovery import build
    service = build('gmail', 'v1', credentials=credentials)
    profile = service.users().getProfile(userId='me').execute()
    email_address = profile['emailAddress']
    
    session['email'] = email_address
    
    # Initialize UserManager and save creds
    manager = get_user_manager(email_address)
    manager.credentials = credentials
    manager.save_credentials()
    
    return redirect(url_for('index'))

@app.route('/auth/logout')
def logout():
    session.pop('email', None)
    return redirect(url_for('index'))

def _get_flow():
    # Helper to create flow
    flow = Flow.from_client_secrets_file(
        Config.GOOGLE_CLIENT_SECRETS_FILE,
        scopes=Config.SCOPES)
    flow.redirect_uri = url_for('oauth2callback', _external=True)
    return flow

@app.route('/api/emails')
def get_emails():
    email_user = session.get('email')

    if not email_user:
        return jsonify({"error": "Please login"}), 401

    try:
        manager = get_user_manager(email_user)
        
        # Return next from buffer WITHOUT popping (Peek)
        # Check for exclude_id (optimization for non-blocking UI)
        exclude_id = request.args.get('exclude_id')
        
        emails_to_return = []
        with manager.lock:
            emails_to_return = list(manager.buffer)
            if exclude_id:
                emails_to_return = [e for e in emails_to_return if e['id'] != exclude_id]
        
        return jsonify({"emails": emails_to_return, "skipped": []})

    except Exception as e:
        logging.error(f"Fetch Error: {e}")
        # Identify auth errors specifically if possible
        if "invalid_grant" in str(e) or "Token has been expired" in str(e):
             return jsonify({"error": "Session expired, please re-login"}), 401
        return jsonify({"error": str(e)}), 500

@app.route('/api/logs')
def get_logs():
    email_user = session.get('email')

    if not email_user:
        return jsonify({"error": "Please login"}), 401
    
    manager = get_user_manager(email_user)
    
    logs = []
    if os.path.exists(manager.logs_file):
        try:
            with open(manager.logs_file, 'r') as f:
                logs = json.load(f)
        except:
            pass
            
    return jsonify({
        "logs": logs,
        "stats": manager.stats
    })

@app.route('/api/mark_done', methods=['POST'])
def mark_done():
    data = request.json
    email_id = data.get('id')
    
    email_user = session.get('email')

    if not email_user:
        return jsonify({"error": "Please login"}), 401
    
    try:
        manager = get_user_manager(email_user)
        # Mark as done (Pop from buffer + Mark as Read in Gmail)
        manager.mark_done(email_id)
        return jsonify({"status": "success"})
    except Exception as e:
        logging.error(f"Mark Done Error: {e}")
        return jsonify({"error": str(e)}), 500



@app.route('/api/memory', methods=['POST'])
def update_memory():
    data = request.json
    
    email_user = session.get('email')

    if not email_user:
        return jsonify({"error": "Please login"}), 401
    
    manager = get_user_manager(email_user)

    text = data.get('text')
    if text:
        manager.robert.update_memory(text)
        manager.needs_reevaluation = True
        
    return jsonify({"status": "success"})

@app.route('/api/mark_read', methods=['POST'])
def mark_read():
    data = request.json
    email_id = data.get('id')
    email_user = session.get('email')

    if not email_user:
        return jsonify({"error": "Please login"}), 401

    if email_id:
        try:
            # We can still use the raw client, or manager.client
            manager = get_user_manager(email_user)
            manager.client.mark_as_read(email_id, manager.credentials)
            return jsonify({"status": "success"})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
            
    return jsonify({"error": "No ID provided"}), 400

@app.route('/api/email/<email_id>')
def get_single_email(email_id):
    email_user = session.get('email')

    if not email_user:
        return jsonify({"error": "Please login"}), 401
    
    try:
        manager = get_user_manager(email_user)
        email_data = manager.client.fetch_email_by_id(email_id, manager.credentials)
        
        # Add a flag to indicate this is a historical view
        email_data['is_history'] = True
        
        # Try to parse summary memory if available? For now just raw email.
        return jsonify(email_data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=3000)
