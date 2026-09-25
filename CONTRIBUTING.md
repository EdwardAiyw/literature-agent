# Contributing and beta feedback

Literature Agent is a Windows desktop application. Please read [README.md](README.md) for setup and [TEST_GUIDE.md](TEST_GUIDE.md) for the acceptance checklist.

For a bug, use the GitHub bug report template. Include the version, Windows and browser versions, reproduction steps, expected and actual results, and a run ID if relevant. Remove API keys, SMTP credentials, email addresses, paper content you cannot share, and personal data from screenshots and logs.

For development, install Python 3.12 and Node.js 22, then run:

```bash
python -m pip install -e "./backend[dev]"
python -m pytest -q backend/tests
cd frontend
npm ci
npm run build
```

Browser regression tests require Windows Edge and a Python virtual environment at `backend/.venv`; see [Windows release instructions](docs/WINDOWS_RELEASE.md). Open a pull request against `main` with a brief description and test results. Please do not commit generated test results, credentials, or local data.
