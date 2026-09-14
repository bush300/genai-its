import os
import json
import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
# Import the progress service to track student quiz completions
from progress_service import get_quizzes_completed, get_average_score, get_improvement_rate
# Import the formatting utility for quiz context
import sys

#input sanitisation
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE not in sys.path:
    sys.path.append(BASE)

from middleware.input_sanitizer import InputSanitizer

sys.path.append(os.path.join(os.path.dirname(__file__), 'utils'))
from utils.format_quiz_context import format_quiz_context

# Load survey URLs from environment
PRE_QUIZ_SURVEY_URL = os.getenv("PRE_QUIZ_SURVEY_URL", "")
POST_QUIZ_SURVEY_URL = os.getenv("POST_QUIZ_SURVEY_URL", "")

# Set page configuration (must be the first Streamlit command)
# CyberNexa page configuration
st.set_page_config(
    page_title="CyberNexa",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ---------- Global CyberNexa Theme ----------
st.markdown("""
<style>

/* Background */
.stApp{
    background:#081524;
    color:white;
}

/* Main container */
.block-container{
    max-width:1200px;
    padding-top:2rem;
    padding-bottom:2rem;
}

/* Titles */
h1,h2,h3{
    color:white !important;
}

/* Text */
p,label{
    color:#D7E5F7 !important;
}

/* Buttons */
.stButton>button{
    width:100%;
    height:48px;
    border-radius:12px;
    background:#173B68;
    color:white;
    border:1px solid #2E5D94;
    font-weight:600;
}

.stButton>button:hover{
    background:#23548F;
}

/* Metric Cards */
div[data-testid="stMetric"]{
    background:#10233F;
    border:1px solid #355E91;
    border-radius:12px;
    padding:18px;
}

/* Info boxes */
div[data-testid="stAlert"]{
    background:#10233F;
    border-radius:12px;
}

/* Horizontal line */
hr{
    border-color:#2E5D94;
}

</style>
""", unsafe_allow_html=True)



# Import necessary modules
import asyncio, sys

# AsyncIO fix for Streamlit on Windows
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Path patch so `import …` works
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.extend(
    [
        os.path.join(BASE, "1.2_back_end"),
        os.path.join(BASE, "1.3_models"),
        os.path.join(BASE, "1.4_agent2_quiz"),
    ]
)

from document_loader import load_and_embed_pdf
from quiz_extractor import extract_questions_from_pdf
from quiz_agent import QuizAgent

# Compatibility helper: some Streamlit versions expose experimental_rerun, others only have rerun
def safe_rerun():
    try:
        rerun_fn = getattr(st, 'experimental_rerun', None)
        if callable(rerun_fn):
            rerun_fn()
            return
    except Exception:
        pass
    # Fallback to public API if experimental is not available
    try:
        st.rerun()
    except Exception:
        # Last-resort: no-op (can't force a rerun safely)
        return

# Ensure all required data directories exist
required_dirs = [
    "data/finalised_quizzes",
    "data/uploaded_pdfs",
    "data/student_profiles",
    "data/student_performance",
    "data/global_kb",
    "data/quiz_sessions"
]
for d in required_dirs:
    os.makedirs(os.path.join(BASE, d), exist_ok=True)

# Initialize Firebase Admin SDK
if not firebase_admin._apps:
    cred = credentials.Certificate(dict(st.secrets["FIREBASE"]))
    firebase_admin.initialize_app(cred)
db = firestore.client()
def load_student_performance():
    """Load all student performance records from Firestore."""
    performance = []

    docs = db.collection("student_performance").stream()

    for doc in docs:
        data = doc.to_dict() or {}

        # Keep the Firestore document ID for the report.
        data["document_id"] = doc.id

        # Older records may not contain student_id as a field.
        if not data.get("student_id"):
            data["student_id"] = doc.id.split("_")[0]

        performance.append(data)

    return performance

def save_quiz_to_firestore(subject, week, questions):
    doc_id = f"{subject}_{week}"
    db.collection("finalised_quizzes").document(doc_id).set({
        "subject": subject,
        "week": week,
        "questions": questions
    })

def load_quiz_from_firestore(subject, week):
    doc_id = f"{subject}_{week}"
    doc = db.collection("finalised_quizzes").document(doc_id).get()
    if doc.exists:
        return doc.to_dict().get("questions", [])
    else:
        return []

# Add functionality for uploading and managing knowledgebase files

# Function to save knowledgebase to Firebase

def save_knowledgebase_to_firestore(subject, week, knowledgebase):
    doc_id = f"{subject}_{week}_kb"
    # Normalize entries before saving: ensure each item is a dict with predictable fields
    normalized = []
    for it in (knowledgebase or []):
        if isinstance(it, dict):
            name = (it.get('name') or '').replace('\n', ' ').strip()
            normalized.append({
                'name': name,
                'type': it.get('type', 'unknown'),
                'content': it.get('content'),
                'url': it.get('url'),
                'uploaded_at': it.get('uploaded_at'),
                'uploader': it.get('uploader')
            })
        else:
            name = str(it).replace('\n', ' ').strip()
            normalized.append({'name': name, 'type': 'unknown', 'content': None, 'url': None})

    db.collection("knowledgebase").document(doc_id).set({
        "subject": subject,
        "week": week,
        "knowledgebase": normalized
    })

# Function to load knowledgebase from Firebase

def load_knowledgebase_from_firestore(subject, week):
    doc_id = f"{subject}_{week}_kb"
    doc = db.collection("knowledgebase").document(doc_id).get()
    if doc.exists:
        kb = doc.to_dict().get("knowledgebase", [])
        # Normalize returned KB into list of dicts with cleaned names
        normalized = []
        for it in (kb or []):
            if isinstance(it, dict):
                name = (it.get('name') or '').replace('\n', ' ').strip()
                normalized.append({
                    'name': name,
                    'type': it.get('type', 'unknown'),
                    'content': it.get('content'),
                    'url': it.get('url'),
                    'uploaded_at': it.get('uploaded_at'),
                    'uploader': it.get('uploader')
                })
            else:
                name = str(it).replace('\n', ' ').strip()
                normalized.append({'name': name, 'type': 'unknown', 'content': None, 'url': None})
        return normalized
    return []

# ── Streamlit layout ──────────────────────────────────────────────────
# Main entry page: login/role selection
if 'page' not in st.session_state:
    st.session_state.page = 'main'

# Query param management for robust session persistence
params = st.query_params
if 'page' in params and params['page']:
    st.session_state.page = params['page']
if 'subject' in params and params['subject']:
    st.session_state['student_subject'] = params['subject']
if 'week' in params and params['week']:
    st.session_state['student_week'] = params['week']
if 'student_id' in params and params['student_id']:
    st.session_state['student_id'] = params['student_id']

def set_query_params():
    st.query_params.clear()
    st.query_params.update({
        'page': st.session_state.page,
        'subject': st.session_state.get('student_subject', ''),
        'week': st.session_state.get('student_week', ''),
        'student_id': st.session_state.get('student_id', '')
    })

if st.session_state.page == 'main':
    st.sidebar.empty()

    # A3-style landing page CSS
    st.markdown(
        """
<style>
    [data-testid="stAppViewContainer"] {
        background:
            radial-gradient(
                circle at 15% 20%,
                rgba(37, 99, 235, 0.18),
                transparent 32%
            ),
            linear-gradient(
                135deg,
                #071426 0%,
                #0A1930 48%,
                #0D2240 100%
            );
    }

    [data-testid="stHeader"] {
        background: transparent;
    }

    [data-testid="stMainBlockContainer"] {
        max-width: 1180px;
        padding-top: 3rem;
        padding-bottom: 3rem;
    }

    div[data-testid="stButton"] > button {
        min-height: 58px;
        border-radius: 12px;
        border: 1px solid rgba(96, 165, 250, 0.35);
        background: linear-gradient(
            90deg,
            #2563EB 0%,
            #1D4ED8 100%
        );
        color: white;
        font-size: 15px;
        font-weight: 700;
        transition: all 0.2s ease;
    }

    div[data-testid="stButton"] > button:hover {
        border-color: #60A5FA;
        background: linear-gradient(
            90deg,
            #1D4ED8 0%,
            #1E40AF 100%
        );
        transform: translateY(-1px);
    }

    div[data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 22px;
        border: 1px solid rgba(148, 163, 184, 0.20);
        background: rgba(12, 30, 55, 0.82);
        box-shadow: 0 22px 55px rgba(0, 0, 0, 0.30);
    }
</style>
""",
        unsafe_allow_html=True
    )

    left_column, right_column = st.columns(
        [1.15, 0.95],
        gap="large",
        vertical_alignment="center"
    )

    with left_column:
        logo_path = os.path.join(
            os.path.dirname(__file__),
            "assets",
            "cybernexa_logo.png"
        )

        logo_left, logo_middle, logo_right = st.columns(
            [1, 1.4, 1]
        )

        with logo_middle:
            st.image(
                logo_path,
                width=230
            )
        st.markdown(
            """<div style="color:#C7D8EA;font-size:14px;font-weight:600;text-align:center;margin-top:4px;">
Secure AI-Powered Learning Platform
</div>

<div style="display:flex;align-items:center;gap:12px;margin:28px 0 30px 0;">
<div style="height:1px;flex:1;background:#2A6285;"></div>
<div style="width:34px;height:34px;border-radius:50%;border:1px solid #2A6285;display:flex;justify-content:center;align-items:center;font-size:16px;">
🔒
</div>
<div style="height:1px;flex:1;background:#2A6285;"></div>
</div>

<div style="display:grid;gap:24px;max-width:390px;margin:0 auto;text-align:left;">

<div style="display:grid;grid-template-columns:55px 1fr;align-items:center;">
<div style="font-size:30px;text-align:center;">🛡️</div>
<div>
<div style="color:#FFFFFF;font-size:16px;font-weight:800;">Secure</div>
<div style="color:#8FA8C2;font-size:13px;margin-top:3px;">Your data is safe with us.</div>
</div>
</div>

<div style="display:grid;grid-template-columns:55px 1fr;align-items:center;">
<div style="font-size:30px;text-align:center;">👥</div>
<div>
<div style="color:#FFFFFF;font-size:16px;font-weight:800;">Role-Based Access</div>
<div style="color:#8FA8C2;font-size:13px;margin-top:3px;">Separate dashboards for students and teachers.</div>
</div>
</div>

<div style="display:grid;grid-template-columns:55px 1fr;align-items:center;">
<div style="font-size:30px;text-align:center;">🧠</div>
<div>
<div style="color:#FFFFFF;font-size:16px;font-weight:800;">Smart Learning</div>
<div style="color:#8FA8C2;font-size:13px;margin-top:3px;">AI-driven quizzes and instant feedback.</div>
</div>
</div>

</div>""",
            unsafe_allow_html=True
        )
        with right_column:
          with st.container(border=True):

            st.markdown(
                """
<div style="text-align:center; padding:18px 16px 10px 16px;">

<div style="
width:54px;
height:54px;
margin:0 auto 16px auto;
border-radius:15px;
background:rgba(37, 99, 235, 0.18);
border:1px solid rgba(96, 165, 250, 0.35);
display:flex;
align-items:center;
justify-content:center;
font-size:27px;
">
🔐
</div>

<h2 style="
color:#FFFFFF;
font-size:27px;
margin:0 0 8px 0;
font-weight:800;
">
Welcome to CyberNexa
</h2>

<p style="
color:#9FB6D4;
font-size:14px;
line-height:1.6;
margin:0 0 26px 0;
">
Choose your role to enter the secure learning platform.
</p>

</div>
""",
                unsafe_allow_html=True
            )

            btn_student = st.button(
                "🎓 Continue as Student",
                key="student_btn",
                help="Open the student learning portal",
                use_container_width=True
            )

            st.markdown(
                """
<div style="
text-align:center;
color:#6F89A7;
font-size:12px;
margin:8px 0;
">
OR
</div>
""",
                unsafe_allow_html=True
            )

            btn_teacher = st.button(
                "👩‍🏫 Continue as Teacher",
                key="teacher_btn",
                help="Open quiz management and analytics",
                use_container_width=True
            )

            st.markdown(
                """
<div style="
margin-top:24px;
padding:14px 16px;
border-radius:11px;
background:rgba(15, 39, 68, 0.72);
border:1px solid rgba(148, 163, 184, 0.16);
text-align:center;
color:#91A9C4;
font-size:12px;
line-height:1.6;
">
🔒 Secure access enabled<br>
Your learning information is protected.
</div>

<div style="
text-align:center;
color:#5F7895;
font-size:11px;
margin-top:18px;
margin-bottom:8px;
">
CyberNexa • Secure AI-Powered Education
</div>
""",
                unsafe_allow_html=True
            )

    if btn_teacher:
        st.session_state.page = 'teacher'
        set_query_params()
        st.rerun()

    if btn_student:
        st.session_state.page = 'student_login'
        set_query_params()
        st.rerun()

    st.stop()
if st.session_state.page == 'teacher':
    st.sidebar.header("Teacher Options")

    if st.button("⬅️ Back to Main Page"):
        st.session_state.page = 'main'
        set_query_params()
        st.rerun()

    # Teacher navigation
    nav_col1, nav_col2, nav_col3 = st.columns([1, 1, 0.75])

    with nav_col1:
        st.button(
            "🏠 Teacher Hub",
            key="current_teacher_hub",
            disabled=True,
            use_container_width=True
        )

    with nav_col2:
        if st.button(
            "📊 Analytics & Reports",
            key="teacher_hub_to_analytics",
            use_container_width=True
        ):
            st.session_state.page = "teacher_analytics"
            set_query_params()
            st.rerun()

    with nav_col3:
        if st.button(
            "🚪 Log Out",
            key="teacher_logout",
            use_container_width=True
        ):
            st.session_state.pop("teacher_id", None)
            st.session_state.page = "main"
            set_query_params()
            st.rerun()

    # CyberNexa branding
    logo_path = os.path.join(
        os.path.dirname(__file__),
        "assets",
        "cybernexa_logo.png"
    )

    st.image(
        logo_path,
        width=180
    )

    st.title("🏠 Teacher Hub")

    st.caption(
        "Manage quizzes, upload learning resources and monitor student progress."
    )

    st.markdown("---")

    mode = st.radio("Choose an action:", ["Select Existing Quiz", "Upload New Quiz"], horizontal=True)

    base = "data/finalised_quizzes"
    if mode == "Select Existing Quiz":
        # Only show subjects with at least one week containing quiz.json
        subjects = []
        for doc in db.collection("finalised_quizzes").stream():
            data = doc.to_dict()
            if data and "subject" in data:
                subjects.append(data["subject"])
        subjects = sorted(set(subjects))
        subject = st.selectbox("Select Subject", subjects, key="teacher_subject")
        weeks = []
        if subject:
            for doc in db.collection("finalised_quizzes").stream():
                data = doc.to_dict()
                if data and data.get("subject") == subject:
                    weeks.append(data.get("week"))
        weeks = sorted(set(weeks))
        week = st.selectbox("Select Week", weeks if weeks else [], key="teacher_week")
        quiz_data = load_quiz_from_firestore(subject, week) if subject and week else []

        # Show knowledgebase files and uploader for the selected subject/week
        if subject and week:
            st.markdown("### Knowledgebase for this quiz")
            knowledgebase_files = load_knowledgebase_from_firestore(subject, week)
            if knowledgebase_files:
                # Dedupe by filename (preserve first-seen order)
                seen = set()
                deduped = []
                for file in knowledgebase_files:
                    name = file.get('name') if isinstance(file, dict) else str(file)
                    if name in seen:
                        continue
                    seen.add(name)
                    deduped.append(file)
                for file in deduped:
                    if isinstance(file, dict):
                        display_name = file.get('name')
                        display_type = file.get('type', 'unknown')
                        uploaded_at = file.get('uploaded_at')
                        uploader = file.get('uploader')
                        extra = f" — uploaded by {uploader}" if uploader else ""
                        if uploaded_at:
                            extra += f" on {uploaded_at.split('T')[0]}"
                        st.markdown(f"- {display_name} ({display_type}){extra}")
                    else:
                        st.markdown(f"- {file}")

                # (Cleanup button removed as requested)
            else:
                st.info("No knowledgebase files found for this subject/week.")

            # KB uploader with progress indicators
            uploaded_kb = st.file_uploader("Upload Knowledgebase (TXT or PDF)", type=["txt", "pdf"], key=f"upload_kb_{subject}_{week}")
            if uploaded_kb:
                progress = st.empty()
                try:
                    progress.text("Reading file...")
                    file_bytes = uploaded_kb.getvalue()
                    mimetype = getattr(uploaded_kb, 'type', None) or uploaded_kb.name.split('.')[-1]
                    content_text = None
                    url = None

                    # If text file, read content
                    if uploaded_kb.name.lower().endswith('.txt') or (mimetype and 'text' in mimetype):
                        progress.text("Parsing text file...")
                        content_text = file_bytes.decode('utf-8', errors='ignore')

                    # If PDF, save temporarily and extract text
                    elif uploaded_kb.name.lower().endswith('.pdf'):
                        progress.text("Saving PDF and extracting text (this may take a moment)...")
                        temp_dir = os.path.join(BASE, 'data', 'uploaded_pdfs', 'kb', subject, week)
                        os.makedirs(temp_dir, exist_ok=True)
                        temp_pdf_path = os.path.join(temp_dir, uploaded_kb.name)
                        with open(temp_pdf_path, 'wb') as tf:
                            tf.write(file_bytes)

                        try:
                            import quiz_extractor
                            extracted_text = quiz_extractor._pdf_to_text(temp_pdf_path)
                            if extracted_text:
                                content_text = extracted_text.strip()
                                progress.text("Text extraction complete.")
                        except Exception as e:
                            progress.text(f"Text extraction failed: {e}")

                        # Optional GCS upload
                        gcs_cfg = st.secrets.get('GCS', None)
                        if gcs_cfg and gcs_cfg.get('bucket'):
                            try:
                                progress.text("Uploading PDF to Cloud Storage...")
                                from google.cloud import storage
                                client = storage.Client()
                                bucket = client.bucket(gcs_cfg['bucket'])
                                blob_name = f"knowledgebase/{subject}/{week}/{uploaded_kb.name}"
                                blob = bucket.blob(blob_name)
                                blob.upload_from_filename(temp_pdf_path, content_type='application/pdf')
                                if gcs_cfg.get('make_public'):
                                    blob.make_public()
                                    url = blob.public_url
                                else:
                                    url = f"gs://{gcs_cfg['bucket']}/{blob_name}"
                                progress.text("PDF uploaded to Cloud Storage.")
                            except Exception as e:
                                progress.text(f"Cloud upload failed: {e}")

                    # Save metadata to Firestore (merge by filename, overwrite if exists)
                    progress.text("Saving knowledgebase metadata to Firestore...")
                    existing = load_knowledgebase_from_firestore(subject, week) or []
                    merged = []
                    replaced = False
                    # Preserve existing order; replace entry when the name matches
                    for it in existing:
                        if isinstance(it, dict):
                            name = it.get('name')
                            if name == uploaded_kb.name:
                                merged.append({"name": uploaded_kb.name, "type": mimetype, "content": content_text, "url": url})
                                replaced = True
                            else:
                                merged.append(it)
                        else:
                            name = str(it)
                            if name == uploaded_kb.name:
                                merged.append({"name": uploaded_kb.name, "type": mimetype, "content": content_text, "url": url})
                                replaced = True
                            else:
                                merged.append({"name": name, "type": "unknown", "content": None, "url": None})
                    # Only save the new entry if it contains useful data (content or URL)
                    uploader_id = st.session_state.get('student_id') or st.session_state.get('teacher_id') or 'teacher'
                    from datetime import datetime, timezone
                    if content_text or url or (uploaded_kb.name.lower().endswith('.txt') and content_text is not None):
                        entry = {"name": uploaded_kb.name, "type": mimetype, "content": content_text, "url": url, "uploaded_at": datetime.now(timezone.utc).isoformat(), "uploader": uploader_id}
                        if not replaced:
                            merged.append(entry)
                    else:
                        # If the uploaded file produced no content and wasn't uploaded to cloud, do not add it
                        progress.text("Uploaded file produced no extractable content; not saving an empty KB entry.")
                        save_knowledgebase_to_firestore(subject, week, merged)
                        progress.success("Knowledgebase saved (no new entry added).")
                        safe_rerun()
                    # If the new entry was appended earlier, ensure it's saved now
                    save_knowledgebase_to_firestore(subject, week, merged)
                    progress.success("Knowledgebase uploaded and saved.")
                    safe_rerun()

                except Exception as e:
                    progress.error(f"Upload failed: {e}")

        if subject and week and quiz_data:
            st.success(f"Selected quiz: {subject} / {week}")

            # Build a KB text blob from saved knowledgebase entries for enrichment (safe, minimal change)
            kb_entries = load_knowledgebase_from_firestore(subject, week) or []
            kb_text_chunks = []
            for it in kb_entries:
                if isinstance(it, dict):
                    name = (it.get('name') or '').strip()
                    content = (it.get('content') or '').strip()
                    if content:
                        kb_text_chunks.append(f"[Source: {name}]\n{content}")
            kb_text = "\n\n".join(kb_text_chunks)[:20000]  # cap to ~20k chars to keep token usage reasonable

            # Re-run buttons for Pass-2 and Pass-3 operating on the currently edited fields
            cols = st.columns(2)
            with cols[0]:
                rerun_p2 = st.button("Re-run Pass 2: Enrich Context (uses Knowledgebase)")
            with cols[1]:
                rerun_p3 = st.button("Re-run Pass 3: Generate Rubrics")

            # Helper to fetch current edited values from the text areas (if present),
            # otherwise fall back to stored quiz data.
            def _current_value(key: str, default: str):
                return st.session_state.get(key, default)

            # Re-run Pass 2: update contexts in-place using KB + existing context
            if rerun_p2:
                import quiz_extractor  # reuse prompts and cleaner
                llm = quiz_extractor.get_llm()
                progress = st.progress(0.0, text="Enriching contexts...")
                updated = 0
                for idx, q in enumerate(quiz_data, start=1):
                    qid = q.get('id', idx)
                    q_key = f"edit_q_{qid}_question"
                    c_key = f"edit_q_{qid}_context"
                    question_txt = _current_value(q_key, q.get('question', ''))
                    context_txt  = _current_value(c_key, q.get('context', ''))
                    try:
                        enrich_prompt = quiz_extractor.ENRICH_PROMPT.format(
                            pdf_text=(kb_text or ""),
                            question=question_txt,
                            context=context_txt,
                        )
                        enriched_context = llm.invoke(
                            [
                                {"role": "system", "content": "Return ONLY the enriched context as plain text. Do not add any preamble or conclusion. Do NOT include any answer."},
                                {"role": "user", "content": enrich_prompt},
                            ],
                            temperature=0.2,
                        ).content
                        cleaned = quiz_extractor.clean_enriched_context(enriched_context)
                        # If enrichment is too short, append a few KB lines heuristically
                        if len(cleaned) < 40 and kb_text:
                            kb_lines = [ln for ln in kb_text.splitlines() if ln.strip()][:8]
                            cleaned = (cleaned + "\n" + "\n".join(kb_lines)).strip()
                        # Update text area value via session_state, then the UI will reflect after rerun
                        st.session_state[c_key] = cleaned
                        updated += 1
                    except Exception as e:
                        st.warning(f"⚠️ Pass-2 failed for Q{qid}: {e}")
                    progress.progress(updated / max(1, len(quiz_data)))
                progress.empty()
                st.success("Pass 2 complete: Context enriched using knowledgebase.")
                safe_rerun()

            # Re-run Pass 3: generate new rubrics from current question+context
            if rerun_p3:
                import quiz_extractor
                llm = quiz_extractor.get_llm()
                progress = st.progress(0.0, text="Generating rubrics...")
                updated = 0
                for idx, q in enumerate(quiz_data, start=1):
                    qid = q.get('id', idx)
                    q_key = f"edit_q_{qid}_question"
                    c_key = f"edit_q_{qid}_context"
                    r_key = f"edit_q_{qid}_rubric"
                    question_txt = _current_value(q_key, q.get('question', ''))
                    context_txt  = _current_value(c_key, q.get('context', ''))
                    try:
                        rubric_prompt = quiz_extractor.RUBRIC_PROMPT.format(
                            question=question_txt,
                            context=context_txt,
                        )
                        rubric = llm.invoke(
                            [
                                {"role": "system", "content": "Return the marking rubric as plain text."},
                                {"role": "user", "content": rubric_prompt},
                            ]
                        ).content
                        st.session_state[r_key] = rubric.strip()
                        updated += 1
                    except Exception as e:
                        st.warning(f"⚠️ Pass-3 failed for Q{qid}: {e}")
                    progress.progress(updated / max(1, len(quiz_data)))
                progress.empty()
                st.success("Pass 3 complete: Rubrics regenerated.")
                safe_rerun()

            # Render questions with a live-updating preview above the edit fields
            questions = quiz_data
            edited_questions = []
            for q in questions:
                qid = q.get('id', '')
                with st.expander(f"Question {qid}: {q.get('question', '')}"):
                    # Build a preview based on current (possibly edited) values
                    preview = st.empty()
                    q_key = f"edit_q_{qid}_question"
                    c_key = f"edit_q_{qid}_context"
                    r_key = f"edit_q_{qid}_rubric"
                    # Seed initial values in session_state so widgets are not blank and we avoid value/session_state conflicts
                    if q_key not in st.session_state:
                        st.session_state[q_key] = q.get('question', '')
                    if c_key not in st.session_state:
                        st.session_state[c_key] = q.get('context', '')
                    if r_key not in st.session_state:
                        st.session_state[r_key] = q.get('answer', '')
                    # Editable fields – avoid setting both default and session_state value for same key
                    new_question = st.text_area("Question", key=q_key)
                    new_context  = st.text_area("Context", key=c_key, height=150)
                    new_rubric   = st.text_area("Rubric", key=r_key, height=200)
                    # Update preview above fields using the live values
                    preview_data = {"id": qid, "question": new_question, "context": new_context}
                    preview.markdown(format_quiz_context(preview_data), unsafe_allow_html=True)
                    edited_questions.append({
                        "id": qid,
                        "question": new_question,
                        "context": new_context,
                        "answer": new_rubric,
                    })
            if st.button("Save All Changes"):
                save_quiz_to_firestore(subject, week, edited_questions)
                st.success(f"Saved edited quiz to Firestore for {subject} / {week}")
        else:
            st.info("Select a subject and week with an existing quiz to view or edit questions.")
    # Resolve `subject` and `week` safely from local scope or session state
    subject = locals().get('subject') or st.session_state.get('teacher_subject') or st.session_state.get('new_subject') or st.session_state.get('student_subject')
    week = locals().get('week') or st.session_state.get('teacher_week') or st.session_state.get('new_week') or st.session_state.get('student_week')

    # NOTE: The per-(subject,week) KB uploader is intentionally shown inside the
    # "Select Existing Quiz" flow above. The duplicate uploader that used to
    # appear here has been removed to avoid accidental double-uploads and
    # confusing UI. Use the "Upload Knowledgebase (TXT or PDF)" control
    # shown when a subject and week are selected under "Select Existing Quiz".

    # Restore the original 'Upload New Quiz' flow when the teacher selects that mode
    if mode == "Upload New Quiz":
        # Upload new quiz flow
        st.info("Upload a new quiz PDF to create a new quiz.")
        new_subject = st.text_input("Enter Subject Name (e.g. COMP801)", key="new_subject")
        new_week = st.text_input("Enter Week (e.g. Week 1)", key="new_week")
        uploaded_file = st.file_uploader(
            "Upload Quiz File",
            type=["pdf", "png", "jpg", "jpeg", "gif", "webp", "txt", "py", "js", "ts", "java", "c", "cpp", "cs", "html", "css", "json", "yaml", "yml", "md", "sh", "bat", "ps1", "sql"],
            key="new_quiz_file",
        )
        if new_subject and new_week and uploaded_file:
            # Save uploaded file to a temp location inside BASE so extraction utilities can access it
            temp_file_path = os.path.join(BASE, "data", "uploaded_pdfs", uploaded_file.name)
            os.makedirs(os.path.dirname(temp_file_path), exist_ok=True)
            with open(temp_file_path, "wb") as f:
                f.write(uploaded_file.read())
            import quiz_extractor
            # Only run extraction if not already done for this PDF
            if 'uploaded_file_name' not in st.session_state or st.session_state.uploaded_file_name != uploaded_file.name:
                with st.spinner("Extracting questions from file (Pass 1)..."):
                    try:
                        questions = quiz_extractor.extract_questions_from_source(temp_file_path)
                        st.session_state.uploaded_questions = questions
                        st.session_state.uploaded_file_name = uploaded_file.name
                    except Exception as e:
                        st.error(f"Error processing file: {e}")
                        st.session_state.uploaded_questions = []
            # If already extracted, use session state
            questions = st.session_state.get('uploaded_questions', [])
            if questions:
                st.success(f"Extracted {len(questions)} questions. You can edit them below before saving.")
                # Buttons to re-run Pass 2 and Pass 3
                if st.button("Re-run Pass 2: Enrich Context"):
                    with st.spinner("Re-enriching context for all questions (Pass 2)..."):
                        enriched_questions = []
                        llm = quiz_extractor.get_llm()
                        pdf_text = quiz_extractor._pdf_to_text(temp_pdf_path)
                        for idx, q in enumerate(st.session_state.uploaded_questions, start=1):
                            q.setdefault("id", idx)
                            try:
                                enrich_prompt = quiz_extractor.ENRICH_PROMPT.format(
                                    pdf_text=pdf_text,
                                    question=q["question"],
                                    context=q["context"],
                                )
                                enriched_context = llm.invoke(
                                    [
                                        {"role": "system", "content": "Return ONLY the enriched context as plain text. Do not add any preamble or conclusion."},
                                        {"role": "user", "content": enrich_prompt},
                                    ],
                                    temperature=0.2
                                ).content
                                cleaned_context = quiz_extractor.clean_enriched_context(enriched_context)
                                if len(cleaned_context) < 40 or cleaned_context.lower().startswith("the question is asking"):
                                    q_text = q["question"][:40]
                                    pdf_lines = pdf_text.splitlines()
                                    relevant_lines = [line for line in pdf_lines if q_text.split()[0] in line or any(x in line for x in ["=", "print", ":", "+", "input", "output"])]
                                    if relevant_lines:
                                        cleaned_context += "\n" + "\n".join(relevant_lines[:6])
                                q["context"] = cleaned_context.strip()
                            except Exception as e:
                                st.warning(f"⚠️ Error enriching context for Q{idx}: {e}")
                            enriched_questions.append(q)
                        st.session_state.uploaded_questions = enriched_questions
                        st.success("Pass 2 complete: Context enriched.")
                if st.button("Re-run Pass 3: Generate Rubrics"):
                    with st.spinner("Generating rubrics for all questions (Pass 3)..."):
                        rubric_questions = []
                        llm = quiz_extractor.get_llm()
                        for q in st.session_state.uploaded_questions:
                            try:
                                rubric_prompt = quiz_extractor.RUBRIC_PROMPT.format(
                                    question=q["question"],
                                    context=q["context"],
                                )
                                rubric_response = llm.invoke(
                                    [
                                        {"role": "system", "content": "Return the marking rubric as plain text."},
                                        {"role": "user", "content": rubric_prompt},
                                    ]
                                ).content
                                q["answer"] = rubric_response.strip()
                            except Exception as e:
                                st.warning(f"⚠️ Error generating rubric for Q{q.get('id','')}: {e}")
                                q["answer"] = "Rubric generation failed."
                            rubric_questions.append(q)
                        st.session_state.uploaded_questions = rubric_questions
                        st.success("Pass 3 complete: Rubrics generated.")
                # Always show the questions for editing
                edited_questions = []
                for q in st.session_state.uploaded_questions:
                    with st.expander(f"Question {q.get('id', '')}: {q.get('question', '')}"):
                        st.markdown(format_quiz_context(q), unsafe_allow_html=True)
                        new_question = st.text_area("Question", value=q.get('question', ''), key=f"new_q_{q.get('id','')}_question")
                        new_context = st.text_area("Context", value=q.get('context', ''), key=f"new_q_{q.get('id','')}_context", height=150)
                        new_rubric = st.text_area("Rubric", value=q.get('answer', ''), key=f"new_q_{q.get('id','')}_rubric", height=200)
                        edited_questions.append({
                            "id": q.get('id',''),
                            "question": new_question,
                            "context": new_context,
                            "answer": new_rubric
                        })
                # If no expanders are opened, still save the current questions
                if not edited_questions:
                    edited_questions = st.session_state.uploaded_questions
                if st.button("Save Quiz"):
                    save_quiz_to_firestore(new_subject, new_week, edited_questions)
                    st.success(f"Quiz saved to Firestore for {new_subject} / {new_week}. It is now available to students.")
elif st.session_state.page == 'teacher_analytics':
    st.sidebar.empty()

    # Teacher analytics navigation
    nav_col1, nav_col2, nav_col3 = st.columns([1, 1, 0.75])

    with nav_col1:
        if st.button(
            "🏠 Teacher Hub",
            key="analytics_to_teacher_hub",
            use_container_width=True
        ):
            st.session_state.page = "teacher"
            set_query_params()
            st.rerun()

    with nav_col2:
        st.button(
            "📊 Analytics & Reports",
            key="current_teacher_analytics",
            disabled=True,
            use_container_width=True
        )

    with nav_col3:
        if st.button(
            "🚪 Log Out",
            key="analytics_logout",
            use_container_width=True
        ):
            st.session_state.pop("teacher_id", None)
            st.session_state.page = "main"
            set_query_params()
            st.rerun()

    # CyberNexa logo
    logo_path = os.path.join(
        os.path.dirname(__file__),
        "assets",
        "cybernexa_logo.png"
    )

    st.image(logo_path, width=180)

    st.title("📊 Analytics & Reports")

    st.caption(
        "Monitor student participation, quiz performance and learning activity."
    )

    st.markdown("---")
        # Load performance data from Firestore
    performance = load_student_performance()

    # Prepare rows for chart, table and report
    analytics_rows = []

    for record in performance:
        score = record.get("last_score", 0)

        try:
            score = float(score) * 100
        except (TypeError, ValueError):
            score = 0.0

        analytics_rows.append({
            "Student ID": record.get("student_id", "Unknown"),
            "Performance Record": record.get(
                "document_id",
                "Unknown"
            ),
            "Current Question": record.get("current_q", 0),
            "Score": round(score, 1)
        })

    # Summary metrics
    metric_col1, metric_col2, metric_col3, metric_col4 = st.columns(4)

    with metric_col1:
        students = set()

        for p in performance:
            if p.get("student_id"):
                students.add(p["student_id"])

        st.metric(
            label="Total Students",
            value=len(students)
        )

    with metric_col2:
        attempts = len(performance)

        st.metric(
            label="Quiz Attempts",
            value=attempts
        )

    with metric_col3:
        scores = []

        for p in performance:
            score = p.get("last_score")

            if isinstance(score, (int, float)):
                scores.append(float(score) * 100)

        average_score = (
            sum(scores) / len(scores)
            if scores
            else 0
        )

        st.metric(
            label="Average Score",
            value=f"{average_score:.1f}%"
        )

    with metric_col4:
        completed = 0

        for p in performance:
            if p.get("current_q", 0) > 0:
                completed += 1

        completion_rate = (
            completed / attempts * 100
            if attempts
            else 0
        )

        st.metric(
            label="Completion Rate",
            value=f"{completion_rate:.0f}%"
        )

    st.markdown("---")

    # Performance section
    st.subheader("📈 Student Performance Overview")

    if analytics_rows:
        import pandas as pd

        performance_df = pd.DataFrame(analytics_rows)

        chart_df = performance_df[
            ["Performance Record", "Score"]
        ].set_index("Performance Record")

        st.bar_chart(chart_df)
    else:
        st.info(
            "Student performance charts will appear here "
            "when quiz data is available."
        )

    st.markdown("---")

    # Recent attempts section
    st.subheader("📋 Recent Quiz Attempts")

    if analytics_rows:
        import pandas as pd

        attempts_df = pd.DataFrame(analytics_rows)

        attempts_df["Score"] = attempts_df["Score"].map(
            lambda value: f"{value:.1f}%"
        )

        st.dataframe(
            attempts_df,
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info(
            "No student quiz attempts are available yet."
        )

    st.markdown("---")

    insight_col, report_col = st.columns(2)

    with insight_col:
        st.subheader("🤖 Learning Insights")

        if analytics_rows:
            highest_score = max(
                row["Score"] for row in analytics_rows
            )

            insight_average = sum(
                row["Score"] for row in analytics_rows
            ) / len(analytics_rows)

            st.success(
                f"Highest score: {highest_score:.1f}%"
            )

            st.info(
                f"Average score: {insight_average:.1f}%"
            )
        else:
            st.info(
                "Learning insights will appear after "
                "student activity is recorded."
            )

    with report_col:
        st.subheader("📄 Reports")

        if analytics_rows:
            import pandas as pd

            report_df = pd.DataFrame(analytics_rows)

            csv_report = report_df.to_csv(
                index=False
            ).encode("utf-8")

            st.download_button(
                label="Download Analytics Report",
                data=csv_report,
                file_name="analytics_report.csv",
                mime="text/csv",
                key="download_analytics_report",
                use_container_width=True
            )
        else:
            st.info(
                "Teacher reports will become available "
                "when performance data is connected."
            )

    st.stop()
elif st.session_state.page == 'student_login':
    st.sidebar.empty()

    if st.button("⬅ Back to Home"):
        st.session_state.page = 'main'
        set_query_params()
        st.rerun()

    logo_path = os.path.join(
        os.path.dirname(__file__),
        "assets",
        "cybernexa_logo.png"
    )

    st.image(logo_path, width=180)

    st.title("🧑‍🎓 Student Portal")
    st.caption("Welcome back! Select your Student ID to continue.")

    # --- Student ID selection/registration ---
    firestore_ids = set()
    for doc in db.collection("student_surveys").stream():
        data = doc.to_dict()
        if data and "student_id" in data:
            firestore_ids.add(data["student_id"])
    for doc in db.collection("student_performance").stream():
        doc_id = doc.id
        if doc_id:
            sid = doc_id.split("_")[0]
            firestore_ids.add(sid)
    local_profiles_dir = os.path.join("data", "student_profiles")
    local_ids = set()
    if os.path.exists(local_profiles_dir):
        for entry in os.listdir(local_profiles_dir):
            if os.path.isdir(os.path.join(local_profiles_dir, entry)) or entry.endswith(".json"):
                local_ids.add(entry.replace(".json", ""))
    all_ids = sorted(firestore_ids.union(local_ids))
    # 2. Dropdown + Add new option
    options = all_ids + ["Add new student..."] if all_ids else ["Add new student..."]
    selected = st.selectbox("Select your student ID", options, key="student_id_select")
    new_id = None
    if selected == "Add new student...":
        new_id = st.text_input("Enter new student ID (letters, numbers, underscores only)", key="new_student_id")
        valid = bool(new_id) and new_id.isidentifier() and new_id not in all_ids
        if new_id and not new_id.isidentifier():
            st.warning("Student ID must contain only letters, numbers, or underscores and not start with a number.")
        elif new_id and new_id in all_ids:
            st.warning("This student ID already exists. Please choose another.")
        if st.button("Continue", disabled=not valid):
            # Reset all user-specific session state on new login
            for key in list(st.session_state.keys()):
                if key not in ["page"]:
                    del st.session_state[key]
            st.session_state.student_id = new_id
            st.session_state.page = 'student_subject_select'
            set_query_params()
            st.rerun()
    else:
        if st.button("Continue", disabled=(not selected or selected == "Add new student...")):
            # Reset all user-specific session state on new login
            for key in list(st.session_state.keys()):
                if key not in ["page"]:
                    del st.session_state[key]
            st.session_state.student_id = selected
            st.session_state.page = 'student_subject_select'
            set_query_params()
            st.rerun()
    st.stop()

elif st.session_state.page == 'student_subject_select':
    st.sidebar.empty()

    # Back button
    if st.button("⬅ Back to Student Portal"):
        st.session_state.page = 'student_login'
        set_query_params()
        st.rerun()

    # CyberNexa branding
    logo_path = os.path.join(
        os.path.dirname(__file__),
        "assets",
        "cybernexa_logo.png"
    )

    st.image(logo_path, width=180)

    st.title("📚 Choose Your Subject")
    st.caption("Select the subject you would like to study today.")

    # Get all subjects from Firestore
    subjects = []
    for doc in db.collection("finalised_quizzes").stream():
        data = doc.to_dict()
        if data and "subject" in data:
            subjects.append(data["subject"])

    subjects = sorted(set(subjects))

    subject = st.selectbox(
        "Select Subject",
        subjects,
        key="student_subject_select"
    )

    if st.button("Continue", disabled=not subject):
        st.session_state['student_subject'] = subject

        # Check if pre-quiz survey is already done
        survey_doc_id = f"{st.session_state['student_id']}_pre_survey"
        survey_ref = db.collection("student_surveys").document(survey_doc_id)
        survey_doc = survey_ref.get()

        if survey_doc.exists and survey_doc.to_dict().get("done"):
            st.session_state.page = 'student_quiz'
        else:
            st.session_state.page = 'student_pre_survey'

        set_query_params()
        st.rerun()

    st.stop()

elif st.session_state.page == 'student_pre_survey':
    st.sidebar.empty()
    st.title("Pre-Quiz Survey")
    st.markdown("Please complete the pre-quiz survey below before starting your quiz.")
    # Only require survey once per student (not per subject), store in Firestore
    survey_done = False
    if 'student_id' in st.session_state:
        survey_doc_id = f"{st.session_state['student_id']}_pre_survey"
        survey_ref = db.collection("student_surveys").document(survey_doc_id)
        survey_doc = survey_ref.get()
        if survey_doc.exists and survey_doc.to_dict().get("done"):
            survey_done = True
    if survey_done:
        st.session_state.page = 'student_quiz'
        set_query_params()
        st.rerun()
    if PRE_QUIZ_SURVEY_URL:
        st.markdown(f"""
        <iframe src=\"{PRE_QUIZ_SURVEY_URL}\" width=\"100%\" height=\"600\" frameborder=\"0\"></iframe>
        """, unsafe_allow_html=True)
    else:
        st.warning("Pre-quiz survey link is not configured.")
    confirm = st.checkbox("I confirm I have completed the survey", key="pre_survey_confirm")
    if st.button("I have completed the survey", disabled=not confirm):
        if 'student_id' in st.session_state:
            survey_doc_id = f"{st.session_state['student_id']}_pre_survey"
            survey_ref = db.collection("student_surveys").document(survey_doc_id)
            survey_ref.set({"student_id": st.session_state['student_id'], "done": True})
        st.session_state.page = 'student_quiz'
        set_query_params()
        st.rerun()
    st.stop()

elif st.session_state.page == 'student_quiz':
    st.sidebar.empty()

    # Protect the Student Hub if no student is logged in
    if 'student_id' not in st.session_state:
        st.session_state.page = 'student_login'
        set_query_params()
        st.rerun()

    # -----------------------------
    # Student navigation
    # -----------------------------
    nav_col1, nav_col2, nav_col3 = st.columns([1, 1, 0.75])

    with nav_col1:
        st.button(
            "🏠 Student Hub",
            key="current_student_hub",
            disabled=True,
            use_container_width=True
        )

    with nav_col2:
        if st.button(
            "📈 My Progress",
            key="student_hub_to_progress",
            use_container_width=True
        ):
            st.session_state.page = 'student_progress'
            set_query_params()
            st.rerun()

    with nav_col3:
        if st.button(
            "🚪 Log Out",
            key="student_hub_logout",
            use_container_width=True
        ):
            # Remove student-specific session information
            student_keys = [
                "student_id",
                "student_subject",
                "student_week",
                "student_subject_select",
                "last_displayed_index"
            ]

            for key in student_keys:
                if key in st.session_state:
                    del st.session_state[key]

            st.session_state.page = 'main'
            set_query_params()
            st.rerun()

    st.write("")

    # -----------------------------
    # Student Hub header
    # -----------------------------
    with st.container(border=True):
        header_left, header_right = st.columns([3, 1])

        with header_left:
            st.markdown(
                """
<div style="font-size:13px; font-weight:700; color:#60A5FA; letter-spacing:1.5px; margin-bottom:4px;">
CYBERNEXA LEARNING SPACE
</div>

<h1 style="margin-top:0; margin-bottom:8px; color:#FFFFFF;">
AI Tutor
</h1>

<p style="color:#AFC7E5; margin-top:0; margin-bottom:4px;">
Choose a quiz and work through each question with personalised AI guidance.
</p>
""",
                unsafe_allow_html=True
            )

        with header_right:
         st.info(
        f"""
**Logged in as**

**{st.session_state.student_id}**

🟢 Active student session
"""
    )

    st.write("")

    # -----------------------------
    # Quiz selection heading
    # -----------------------------
    st.markdown(
        """
<div style="font-size:13px; font-weight:700; color:#60A5FA; letter-spacing:1px; margin-bottom:4px;">
QUIZ SELECTION
</div>

<h3 style="color:#FFFFFF; margin-top:0; margin-bottom:4px;">
Choose your learning activity
</h3>

<p style="color:#9FB6D4; margin-top:0; margin-bottom:12px;">
Select a subject and week to begin or continue your quiz.
</p>
""",
        unsafe_allow_html=True
    )

    # -----------------------------
    # Get subjects from Firestore
    # -----------------------------
    subjects = []

    for doc in db.collection("finalised_quizzes").stream():
        data = doc.to_dict()

        if data and "subject" in data:
            subjects.append(data["subject"])

    subjects = sorted(set(subjects))

    if not subjects:
        st.info(
            "No quizzes are currently available. Please ask your teacher to upload a quiz."
        )
        st.stop()

    # Use the previously selected subject when possible
    saved_subject = st.session_state.get("student_subject", "")

    if saved_subject not in subjects:
        saved_subject = subjects[0]

    subject_index = subjects.index(saved_subject)

    selection_col1, selection_col2 = st.columns(2)

    with selection_col1:
        subject = st.selectbox(
            "Subject",
            subjects,
            index=subject_index,
            key="student_subject_picker",
            help="Choose the subject you would like to study."
        )

    # -----------------------------
    # Get weeks for selected subject
    # -----------------------------
    weeks = []

    if subject:
        for doc in db.collection("finalised_quizzes").stream():
            data = doc.to_dict()

            if data and data.get("subject") == subject:
                selected_week = data.get("week")

                if selected_week:
                    weeks.append(selected_week)

    weeks = sorted(set(weeks))

    saved_week = st.session_state.get("student_week", "")

    if saved_week in weeks:
        week_index = weeks.index(saved_week)
    else:
        week_index = 0

    with selection_col2:
        week = st.selectbox(
            "Week",
            weeks,
            index=week_index if weeks else None,
            key="student_week_picker",
            help="Choose the quiz week you would like to complete."
        )

    # Save selected subject and week
    st.session_state["student_subject"] = subject
    st.session_state["student_week"] = week if week else ""

    set_query_params()

    quiz_data = (
        load_quiz_from_firestore(subject, week)
        if subject and week
        else []
    )

    # Prevent user_input from being undefined
    user_input = None

    # Initialize end_quiz to None to prevent UnboundLocalError
    end_quiz = None

    # -----------------------------
    # No quiz message
    # -----------------------------
    if not week:
        st.info(
            "No quiz weeks are available for the selected subject."
        )

    elif not quiz_data:
        st.info(
            "A quiz has not yet been added for this subject and week."
        )

    # -----------------------------
    # Active quiz
    # -----------------------------
    else:
        st.success(
            f"Quiz ready: {subject} — {week}"
        )

        # Student profile and chat-history location
        student_profile_dir = os.path.join(
            "data",
            "student_profiles",
            st.session_state.student_id
        )

        os.makedirs(
            student_profile_dir,
            exist_ok=True
        )

        safe_subject = str(subject).replace("/", "_")
        safe_week = str(week).replace("/", "_")

        chat_history_path = os.path.join(
            student_profile_dir,
            f"{safe_subject}_{safe_week}_quiz.json"
        )

        # Load existing chat history safely
        chat_history = []

        if os.path.exists(chat_history_path):
            try:
                with open(
                    chat_history_path,
                    "r",
                    encoding="utf-8"
                ) as chat_file:
                    loaded_history = json.load(chat_file)

                    if isinstance(loaded_history, list):
                        chat_history = loaded_history

            except (json.JSONDecodeError, OSError):
                chat_history = []

        # -----------------------------
        # Quiz controls
        # -----------------------------
        control_col1, control_col2 = st.columns([1, 3])

        with control_col1:
            clear_chat = st.button(
                "🗑️ Restart Quiz",
                key=f"clear_chat_{subject}_{week}",
                use_container_width=True,
                help="Clear this conversation and restart the selected quiz."
            )

        with control_col2:
            st.caption(
                "Restarting clears this quiz conversation and resets its current progress."
            )

        if clear_chat:
            chat_history = []
            st.session_state.last_displayed_index = 0

            with open(
                chat_history_path,
                "w",
                encoding="utf-8"
            ) as chat_file:
                json.dump(
                    chat_history,
                    chat_file,
                    ensure_ascii=False,
                    indent=2
                )

            # Reset quiz progress in Firestore
            performance_doc_id = (
                f"{st.session_state.student_id}_{subject}_{week}"
            )

            performance_ref = db.collection(
                "student_performance"
            ).document(
                performance_doc_id
            )

            performance_doc = performance_ref.get()

            if performance_doc.exists:
                performance_data = performance_doc.to_dict() or {}

                performance_data["current_q"] = 0
                performance_data["last_score"] = 0.0

                performance_ref.set(
                    performance_data
                )

            st.rerun()

        st.markdown(
    """
<div style="
    background:#10233F;
    border:1px solid #2E5D94;
    border-radius:12px;
    padding:18px;
    margin-top:20px;
    margin-bottom:20px;
">

<h3 style="margin-top:0; color:white;">
🤖 AI Tutor Conversation
</h3>

<p style="color:#D7E5F7;">
Answer each question in your own words. CyberNexa will provide feedback and guide you through the quiz step by step.
</p>

</div>
""",
    unsafe_allow_html=True
)

        st.markdown(
            """
<div style="font-size:13px; font-weight:700; color:#60A5FA; letter-spacing:1px; margin-bottom:4px;">
AI TUTOR CONVERSATION
</div>

<h3 style="color:#FFFFFF; margin-top:0; margin-bottom:4px;">
Work through your quiz
</h3>

<p style="color:#9FB6D4; margin-top:0; margin-bottom:14px;">
Type your answer below. The AI tutor will provide feedback and guide you to the next question.
</p>
""",
            unsafe_allow_html=True
        )

        # -----------------------------
        # Start quiz when history is empty
        # -----------------------------
        if not chat_history:
            try:
                from quiz_agent import QuizAgent

            except ImportError:
                import importlib

                quiz_agent_module = importlib.import_module(
                    "quiz_agent"
                )

                QuizAgent = quiz_agent_module.QuizAgent

            agent = QuizAgent(
                quiz_data,
                subject,
                week,
                st.session_state.student_id,
                {}
            )

            rules = agent.get_instructions()
            first_question = agent.present_question(
                quiz_data[0]
            )

            chat_history.append(
                {
                    "role": "assistant",
                    "content": rules + "\n\n" + first_question
                }
            )

            with open(
                chat_history_path,
                "w",
                encoding="utf-8"
            ) as chat_file:
                json.dump(
                    chat_history,
                    chat_file,
                    ensure_ascii=False,
                    indent=2
                )

            st.session_state.last_displayed_index = 0

        # -----------------------------
        # Display conversation
        # -----------------------------
        if (
            "last_displayed_index" not in st.session_state
            or st.session_state.last_displayed_index > len(chat_history)
        ):
            st.session_state.last_displayed_index = len(
                chat_history
            )

        chat_container = st.container(border=True)

        with chat_container:
            for message in chat_history:
                role = message.get(
                    "role",
                    "assistant"
                )

                content = message.get(
                    "content",
                    ""
                )

                if role == "user":
                    with st.chat_message(
                        "user"
                    ):
                        st.markdown(content)

                else:
                    with st.chat_message(
                        "assistant"
                    ):
                        st.markdown(content)

        # -----------------------------
        # Student answer input
        # -----------------------------
        if 'sanitizer' not in st.session_state:
            st.session_state.sanitizer = InputSanitizer()
        sanitizer = st.session_state.sanitizer

        raw_user_input = st.chat_input("Type your answer and press Enter...")

        if raw_user_input:
            # 1. RUN SECURITY GATE FIRST
            is_safe, reason = sanitizer.check_secondary_gate(raw_user_input)

            if not is_safe:
                # 2. TRIGGER RED BANNER GOVERNANCE
                st.error(
                    f"🚨 **Security Policy Violation**\n\n"
                    f"Your input was intercepted and blocked.\n\n"
                    f"**Reason:** {reason}"
                )
                st.stop()  # Prevents execution from reaching line 1918 where 'response' is referenced
            else:
                # 3. APPLY XML BOUNDING & CONTINUE
                bounded_input = sanitizer.apply_xml_prompt_bounding(raw_user_input)

                # Allow student to leave using the word quit
                if raw_user_input.strip().lower() == "quit":
                    st.session_state.page = "main"
                    set_query_params()
                    st.rerun()

                # Save RAW input to chat history so the UI looks clean
                chat_history.append(
                    {
                        "role": "user",
                        "content": raw_user_input
                    }
                )

                try:
                    from quiz_agent import QuizAgent

                except ImportError:
                    import importlib

                    quiz_agent_module = importlib.import_module("quiz_agent")
                    QuizAgent = quiz_agent_module.QuizAgent

                agent = QuizAgent(
                    quiz_data,
                    subject,
                    week,
                    st.session_state.student_id,
                    {}
                )

                with st.spinner("CyberNexa is reviewing your answer..."):
                    # Pass the BOUNDED input securely to the main AI model
                    response, end_quiz = agent.handle_input(
                        bounded_input,
                        chat_history
                    )

                # 4. POST-INFERENCE DETECTIVE CONTROL (Canary Token check)
                from middleware.input_sanitizer import contains_canary_leak
                if contains_canary_leak(response):
                    st.error(
                        "🚨 **Data Exfiltration Detected**\n\n"
                        "The AI response contained a confidential internal marker. "
                        "This session has been halted for review."
                    )
                    st.stop()

            # Move to post-quiz survey when the quiz finishes
            if end_quiz == "qualtrics2":
                chat_history.append(
                    {
                        "role": "assistant",
                        "content": response
                    }
                )

                with open(
                    chat_history_path,
                    "w",
                    encoding="utf-8"
                ) as chat_file:
                    json.dump(
                        chat_history,
                        chat_file,
                        ensure_ascii=False,
                        indent=2
                    )

                st.session_state.last_displayed_index = len(
                    chat_history
                )

                st.session_state.page = (
                    "student_post_survey"
                )

                set_query_params()
                st.rerun()

            # Split feedback and the next question when both
            # are contained in the same AI response
            if (
                "**Question" in response
                and "Context & Instructions" in response
            ):
                response_parts = response.split(
                    "**Question",
                    1
                )

                feedback = response_parts[0].strip()
                next_question = (
                    "**Question"
                    + response_parts[1].strip()
                )

                if feedback:
                    chat_history.append(
                        {
                            "role": "assistant",
                            "content": feedback
                        }
                    )

                if next_question:
                    chat_history.append(
                        {
                            "role": "assistant",
                            "content": next_question
                        }
                    )

            else:
                chat_history.append(
                    {
                        "role": "assistant",
                        "content": response
                    }
                )

            # Save updated conversation
            with open(
                chat_history_path,
                "w",
                encoding="utf-8"
            ) as chat_file:
                json.dump(
                    chat_history,
                    chat_file,
                    ensure_ascii=False,
                    indent=2
                )

            st.session_state.last_displayed_index = len(
                chat_history
            )

            st.rerun()

    set_query_params() # Update query params after any changes
elif st.session_state.page == 'student_progress':
    st.sidebar.empty()

    # Protect the page if no student is logged in
    if 'student_id' not in st.session_state:
        st.session_state.page = 'student_login'
        set_query_params()
        st.rerun()

    # Student navigation
    nav_col1, nav_col2, nav_col3 = st.columns(3)

    with nav_col1:
        if st.button(
            "🏠 Student Hub",
            use_container_width=True
        ):
            st.session_state.page = 'student_quiz'
            set_query_params()
            st.rerun()

    with nav_col2:
        st.button(
            "📈 My Progress",
            disabled=True,
            use_container_width=True
        )

    with nav_col3:
        if st.button(
            "🚪 Log Out",
            use_container_width=True
        ):
            st.session_state.pop("student_id", None)
            st.session_state.pop("student_subject", None)
            st.session_state.pop("student_week", None)
            st.session_state.page = "main"
            set_query_params()
            st.rerun()

    # Page header
    header_left, header_right = st.columns([3, 1])

    with header_left:
        st.markdown(
            """
<div style="font-size:13px; font-weight:700; color:#60A5FA;
letter-spacing:1.5px; margin-bottom:4px;">
CYBERNEXA LEARNING SPACE
</div>

<h1 style="margin-top:0; margin-bottom:8px; color:#FFFFFF;">
📈 My Progress
</h1>

<p style="color:#AFC7E5; margin-top:0;">
Track your quiz performance, learning activity and improvement over time.
</p>
""",
            unsafe_allow_html=True
        )

    with header_right:
        st.info(
            f"""
**Student ID**

**{st.session_state.student_id}**

🟢 Active session
"""
        )

    st.write("")
     # Load this student's performance records from Firestore
    student_id = st.session_state.student_id
    student_records = []

    for performance_doc in db.collection(
        "student_performance"
    ).stream():

        if not performance_doc.id.startswith(
            f"{student_id}_"
        ):
            continue

        performance_data = performance_doc.to_dict() or {}

        score = performance_data.get("last_score", 0)

        try:
            score = float(score) * 100
        except (TypeError, ValueError):
            score = 0.0

        quiz_name = performance_doc.id.replace(
            f"{student_id}_",
            "",
            1
        )

        answers = performance_data.get("answers", {})
        latest_feedback = ""

        if isinstance(answers, dict):
            for attempts in answers.values():
                if not isinstance(attempts, list):
                    continue

                for attempt in attempts:
                    if not isinstance(attempt, dict):
                        continue

                    feedback = attempt.get("feedback")

                    if feedback:
                        latest_feedback = feedback

        student_records.append({
            "Quiz": quiz_name,
            "Current Question": performance_data.get(
                "current_q",
                0
            ),
            "Score": round(score, 1),
            "Feedback": latest_feedback
        })

    # Learning summary
    st.markdown(
        """
<div style="
    background:#10233F;
    border:1px solid #2E5D94;
    border-radius:12px;
    padding:18px;
    margin-bottom:18px;
">
<h3 style="margin:0; color:#FFFFFF;">Learning Summary</h3>
<p style="color:#AFC7E5; margin-bottom:0;">
A quick overview of your current learning activity.
</p>
</div>
""",
        unsafe_allow_html=True
    )

    summary_col1, summary_col2, summary_col3 = st.columns(3)

    with summary_col1:
        completed_quizzes = get_quizzes_completed(st.session_state.student_id)

        st.metric(
            label="Quizzes Completed",
            value=completed_quizzes,
            help="Total number of completed quiz attempts."
        )

    with summary_col2:
        average_score = get_average_score(st.session_state.student_id)

        st.metric(
            label="Average Score",
            value=f"{average_score:.0f}%",
            help="Your average score across completed quizzes."
        )

    with summary_col3:
        st.metric(
            label="Improvement Rate",
            value= f"{get_improvement_rate(st.session_state.student_id):.0f}%",
            help="Your performance improvement between attempts."
        )

    st.write("")

        # Performance chart section
    st.markdown(
        """
<div style="
    background:#10233F;
    border:1px solid #2E5D94;
    border-radius:12px;
    padding:18px;
    margin-top:10px;
    margin-bottom:12px;
">
<h3 style="margin:0; color:#FFFFFF;">
📊 Quiz Performance Over Time
</h3>
<p style="color:#AFC7E5; margin-bottom:0;">
Your quiz results and performance trends will be shown here.
</p>
</div>
""",
        unsafe_allow_html=True
    )

    if student_records:
        import pandas as pd

        chart_df = pd.DataFrame(student_records)

        chart_df = chart_df[
            ["Quiz", "Score"]
        ].set_index("Quiz")

        st.line_chart(
            chart_df,
            use_container_width=True
        )
    else:
        st.info(
            "Complete a quiz to begin building your performance chart."
        )

    st.write("")

        # Attempt history section
    st.markdown(
        """
<div style="
    background:#10233F;
    border:1px solid #2E5D94;
    border-radius:12px;
    padding:18px;
    margin-top:10px;
    margin-bottom:12px;
">
<h3 style="margin:0; color:#FFFFFF;">
📋 Attempt History
</h3>
<p style="color:#AFC7E5; margin-bottom:0;">
Review your completed quizzes, scores and recent activity.
</p>
</div>
""",
        unsafe_allow_html=True
    )

    if student_records:
        import pandas as pd

        history_df = pd.DataFrame(student_records)

        history_df["Score"] = history_df["Score"].map(
            lambda value: f"{value:.1f}%"
        )

        st.dataframe(
            history_df[
                [
                    "Quiz",
                    "Current Question",
                    "Score"
                ]
            ],
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info(
            "No quiz attempts are available yet."
        )

    st.write("")

        # Feedback and reminder section
    feedback_col, reminder_col = st.columns(2)

    latest_score = (
        student_records[-1]["Score"]
        if student_records
        else 0
    )

    latest_feedback = (
        student_records[-1]["Feedback"]
        if student_records
        else ""
    )

    with feedback_col:
        with st.container(border=True):
            st.subheader("🤖 AI Tutor Feedback")

            if latest_feedback:
                st.info(latest_feedback)

            elif latest_score >= 80:
                st.success(
                    "Excellent work. You demonstrated a strong "
                    "understanding of the quiz material. Keep "
                    "practising to maintain this result."
                )

            elif latest_score >= 50:
                st.info(
                    "Good progress. Review the questions that "
                    "required more attempts and continue practising."
                )

            elif student_records:
                st.warning(
                    "Review this week's learning material before "
                    "attempting the quiz again."
                )

            else:
                st.info(
                    "Personalised feedback will appear after "
                    "quiz activity is recorded."
                )

    with reminder_col:
        with st.container(border=True):
            st.subheader("🔔 Learning Reminder")

            if latest_score >= 80:
                st.success(
                    "Great result. Continue with the next quiz "
                    "and practise regularly to maintain your progress."
                )

            elif latest_score >= 50:
                st.info(
                    "Review your previous feedback before starting "
                    "the next quiz."
                )

            elif student_records:
                st.warning(
                    "Revisit the current topic and retry the quiz "
                    "when you feel ready."
                )

            else:
                st.info(
                    "Complete a quiz to receive a personalised "
                    "learning reminder."
                )
    st.stop()
elif st.session_state.page == 'student_post_survey':
    st.sidebar.empty()
    st.title("Post-Quiz Survey")
    st.success("Please complete the post-quiz survey below:")
    post_survey_done = False
    if 'student_id' in st.session_state:
        post_survey_doc_id = f"{st.session_state['student_id']}_post_survey"
        post_survey_ref = db.collection("student_surveys").document(post_survey_doc_id)
        post_survey_doc = post_survey_ref.get()
        if post_survey_doc.exists and post_survey_doc.to_dict().get("done"):
            post_survey_done = True
    if post_survey_done:
        st.success("You have already completed the post-quiz survey. Returning to main page...")
        st.session_state.page = 'main'
        set_query_params()
        st.rerun()
    elif POST_QUIZ_SURVEY_URL:
        st.markdown(f"""
        <iframe src=\"{POST_QUIZ_SURVEY_URL}\" width=\"100%\" height=\"600\" frameborder=\"0\"></iframe>
        """, unsafe_allow_html=True)
        post_confirm = st.checkbox("I confirm I have completed the post-quiz survey", key="post_survey_confirm")
        if st.button("I have completed the post-quiz survey", disabled=not post_confirm):
            if 'student_id' in st.session_state:
                post_survey_doc_id = f"{st.session_state['student_id']}_post_survey"
                post_survey_ref = db.collection("student_surveys").document(post_survey_doc_id)
                post_survey_ref.set({"student_id": st.session_state['student_id'], "done": True})
            st.session_state.page = 'main'
            set_query_params()
            st.rerun()
    else:
        st.warning("Post-quiz survey link is not configured.")
    st.stop()
