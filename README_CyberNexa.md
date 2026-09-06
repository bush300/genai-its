# CyberNexa – Setup, Usage and Deployment Guide

CyberNexa is a secure, AI-powered Intelligent Tutoring System (ITS) for cybersecurity education.  
The prototype uses Streamlit for the user interface, Firebase Firestore for persistent data, and configurable LLM providers including Groq, Ollama and OpenAI.

---

## 1. Prerequisites

Recommended local environment:

- Python 3.11 or 3.12
- Git
- Internet connection for cloud LLM providers
- Docker Desktop for container / Blue-Green deployment
- Ollama only when using a local LLM

> Python 3.11 or 3.12 is recommended for the current dependency set.

---

## 2. Clone the Repository

```bash
git clone https://github.com/bush300/genai-its.git
cd genai-its
```

Make sure you are using the latest `main` branch:

```bash
git switch main
git pull --ff-only origin main
```

---

## 3. Create a Virtual Environment

### Windows

```bash
python -m venv .venv
.venv\Scripts\activate
```

### macOS / Linux

```bash
python -m venv .venv
source .venv/bin/activate
```

---

## 4. Install Dependencies

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Troubleshooting: If you encounter a version conflict or error while installing the requirements, manually install the Gemini SDK first by running python -m pip install google-genai

---

## 5. Configure Environment and Secrets

CyberNexa keeps private credentials outside the source code.

Create a local `.env` file using `.env.example` as a guide.

Also create:

```text
.streamlit/secrets.toml
```

using:

```text
.streamlit/secrets.example.toml
```

as a guide.

Do **not** commit real API keys, Firebase credentials, `.env`, or `secrets.toml` to GitHub.

---

## 6. Validate Configuration

Before starting the application, run:

```bash
python 1.5_security/config_validator.py
```

A valid configuration should return:

```text
[OK] Configuration validation passed.
```

---

## 7. Run Automated Tests

Run the official project test suite:

```bash
python -m pytest tests -q
```

---

## 8. Run CyberNexa Locally

Start the Streamlit application with:

```bash
python -m streamlit run 1.1_interface/streamlit_app.py
```

Streamlit will display the local application URL in the terminal.

The application provides separate Student and Teacher portals.

---

## 9. LLM Provider Configuration

CyberNexa supports:

- **Groq** – cloud provider
- **Ollama** – local provider
- **OpenAI** – configurable cloud provider

The active provider is selected through the `LLM_PROVIDER` environment variable.

Example:

```env
LLM_PROVIDER=groq
```

To use Ollama locally:

```env
LLM_PROVIDER=ollama
```

Provider-specific model and governance configuration is maintained in:

```text
config/llm_config.yaml
```

The provider can be changed without modifying the main application code.

---

## 10. Local Ollama Setup

Install Ollama separately, then download the local model:

```bash
ollama pull llama3.2
```

Confirm that it is available:

```bash
ollama list
```

Then set:

```env
LLM_PROVIDER=ollama
```

A provider smoke test can be run with:

```bash
python 1.3_models/quick_test.py
```

---

## 11. Docker / Blue-Green Deployment

CyberNexa includes Blue-Green deployment infrastructure using Docker Compose and Nginx.

- **Blue** represents the current stable application version.
- **Green** represents the new candidate version.
- Nginx routes traffic to the active deployment slot.
- Health checks are used before switching traffic.
- Traffic can be rolled back to Blue if Green fails.

### Start the Blue and Green services

```bash
docker compose -f deploy/compose.blue-green.yml up --build -d
```

### Check service status

```bash
docker compose -f deploy/compose.blue-green.yml ps
```

### View logs

```bash
docker compose -f deploy/compose.blue-green.yml logs --tail=100
```

### Switch traffic to Green

From Git Bash or another Bash-compatible shell:

```bash
bash deploy/switch-slot.sh green
```

### Check the active deployment slot

```bash
curl http://localhost:8080/deployment-slot
```

Expected after switching:

```text
green
```

### Roll back to Blue

```bash
bash deploy/switch-slot.sh blue
```

Check again:

```bash
curl http://localhost:8080/deployment-slot
```

Expected:

```text
blue
```

### Stop the deployment

```bash
docker compose -f deploy/compose.blue-green.yml down -v
```

---

## 12. CI/CD

GitHub Actions is used to provide automated quality and deployment checks.

The CI workflow includes:

- configuration validation
- Python syntax / compilation checks
- automated tests
- checks to prevent private credential files from being tracked

The Blue-Green workflow validates:

- container build
- service startup
- health checks
- initial routing
- traffic switching
- rollback

---

## 13. Security and Governance

CyberNexa includes governance controls around LLM usage, including:

- request-rate limiting
- daily request limits
- cost-budget controls
- input sanitisation
- output guardrails
- audit logging integration

These controls help reduce misuse, unexpected API usage and exposure of restricted information.

---

## 14. Known Limitation

The Blue-Green deployment infrastructure has passed automated CI validation for build, health checks, traffic switching and rollback.

Manual end-to-end Docker verification using the complete live Firebase configuration, private secrets and full Student / Teacher workflows is still being finalised. Do not commit local credential files when performing this test.

---

## 15. Quick Command Reference

```bash
# Validate configuration
python 1.5_security/config_validator.py

# Run tests
python -m pytest tests -q

# Start application
python -m streamlit run 1.1_interface/streamlit_app.py

# Test selected LLM provider
python 1.3_models/quick_test.py

# Check local Ollama models
ollama list

# Start Blue-Green deployment
docker compose -f deploy/compose.blue-green.yml up --build -d

# Check deployment containers
docker compose -f deploy/compose.blue-green.yml ps
```
