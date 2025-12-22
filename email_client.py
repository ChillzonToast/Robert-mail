import base64
from email.utils import parsedate_to_datetime
from googleapiclient.discovery import build
import logging

class EmailClient:
    def __init__(self):
        pass

    def _get_service(self, credentials):
        return build('gmail', 'v1', credentials=credentials)

    def fetch_unread_emails(self, credentials, limit=10, exclude_ids=None):
        try:
            service = self._get_service(credentials)
            
            # List unread messages
            results = service.users().messages().list(userId='me', q='is:unread', maxResults=limit + (len(exclude_ids) if exclude_ids else 0)).execute()
            messages = results.get('messages', [])
            
            if not messages:
                return []
            
            # Filter excluded IDs
            if exclude_ids:
                exclude_set = set(exclude_ids)
                messages = [m for m in messages if m['id'] not in exclude_set]
            
            # Respect limit after filtering
            messages = messages[:limit]
            
            emails = []
            for msg in messages:
                # Get full message details
                msg_detail = service.users().messages().get(userId='me', id=msg['id'], format='full').execute()
                
                payload = msg_detail.get('payload', {})
                headers = payload.get('headers', [])
                
                subject = "No Subject"
                sender = "Unknown Sender"
                date_str = ""
                
                for h in headers:
                    name = h.get('name', '').lower()
                    if name == 'subject':
                        subject = h.get('value')
                    elif name == 'from':
                        sender = h.get('value')
                    elif name == 'date':
                        date_str = h.get('value')
                
                body = self._get_body_from_payload(payload)
                        
                emails.append({
                    "id": msg['id'],
                    "subject": subject,
                    "sender": sender,
                    "body": body[:50000],  # Truncate large bodies
                    "date": date_str
                })
                
            return emails

        except Exception as e:
            logging.error(f"Error fetching emails: {e}")
            raise e

    def _get_body_from_payload(self, payload):
        """Recursively extract text/html or text/plain from payload"""
        body = ""
        mime_type = payload.get('mimeType')
        
        # If it's a simple text part
        if mime_type == 'text/plain' or mime_type == 'text/html':
             if payload.get('body') and payload['body'].get('data'):
                 return base64.urlsafe_b64decode(payload['body']['data']).decode(errors='replace')
        
        # If it has parts, recurse
        if 'parts' in payload:
            # We want to prioritize HTML over Plain Text
            # But parts can be nested. 
            
            # Strategy: look for HTML in any part (recursively), if found return it.
            # Else look for Plain in any part.
            
            # DFS for HTML
            for part in payload['parts']:
                if part.get('mimeType') == 'text/html':
                    if part.get('body') and part['body'].get('data'):
                        return base64.urlsafe_b64decode(part['body']['data']).decode(errors='replace')
                
                # Recurse if multipart
                if 'parts' in part:
                     candidate = self._get_body_from_payload(part)
                     # If we found something good (assuming HTML is likely if it returned non-empty)
                     # But simple recursion might return plain text from a sub-part.
                     # This logic is a bit tricky. 
                     
                     # Better separate: find html part, find text part
                     pass
            
            # If we are here, we didn't find a direct text/html child with data.
            # Let's do a more structured search.
            
            html_body = self._find_part(payload, 'text/html')
            if html_body:
                return html_body
                
            text_body = self._find_part(payload, 'text/plain')
            if text_body:
                return text_body
                
        # Handle case where body is at top level but mimetype isn't explicit or we missed it
        if payload.get('body') and payload['body'].get('data'):
             return base64.urlsafe_b64decode(payload['body']['data']).decode(errors='replace')
             
        return ""

    def _find_part(self, payload, target_mime_type):
        """DFS to find a specific mime type"""
        if payload.get('mimeType') == target_mime_type:
            if payload.get('body') and payload['body'].get('data'):
                return base64.urlsafe_b64decode(payload['body']['data']).decode(errors='replace')
        
        if 'parts' in payload:
            for part in payload['parts']:
                found = self._find_part(part, target_mime_type)
                if found:
                    return found
        return None

    def mark_as_read(self, email_id, credentials):
        try:
            service = self._get_service(credentials)
            service.users().messages().modify(
                userId='me',
                id=email_id,
                body={'removeLabelIds': ['UNREAD']}
            ).execute()
        except Exception as e:
            logging.error(f"Error marking as read: {e}")
            raise e
    def fetch_email_by_id(self, email_id, credentials):
        try:
            service = self._get_service(credentials)
            msg_detail = service.users().messages().get(userId='me', id=email_id, format='full').execute()
            
            payload = msg_detail.get('payload', {})
            headers = payload.get('headers', [])
            
            subject = "No Subject"
            sender = "Unknown Sender"
            date_str = ""
            
            for h in headers:
                name = h.get('name', '').lower()
                if name == 'subject':
                    subject = h.get('value')
                elif name == 'from':
                    sender = h.get('value')
                elif name == 'date':
                    date_str = h.get('value')
            
            body = self._get_body_from_payload(payload)
                    
            return {
                "id": msg_detail['id'],
                "subject": subject,
                "sender": sender,
                "body": body[:50000], 
                "date": date_str
            }
        except Exception as e:
            logging.error(f"Error fetching email {email_id}: {e}")
            raise e
