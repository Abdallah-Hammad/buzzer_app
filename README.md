# Buzzer App

A real-time web application implementing a buzzer system using FastAPI and WebSockets. Ideal for quizzes, game shows, or any scenario where multiple participants need to signal their response quickly, with the order recorded.

## Features

*   **Player Interface:** Allows participants to enter their name and "buzz in".
*   **Admin Interface:** Provides a view of the buzz order and allows the admin to reset the buzzer for a new round.
*   **Real-time Updates:** Uses WebSockets to instantly update the buzz order for all connected clients (players and admins).
*   **Ordered Buzzing:** Accurately records and displays the sequence in which players buzzed.
*   **Name Entry:** Players are prompted to enter their name before joining.
*   **Arabic Interface:** The primary user interface elements are in Arabic.

## Setup & Running

1.  **Clone the repository (if applicable):**
    ```bash
    git clone <repository-url>
    cd buzzer_app
    ```

2.  **Create and activate a virtual environment (recommended):**
    ```bash
    python -m venv venv
    # On Windows
    .\venv\Scripts\activate
    # On macOS/Linux
    source venv/bin/activate
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Run the application:**
    ```bash
    python main.py
    ```
    The server will start, typically on `http://0.0.0.0:8000`.