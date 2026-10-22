# User Manual for GenAI Quiz System

## Overview
The GenAI Quiz System is a robust, multi-user platform designed to facilitate interactive quizzes and learning experiences. It supports advanced features such as LLM integration, PDF and OCR-based question extraction, and persistent state management using Firestore. This manual provides guidance for both students and teachers/tutors on how to use the system effectively.

---

## Table of Contents
1. [Getting Started](#getting-started)
2. [Student Perspective](#student-perspective)
   - [Scenario 1: Taking a Quiz](#scenario-1-taking-a-quiz)
3. [Teacher/Tutor Perspective](#teacher-tutor-perspective)
   - [Scenario 2: Managing Quizzes and Student Performance](#scenario-2-managing-quizzes-and-student-performance)
4. [FAQs](#faqs)
5. [Troubleshooting](#troubleshooting)

---

## Getting Started
1. **Login**: Students and teachers/tutors log in with a username and password. Accounts are created in advance by an administrator (see `README_CyberNexa.md`, section "Create User Accounts") - there is no self-service dropdown or sign-up form.
2. **Subject Selection**: After logging in, select the subject you wish to interact with.
3. **Navigation**: Use the sidebar to navigate between quizzes and chat (for teachers/tutors only).

---

## Student Perspective

### Scenario 1: Taking a Quiz
1. **Login**:
   - Enter the username and password given to you by your teacher/administrator and select "Student".
   - Your student ID is your username - it's assigned at login automatically, there is no separate ID to pick.
   - *[Insert Screenshot: Student Login Screen]*

2. **Subject Selection**:
   - Choose the subject for which you want to take a quiz. Only quizzes a teacher has approved (published) appear in this list; a quiz your teacher is still preparing will not show up yet.
   - *[Insert Screenshot: Subject Selection Screen]*

3. **Pre-Quiz Survey**:
   - Complete the pre-quiz survey (if shown). This survey is displayed only once per student.
   - *[Insert Screenshot: Pre-Quiz Survey Screen]*

4. **Taking the Quiz**:
   - The quiz will start automatically after the survey.
   - Answer the questions displayed on the screen. You can navigate between questions using the "Next" and "Previous" buttons.
   - *[Insert Screenshot: Quiz Question Screen]*

5. **Post-Quiz Survey**:
   - After completing the quiz, fill out the post-quiz survey (if shown).
   - *[Insert Screenshot: Post-Quiz Survey Screen]*

6. **End of Quiz**:
   - After submitting the quiz and completing the post-quiz survey, you will return to the main page.

---

## Teacher/Tutor Perspective

### Scenario 2: Managing Quizzes and Student Performance
1. **Login**:
   - Enter your username and password and select "Teacher". Accounts are created in advance by an administrator; there is no self-service registration.
   - *[Insert Screenshot: Teacher Login Screen]*

2. **Subject and Quiz Management**:
   - Navigate to the "Teacher Hub" to upload new quiz materials (PDFs) or edit existing quizzes.
   - A newly uploaded quiz is saved as a **Draft** and is not visible to students yet. Open it under "Select Existing Quiz" and click **Approve** to publish it - this is the point students will be able to see and take it.
   - *[Insert Screenshot: Manage Quizzes Screen]*

3. **Security Events**:
   - The "Security Events" page (Teacher Hub → Security Events) shows blocked prompt-injection attempts and other audit events. It is restricted to Teacher accounts.

4. **Monitoring Student Performance**:
   - Access the "Performance Dashboard" to view individual and class-wide performance metrics.
   - Filter results by student, subject, or week.
   - *[Insert Screenshot: Performance Dashboard Screen]*

5. **Providing Feedback**:
   - Use the chat feature to provide personalized feedback to students.
   - *[Insert Screenshot: Chat Feedback Screen]*

---

## FAQs
1. **What if I forget my username or password?**
   - Contact your teacher/administrator; they can reset your account.
2. **Can I retake a quiz?**
   - Yes, but pre- and post-quiz surveys will not be shown again.
3. **How is my data stored?**
   - All data is securely stored in Firestore.

---

## Troubleshooting
1. **Login Issues**:
   - Double-check your username, password and role (Student/Teacher).
   - If your input seems blocked unexpectedly, you'll see a message that it was blocked; the details go to the teacher's audit log rather than being shown to you.
2. **Quiz Not Loading**:
   - Check your internet connection.
   - If a quiz you expect to see is missing, it may still be in Draft - ask your teacher to approve it.
   - Contact your teacher/tutor if the issue persists.
3. **Performance Dashboard Not Updating**:
   - Refresh the page or log out and log back in.

---

## Notes
- This manual is a living document and will be updated as new features are added.
- For further assistance, contact the system administrator.
