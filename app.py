from flask import Flask, render_template, jsonify, request
from email_client import EmailClient
from robert import Robert
from urllib.parse import unquote
import logging
import threading
import time
import json
import os

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# Global Manager for connected users
class UserManager:
    def __init__(self, email, password):
        self.email = email
        self.password = password
        # Ensure data directory exists for user-specific files
        os.makedirs(f"data/{email}", exist_ok=True)
        self.robert = Robert(email)
        self.client = EmailClient()
        self.buffer = []
        self.buffer_file = f"data/{email}/buffer.json"
        self.logs_file = f"data/{email}/logs.json"
        self.lock = threading.Lock()
        self.running = True
        
        # Load buffer from disk
        self.load_buffer()
        
        # Start background worker
        self.thread = threading.Thread(target=self.background_worker)
        self.thread.daemon = True
        self.thread.start()

    def load_buffer(self):
        if os.path.exists(self.buffer_file):
            try:
                with open(self.buffer_file, 'r') as f:
                    self.buffer = json.load(f)
                    
                # Deduplicate buffer (One-time cleanup for existing users)
                unique_buffer = []
                seen_ids = set()
                for email in self.buffer:
                    if email['id'] not in seen_ids:
                        unique_buffer.append(email)
                        seen_ids.add(email['id'])
                
                if len(unique_buffer) != len(self.buffer):
                    logging.info(f"Removed {len(self.buffer) - len(unique_buffer)} duplicates from buffer for {self.email}")
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
                # Maintain buffer size of 10
                if len(self.buffer) < 10:
                    with self.lock:
                        current_ids = [e['id'] for e in self.buffer]
                        
                    # Fetch batch of 10, excluding what we already have
                    new_emails = self.client.fetch_unread_emails(
                        self.email, 
                        self.password, 
                        limit=10, 
                        exclude_ids=current_ids
                    )
                    
                    if new_emails:
                        added_count = 0
                        for email in new_emails:
                            if len(self.buffer) >= 10:
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
                                self.client.mark_as_read(email['id'], self.email, self.password)
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
                    self.client.mark_as_read(email['id'], self.email, self.password)
                except Exception as e:
                    logging.error(f"Failed to mark as read in Gmail: {e}")
            else:
                # Fallback: if ID doesn't match top, maybe search and remove?
                # For now, strict: must be top of queue. 
                # Or if user clicked done on something that isn't top (race condition), just ignore?
                logging.warning(f"Attempted to mark done email {email_id} but top is {self.buffer[0]['id'] if self.buffer else 'None'}")


# Store user managers by email
active_users = {}
users_lock = threading.Lock()

def get_user_manager(email, password):
    with users_lock:
        if email not in active_users:
            active_users[email] = UserManager(email, password)
        # Update password if changed (re-login)
        active_users[email].password = password
    return active_users[email]

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/emails')
def get_emails():
    email_user = request.cookies.get('email_user')
    email_pass = request.cookies.get('email_pass')

    if not email_user or not email_pass:
        return jsonify({"error": "Missing credentials"}), 401
    
    # Decode and strip
    email_user = unquote(email_user).strip()
    email_pass = unquote(email_pass).strip()

    try:
        manager = get_user_manager(email_user, email_pass)
        
        # Return next from buffer WITHOUT popping (Peek)
        # Check for exclude_id (optimization for non-blocking UI)
        exclude_id = request.args.get('exclude_id')
        
        email = None
        with manager.lock:
            if manager.buffer:
                if exclude_id and len(manager.buffer) > 0 and manager.buffer[0]['id'] == exclude_id:
                     # If the top email is the one we are "pretending" is gone, return the next one
                     if len(manager.buffer) > 1:
                         email = manager.buffer[1]
                else:
                    email = manager.buffer[0]
        
        if email:
            return jsonify({"emails": [email], "skipped": []})
        else:
            return jsonify({"emails": [], "skipped": []}) # buffer empty or fetching

    except Exception as e:
        logging.error(f"Fetch Error: {e}")
        # Identify auth errors specifically if possible, but generic 401 is fine for now
        response = jsonify({"error": str(e)})
        if "AUTHENTICATIONFAILED" in str(e) or "log in" in str(e).lower():
            response.set_cookie('email_user', '', expires=0)
            response.set_cookie('email_pass', '', expires=0)
            return response, 401
        return response, 500

@app.route('/api/logs')
def get_logs():
    email_user = request.cookies.get('email_user')
    email_pass = request.cookies.get('email_pass')

    if not email_user or not email_pass:
        return jsonify({"error": "Missing credentials"}), 401
    
    email_user = unquote(email_user).strip()
    email_pass = unquote(email_pass).strip()
    
    manager = get_user_manager(email_user, email_pass)
    
    logs = []
    if os.path.exists(manager.logs_file):
        try:
            with open(manager.logs_file, 'r') as f:
                logs = json.load(f)
        except:
            pass
            
    return jsonify(logs)

@app.route('/api/mark_done', methods=['POST'])
def mark_done():
    data = request.json
    email_id = data.get('id')
    
    email_user = request.cookies.get('email_user')
    email_pass = request.cookies.get('email_pass')

    if not email_user or not email_pass:
        return jsonify({"error": "Missing credentials"}), 401
    
    email_user = unquote(email_user).strip()
    email_pass = unquote(email_pass).strip()
    
    try:
        manager = get_user_manager(email_user, email_pass)
        # Mark as done (Pop from buffer + Mark as Read in Gmail)
        manager.mark_done(email_id)
        return jsonify({"status": "success"})
    except Exception as e:
        logging.error(f"Mark Done Error: {e}")
        return jsonify({"error": str(e)}), 500



@app.route('/api/memory', methods=['POST'])
def update_memory():
    data = request.json
    
    email_user = request.cookies.get('email_user')
    email_pass = request.cookies.get('email_pass')

    if not email_user or not email_pass:
        return jsonify({"error": "Missing credentials"}), 401
    
    email_user = unquote(email_user).strip()
    email_pass = unquote(email_pass).strip()
    manager = get_user_manager(email_user, email_pass)

    text = data.get('text')
    if text:
        manager.robert.update_memory(text)
        
    return jsonify({"status": "success"})

@app.route('/api/mark_read', methods=['POST'])
def mark_read():
    data = request.json
    email_id = data.get('id')
    email_user = request.cookies.get('email_user')
    email_pass = request.cookies.get('email_pass')

    if not email_user or not email_pass:
        return jsonify({"error": "Missing credentials"}), 401

    email_user = unquote(email_user).strip()
    email_pass = unquote(email_pass).strip()
    # manager = get_user_manager(email_user, email_pass) # Not strictly needed as client is stateless, but good for consistency

    if email_id:
        try:
            # We can still use the raw client, or manager.client
            manager = get_user_manager(email_user, email_pass)
            manager.client.mark_as_read(email_id, email_user, email_pass)
            return jsonify({"status": "success"})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
            
    return jsonify({"error": "No ID provided"}), 400

if __name__ == '__main__':
    app.run(debug=True, port=3000)
