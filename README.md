# Jarvis do Cerrado

Jarvis do Cerrado is a comprehensive home automation and monitoring bot integrated with Telegram.

## Features

- **Home Automation**: Control devices, wake-on-lan, smart home integration.
- **Monitoring**: System status, network scanning, energy monitoring (planned).
- **AI Integration**: Uses Google Generative AI for natural language understanding as a fallback to rule-based logic.
- **Reminders**: Set and manage reminders via chat.
- **Guardian Service**: Background monitoring for network anomalies and system health.

## Project Structure

The project follows a modular structure:

- `src/jarvis/core`: Core logic, including the Brain (AI), Executor, and Rules Engine.
- `src/jarvis/modules`: Capabilities like Network, SmartHome, and System management.
- `src/jarvis/services`: Background services like the Guardian and Collector.
- `src/jarvis/database`: SQLite persistence layer.
- `src/jarvis/nlp`: Natural Language Processing utilities.

## Installation

1. Clone the repository.
2. Install dependencies:
   ```bash
   pip install -e .
   ```
3. Create a `.env` file with your credentials (see `config.py` for required variables).

## Usage

Run the main application:

```bash
python -m jarvis.main
```

## Testing

Run tests with:

```bash
python tests/test_bot_logic.py
```
