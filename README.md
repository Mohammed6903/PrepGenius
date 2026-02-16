# Vision Backend

This is the backend service for the Vision project. It provides core functionality for processing, validating, and serving data for the application.

## Features
- Python backend using FastAPI and google ADK
- Modular code structure for easy maintenance
- Validation utilities for environment and data
- Static file serving for frontend assets

## Project Structure
```
vision/
├── main.py                # Entry point for the backend server
├── pyproject.toml         # Python project dependencies and metadata
├── src/
│   ├── agent.py           # Core agent logic
│   └── validation/
│       └── environment.py # Environment validation utilities
├── static/
│   ├── index.html         # Static HTML file
│   └── js/                # Static JS assets
├── __pycache__/           # Python cache files (auto-generated)
└── README.md              # Project documentation
```

## Getting Started

### Prerequisites
- Python 3.9+
- (Recommended) Create a virtual environment:
  ```bash
  python3 -m venv venv
  source venv/bin/activate
  ```

### Installation
1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   # or, if using pyproject.toml
   pip install .
   ```

2. Copy the example environment file and configure as needed:
   ```bash
   cp .env.example .env
   # Edit .env with your settings
   ```

### Running the Server

```bash
python main.py
# or, if using FastAPI/uvicorn:
uvicorn main:app --reload
```

The backend will be available at `http://localhost:8000` by default.

### Serving Static Files
Static files (HTML, JS) are served from the `static/` directory.

## Development
- Source code is in the `src/` directory.
- Add new features or validation logic in appropriate modules.

## Testing
Add your tests in a `tests/` directory (not included by default).
