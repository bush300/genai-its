# Data flow (DP4 - institutional data sovereignty)

Where student/teacher data goes, and what leaves the institution's own infrastructure.

```mermaid
flowchart LR
    student[Student browser] -->|answer text| app[Streamlit app]
    teacher[Teacher browser] -->|quiz PDF / KB file| app

    app -->|validate_upload + content-safety gate| ingest[Quiz extractor / KB loader]
    app -->|cap_input_length + check_secondary_gate| gate[Input sanitiser]

    gate -->|bounded prompt| tutor[Tutor LLM - Groq/Ollama/OpenAI]
    ingest -->|question/context/rubric| tutor

    tutor -->|reply| app
    app -->|canary check| app

    app -->|Admin SDK, server-side only| firestore[(Firestore)]
    app -.->|masked: no names/emails/student IDs| cloud_provider[Cloud LLM provider]
```

**What crosses the institution boundary:** only the question text, the student's
answer, and the rubric go to a cloud LLM provider (Groq/OpenAI), and only after
`rate_limiter._mask_sensitive_request` strips emails and student-ID patterns out
of the outbound text. Switching `LLM_PROVIDER=ollama` keeps everything local instead.

**What never leaves Firestore:** student names/IDs tied to performance records,
audit log raw prompts, and the canary token's surrounding system prompt - the
audit logger redacts these fields before they're written anywhere (see
`1.5_security/audit_logger.py`).

**Client access to Firestore:** none. Every read/write goes through the
Streamlit backend over the Firebase Admin SDK, which bypasses Firestore
Security Rules entirely - `firestore.rules` (repo root) denies all direct
client access as a backstop in case a client key ever ends up somewhere it
shouldn't.
