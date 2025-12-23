# Robert Mail AI

**Robert** is a personal AI email assistant that runs locally on your machine. It connects to your Gmail via the official API, reads your unread emails, and uses a local LLM to summarize them, categorize them, and even "skip" unimportant ones for you.

## Features ✨

-   **Zero-Inbox Focus**: Shows you one email at a time to help you process your inbox efficiently.
-   **AI Summaries**: Instantly get a one-sentence summary of long emails.
-   **Smart Skipping**: Robert learns your preferences (rules) and automatically marks unimportant emails (like newsletters or promotions) as read.
-   **Activity Log**: detailed log of what Robert read and skipped, with clickable entries to verify his decisions.
-   **Secure**: Uses **OAuth 2.0** to verify with Google. Your password specifically never touches this app.
-   **Local**: Runs on your machine. Data stays with you.

## Screenshots 📸

| Main Feed | Activity Log |
| :---: | :---: |
| ![Main Feed](assets/screenshot1.jpg) | ![Activity Log](assets/screenshot2.jpg) |

## Setup 🛠️

### Prerequisites
-   Python 3.8+
-   A Google Cloud Project with the **Gmail API** enabled.
-   An OAuth 2.0 Client ID (`credentials.json`) file from Google Cloud.

### Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/yourusername/robert-mail.git
    cd robert-mail
    ```

2.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Configure Credentials:**
    -   Place your `credentials.json` file in the root directory.
    -   **Important:** Do NOT share or commit this file.

4.  **Run the App:**
    ```bash
    python app.py
    ```
    Open your browser to `http://localhost:3000`.

## Tech Stack 💻
-   **Backend:** Flask (Python)
-   **Frontend:** Vanilla JS, HTML5, CSS3
-   **Auth:** Google OAuth 2.0
-   **API:** Gmail API (REST)

## License
MIT