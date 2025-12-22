import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    EMAIL_USER = os.getenv("EMAIL_USER")
    EMAIL_PASS = os.getenv("EMAIL_PASS")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    IMAP_SERVER = "imap.gmail.com"
    IMAP_PORT = 993
