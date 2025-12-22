import os
import json
import logging
import time
import requests
from config import Config

class Robert:
    def __init__(self, user_email):
        self.user_email = user_email
        self.base_dir = f"data/{user_email}"
        self.memory_file = f"{self.base_dir}/memory.txt"
        self.aypdf_config_path = "aypdf.json"
        
        # Ensure user directory exists
        os.makedirs(self.base_dir, exist_ok=True)
        
        # Initialize Memory
        if not os.path.exists(self.memory_file):
            with open(self.memory_file, "w") as f:
                f.write("")

    def _call_llm(self, prompt):
        """Low-level wrapper for the AskYourPDF API"""
        if not os.path.exists(self.aypdf_config_path):
            logging.error(f"{self.aypdf_config_path} not found.")
            return None

        try:
            with open(self.aypdf_config_path, "r") as f:
                json_data = json.load(f)
            
            baseurl = "https://tools.askyourpdf.com/job/generate"
            json_data["text"] = prompt
            
            # Start Job
            response = requests.post(baseurl, json=json_data, timeout=30)
            if response.status_code != 200:
                logging.error(f"API Error: {response.text}")
                return None
                
            result = response.json()
            if "job_id" not in result:
                logging.error(f"No job_id in response: {result}")
                return None
                
            job_id = result["job_id"]

            # Poll for completion
            status_url = f"https://tools.askyourpdf.com/job/generate/{job_id}"

            # Timeout after 20 seconds
            start_time = time.time()
            while time.time() - start_time < 20:
                status_response = requests.get(status_url, timeout=30)
                status_result = status_response.json()

                if status_result.get("status") != "PROCESSING":
                    return status_result.get("response", {}).get("text", "")

                time.sleep(0.5)

            logging.error("LLM Timed out")
            return None

        except Exception as e:
            logging.error(f"LLM Exception: {e}")
            return None

    def get_memory(self):
        try:
            with open(self.memory_file, 'r') as f:
                return f.read()
        except FileNotFoundError:
            return ""

    def update_memory(self, new_info):
        current = self.get_memory()
        # Simple append logic
        updated = current + "\n- " + new_info
        with open(self.memory_file, 'w') as f:
            f.write(updated)

    def process_email(self, email_data):
        """
        Analyzes email to determine if it should be skipped based on memory.
        """
        memory_content = self.get_memory()
        
        prompt = f"""
        You are Robert, an AI email assistant. 
        
        User Memory (Preferences & Interests):
        {memory_content}
        
        Analyze this email:
        Subject: {email_data['subject']}
        Sender: {email_data['sender']}
        Body: {email_data['body']}
        
        Task:
        1. Summarize the email.
        2. Decide if this email should be SKIPPED based on the User Memory.
           - Skip if the user has indicated they are not interested in this topic or if it's clearly spam/irrelevant to them.
           - Do NOT skip if it's important or matches their interests.
           - If memory is empty, default to NOT skipping (false).
        3. GENERATE AUTOFIL RULES:
           - 'dont_show_rule': Generate a simple, direct rule to BLOCK this type of email (e.g. "Block newsletters from Pinterest"). Do NOT make it conditional (avoid "if...").
           - 'always_show_rule': Generate a simple, direct rule to ALLOW this type of email (e.g. "Always show updates from Pinterest").
           - These are hypothetical user preferences. Even if the email is good, generate a rule to block it for the 'dont_show_rule'.
           - BOTH fields must be populated.
        
        Output valid JSON only. format:
        {{
            "summary": "1-2 sentence summary",
            "skip": true or false,
            "reason": "Short reason for skipping or showing",
            "dont_show_rule": "MANDATORY: Simple rule to BLOCK this email type (e.g. 'Block Pinterest newsletters')",
            "always_show_rule": "MANDATORY: Simple rule to ALLOW this email type (e.g. 'Always show Pinterest updates')"
        }}
        """
        
        llm_response = self._call_llm(prompt)
        
        if not llm_response:
            return {
                "summary": "AI processing failed.",
                "skip": False,
                "reason": "Error"
            }
            
        try:
            clean_text = llm_response.replace("```json", "").replace("```", "").strip()
            return json.loads(clean_text)
        except Exception as e:
            logging.error(f"JSON Parse Error: {e}. Raw: {llm_response}")
            return {
                "summary": "Error parsing AI response.",
                "skip": False,
                "reason": "Parse Error"
            }
