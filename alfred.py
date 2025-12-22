import requests
import time
import json
import os
import re
from datetime import datetime


def textOne(prompt: str) -> str:
    baseurl = "https://tools.askyourpdf.com/job/generate"

    # Load parameters from aypdf.json
    with open("aypdf.json", "r") as f:
        json_data = json.load(f)

    # Update the text field with the provided prompt
    json_data["text"] = prompt
    response = requests.post(baseurl, json=json_data, timeout=30)

    # Parse the response to get job_id
    result = json.loads(response.text)
    job_id = result["job_id"]

    # Poll for status every 0.25 seconds
    status_url = f"https://tools.askyourpdf.com/job/generate/{job_id}"
    while True:
        status_response = requests.get(status_url, timeout=30)
        status_result = json.loads(status_response.text)

        if status_result["status"] != "PROCESSING":
            return status_result["response"]["text"]

        time.sleep(0.25)


def load_memory():
    """Load memory from data/memory.txt, create if doesn't exist"""
    os.makedirs("data", exist_ok=True)
    memory_path = "data/memory.txt"

    if os.path.exists(memory_path):
        with open(memory_path, "r") as f:
            return f.read().strip()
    else:
        return ""


def parse_and_execute_response(
    response: str, conversation_filepath: str, conversation_log: str
):
    """Parse the response and execute p, w, and s operations"""
    print_messages = []

    # Find all <w(filename)>content</w> patterns
    write_pattern = r"<w\(([^)]+)\)>(.*?)</w>"
    write_matches = re.findall(write_pattern, response, re.DOTALL)

    for filename, content in write_matches:
        # Save to data folder
        filepath = os.path.join("data", filename)
        with open(filepath, "w") as f:
            f.write(content)

    # Find all <p>content</p> patterns
    print_pattern = r"<p>(.*?)</p>"
    print_matches = re.findall(print_pattern, response, re.DOTALL)

    for message in print_matches:
        print_messages.append(message.strip())

    # Find all <s>content</s> patterns and save conversation
    save_pattern = r"<s>(.*?)</s>"
    save_matches = re.findall(save_pattern, response, re.DOTALL)

    if save_matches:
        # Save the full conversation log to the timestamped file
        with open(conversation_filepath, "w") as f:
            f.write(save_matches[0] + "\n----------\n" + conversation_log)

    return print_messages


prompt = """You are a human-like assistant named Alfred.
Your task is to answer the user's question/prompt with context to the conversation you had with the user.
You will also be given a file 'memory.txt' with context about the user and their preferences (reflects personality, not day to day things), which you can edit if it needs any addition or change.
Do not add any unnecessary details that doesnt add to user's personality. This file is to be used for months. Never use the words 'tomorrow' or 'next week', instead use 'Monday 25th September' etc.

Your conversation has to be summarized and stored in files. Use the necessary functions to do so.

You can use these operations as output:
'p': prints to the monitor and adds to the conversation.
'w(filename)': writes content to the filename.
's': saves the conversation to a file.

Example input-output format:
    Contents of memory.txt:
    User's name is XXX, He is X years old.

    conversation-
    User:I like dogs, cats are kind of cute too.

    output-
    <w(memory.txt)>User's name is XXX, He is X years old.User prefers cats over dogs</w>
    <p>Got it! Interested to adopt a cat anytime soon sir?</p>
    <s>User mentioned he prefers dogs over cats.</s>
End of Example

If incognito mode is enabled, do not edit any files at all.

Contents of memory.txt:
{memory}

Time: {curtime}
Here is the conversation:

Alfred: {greeting}

{conversation}"""

if __name__ == "__main__":
    # Determine greeting based on time of day
    current_hour = datetime.now().hour
    if current_hour < 12:
        greeting = "Good morning sir! How may I help you today?"
    elif current_hour < 17:
        greeting = "Good afternoon sir! How may I help you today?"
    else:
        greeting = "Good evening sir! How may I help you today?"

    print(f"Alfred: {greeting}\n")
    conversation_log = ""

    # Create timestamp filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    conversation_filepath = os.path.join("data", "conversations", f"{timestamp}.txt")

    while True:
        question = input("User: ")
        conversation_log += f"User: {question}\n\n"

        # Load current memory and format prompt
        memory_content = load_memory()
        current_prompt = prompt.format(
            memory=memory_content,
            conversation=conversation_log,
            curtime=datetime.now().strftime("%A, %Y-%m-%d %H:%M:%S"),
            greeting=greeting,
        )

        # Get response from API
        response = textOne(current_prompt)

        # Parse and execute the response
        print_messages = parse_and_execute_response(
            response, conversation_filepath, conversation_log
        )

        # Print the messages to user
        for message in print_messages:
            print(f"Alfred: {message}")

        # Add Alfred's response to conversation log (use the printed messages)
        if print_messages:
            alfred_response = " ".join(print_messages)
            conversation_log += f"Alfred: {alfred_response}\n\n"
