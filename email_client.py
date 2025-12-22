import imaplib
import email
from email.header import decode_header
from bs4 import BeautifulSoup
from config import Config
import logging

class EmailClient:
    def __init__(self):
        # No shared state for connection to avoid race conditions
        pass

    def _get_connection(self, email_user, email_pass):
        if not email_user or not email_pass:
            raise ValueError("Email credentials not provided.")
        
        mail = imaplib.IMAP4_SSL(Config.IMAP_SERVER)
        mail.login(email_user, email_pass)
        return mail

    def fetch_unread_emails(self, email_user, email_pass, limit=10, exclude_ids=None):
        mail = None
        try:
            mail = self._get_connection(email_user, email_pass)
            
            mail.select("inbox")
            # Use UID search for stable IDs
            status, messages = mail.uid('search', None, "UNSEEN")
            
            # Helper to handle empty search results safely
            if not messages or not messages[0]:
                return []

            email_ids = messages[0].split()
            
            # Filter out excluded IDs (already in buffer)
            if exclude_ids:
                # ids are bytes in email_ids, but exclude_ids are likely strings
                exclude_set = set(exclude_ids)
                email_ids = [eid for eid in email_ids if eid.decode() not in exclude_set]
            
            emails = []

            # If no emails left after filtering, return empty
            if not email_ids:
                return []

            # Process latest emails first
            for e_id in reversed(email_ids[-limit:]):
                # Use UID fetch
                res, msg_data = mail.uid('fetch', e_id, "(BODY.PEEK[])")
                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        msg = email.message_from_bytes(response_part[1])
                        
                        # Decode subject
                        subject_header = msg["Subject"]
                        if subject_header:
                            subject, encoding = decode_header(subject_header)[0]
                            if isinstance(subject, bytes):
                                subject = subject.decode(encoding if encoding else "utf-8")
                        else:
                            subject = "(No Subject)"
                        
                        # Decode sender
                        from_header = msg.get("From")
                        if from_header:
                            from_val, encoding = decode_header(from_header)[0]
                            if isinstance(from_val, bytes):
                                from_ = from_val.decode(encoding if encoding else "utf-8")
                            else:
                                from_ = from_val
                        else:
                            from_ = "Unknown Sender"
                        
                        # Get body
                        body = ""
                        html_body = None
                        
                        if msg.is_multipart():
                            for part in msg.walk():
                                content_type = part.get_content_type()
                                content_disposition = str(part.get("Content-Disposition"))
                                
                                if "attachment" in content_disposition:
                                    continue

                                payload = part.get_payload(decode=True)
                                if not payload: 
                                    continue
                                    
                                try:
                                    text = payload.decode()
                                except:
                                    text = payload.decode('latin-1') # Fallback
                                    
                                if content_type == "text/plain":
                                    body += text
                                elif content_type == "text/html":
                                    html_body = text
                        else:
                            payload = msg.get_payload(decode=True)
                            if payload:
                                try:
                                    text = payload.decode()
                                except:
                                    text = payload.decode('latin-1')
                                
                                if msg.get_content_type() == "text/html":
                                    html_body = text
                                else:
                                    body = text

                        # Prioritize HTML if available, otherwise use plain text
                        final_body = html_body if html_body else body

                        emails.append({
                            "id": e_id.decode(), # This is the UID
                            "subject": subject,
                            "sender": from_,
                            "body": final_body[:50000],  # Increase limit for HTML
                            "date": msg.get("Date")
                        })
            return emails
        except Exception as e:
            logging.error(f"Error fetching emails: {e}")
            raise e
        finally:
            if mail:
                try:
                    mail.close()
                except:
                    pass
                try:
                    mail.logout()
                except:
                    pass

    def mark_as_read(self, email_id, email_user, email_pass):
        mail = None
        try:
            mail = self._get_connection(email_user, email_pass)
            mail.select("inbox")
            # Use UID store
            mail.uid('store', email_id, "+FLAGS", "\\Seen")
        except Exception as e:
            logging.error(f"Error marking as read: {e}")
            raise e
        finally:
            if mail:
                try:
                    mail.close()
                except:
                    pass
                try:
                    mail.logout()
                except:
                    pass
