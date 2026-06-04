# Product Roadmap — Ayurveda Study Notes Generator

A feature roadmap to evolve this tool from a personal pipeline into a full student learning platform.
Organized across three student modes: **Learn → Revise → Challenge**

---

## Current State (Done)

- YouTube URL → exam-ready Markdown cheat sheet
- Hindi/Hinglish output via Whisper transcription + Claude synthesis
- OCR on slide frames, aligned with transcript
- Domain-aware formatting: Ayurveda (Sanskrit tables) vs Math (step-by-step working)
- Web UI: submit jobs, monitor pipeline progress, preview/download notes, archive
- Completed jobs restored from disk on server restart

---

## Phase 1 — Foundation (Must-Have for any real users)

### 1.1 User Accounts & Auth
- Google / email login (use Supabase or Auth0)
- Each user sees only their own notes and jobs
- **Why:** Without this it's a single-user personal tool, not a product

### 1.2 Persistent Storage
- Move jobs + notes metadata to Postgres/Supabase instead of in-memory store
- Notes survive server restarts without the disk-scan workaround
- **Why:** Current in-memory store is a stopgap; breaks at scale

### 1.3 Cloud Deployment
- Deploy on Railway / Render / Fly.io
- Currently only runs on local machine
- **Why:** No users can access it otherwise

### 1.4 Playlist / Batch Processing
- Paste a YouTube playlist URL → process all videos in sequence
- Show per-video progress in the UI
- **Why:** Exam courses have 30–100 lectures; students need the full series processed at once

---

## Phase 2 — Learn Mode

> Help students absorb and understand content better.

### 2.1 Concept Glossary (auto-generated)
- Extract every Sanskrit term, formula, and named concept across all notes
- Searchable dictionary: click a term → see which videos and sections covered it
- **Why:** Students constantly ask "what was that term again?" across 30 lectures

### 2.2 Topic Cross-linking
- "This concept was also covered in [Video X] at 12:34"
- Auto-link sections across different videos that cover the same topic
- **Why:** Teachers reinforce key concepts across multiple lectures; cross-links surface those connections

### 2.3 Difficulty Tagging
- Auto-tag each section Easy / Medium / Hard based on number of ⚠️ traps and edge cases
- Students can filter: "show me only Hard sections"
- **Why:** Targeted study — spend time on what's actually difficult

### 2.4 PDF Export
- Download any note as a formatted, print-ready PDF
- **Why:** Students print notes to study offline; no laptop during revision sessions

---

## Phase 3 — Revise Mode

> Help students retain what they've learned.

### 3.1 Flashcard Deck (auto-generated)
- Every Q→A bullet in the notes becomes a flashcard automatically
- Flip-card UI in the browser
- **Why:** Q→A format already exists in the notes — this is a small step with huge study value

### 3.2 Spaced Repetition
- Mark cards as "I knew this" / "I didn't know this"
- Cards you struggle with come back more often (SM-2 algorithm)
- **Why:** The single most evidence-backed study technique; Anki built a company on this

### 3.3 Quick Recap Mode
- One-page summary per video: only bolded facts + ⚠️ traps, nothing else
- "5-minute revision before the exam"
- **Why:** Students don't re-read full notes before an exam — they want the 20% that gives 80% of marks

### 3.4 Revision Schedule & Streak
- "You haven't revised Govind Parikh Page 3 in 7 days — time to review"
- Daily streak counter to build habit
- **Why:** Keeps students engaged with the product daily; passive but effective

---

## Phase 4 — Challenge Mode

> Actively test students and simulate exam conditions.

### 4.1 Auto-generated MCQ Test (per video)
- From any video's notes, generate 10–15 MCQs using Claude
- Student takes the test, sees score, sees which answers were wrong and why
- **Why:** Highest-value feature for exam aspirants; students will specifically pay for this

### 4.2 Exam Simulator (multi-video)
- Select multiple videos → generate a full 25/50 question mock test mixing topics
- Timed. Shows score and topic-wise breakdown at the end
- **Why:** Mimics the actual exam experience; SSC/AIAPGET students practice this obsessively

### 4.3 Trap Question Drill
- Show only the ⚠️ trap questions from all notes, in drill mode
- "Can you spot the trick?" — student must identify the common mistake
- **Why:** These are the questions that cost marks in exams; drilling them specifically is high ROI

### 4.4 Head-to-Head Challenge
- Two students attempt the same quiz simultaneously
- Live score comparison; winner gets a badge
- **Why:** Gamification + social pressure = engagement; works especially in Telegram study groups

### 4.5 Leaderboard by Subject
- Weekly top scorers per subject (Ayurveda, SSC Reasoning, Maths, etc.)
- Resets every week to give everyone a fresh chance
- **Why:** Creates competition, social sharing, and return visits

---

## Phase 5 — Monetization & Growth

### 5.1 Freemium Model
| Plan | Price | Limits |
|------|-------|--------|
| Free | ₹0 | 3 videos/month, small model only, no PDF |
| Pro | ₹299/month | Unlimited videos, medium/large model, PDF export, flashcards |
| Team | ₹999/month | 5 users, shared notes, leaderboard, exam simulator |

### 5.2 Shareable Notes
- Generate a public read-only link for any note (like Notion share)
- Viral growth: students share notes → others sign up to generate their own
- **Why:** Best zero-cost acquisition channel

### 5.3 Telegram Bot
- Send a YouTube URL to a bot → receive the `.md` or PDF in DMs
- **Why:** Massive distribution channel for Indian exam prep audience; huge Telegram study communities

### 5.4 AI Q&A on Notes
- "Ask a question about this lecture" using RAG over the generated notes
- Powered by Claude with the notes as context
- **Why:** Differentiates from static PDF tools; students can clarify doubts instantly

---

## Build Priority Summary

```
NOW (unblocks real users)
  ├── User auth
  ├── Cloud deploy
  └── Playlist/batch processing

NEXT (retention & study value)
  ├── Flashcards + spaced repetition
  ├── Quick recap mode
  ├── Auto MCQ test per video
  └── PDF export

LATER (growth & monetization)
  ├── Freemium quotas
  ├── Exam simulator
  ├── Shareable links
  └── Telegram bot

FUTURE (post product-market fit)
  ├── Leaderboard + head-to-head
  ├── Concept glossary + cross-linking
  └── AI Q&A on notes
```

---

## Core Insight

The notes pipeline is the hardest part — extracting clean, exam-formatted content from raw Hindi videos. Everything above just **consumes** that structured data in different ways.

The Q→A bullets, ⚠️ traps, bolded facts, and comparison tables already in the notes are a **structured study database**. Flashcards, MCQs, recap mode, and drills are different views on top of it.

**The moat isn't the quiz feature — it's the quality of the underlying notes that makes the quizzes actually useful.**

---

*Last updated: 2026-06-04*
