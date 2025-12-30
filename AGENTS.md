# Repository Guidelines

## Project Structure & Module Organization
- `app.py` is the main Flask web app (profile setup, mom settings, chat, schedules).
- `templates/` holds Jinja2 HTML pages; `static/` contains `style.css` and `script.js`.
- `prompts/` contains `base_prompt.txt` and `builder.py` for generating the Modelfile prompt.
- `Modelfile` defines the Ollama model; `config/mom_config.json` is generated from UI settings.
- `chat_mom.py` is a simple CLI client for the model; `logs/` stores chat logs.

## Build, Test, and Development Commands
- `ollama serve`: start the local Ollama server (required for all chats).
- `ollama pull dsasai/llama3-elyza-jp-8b`: download the base model.
- `ollama create elyza-mom -f Modelfile`: build the local “mom” model after edits.
- `python3 app.py`: run the Flask dev server at `http://127.0.0.1:5000/`.
- `python3 chat_mom.py`: start the CLI chat client.
- Dependencies are not pinned; install as needed (e.g., `python3 -m pip install flask requests`).

## Coding Style & Naming Conventions
- Python uses 4-space indentation and snake_case for functions and variables.
- Keep Flask routes and helpers in `app.py`; prefer small, single-purpose helpers.
- HTML templates live in `templates/*.html`; keep UI logic minimal in templates.
- Config JSON keys should follow existing structure in `config/mom_config.json`.

## Testing Guidelines
- There is no automated test suite yet.
- Manual smoke checks: run `python3 app.py`, complete profile setup, send a chat, and verify schedule CRUD works.

## Commit & Pull Request Guidelines
- No strict commit convention is enforced; use short, imperative messages (e.g., “Add schedule edit validation”).
- PRs should include a summary, manual test steps, and screenshots for UI changes.

## Security & Configuration Tips
- `app.secret_key` in `app.py` is for local development; replace via environment config for deployment.
- Keep Ollama bound to localhost and avoid committing personal data from `logs/`.
