# UI Screens & Flow — Question Bank Generator

Fill in actual wireframe sketches/Figma links per screen as they're designed. This doc lists the required screens and their purpose so frontend work can start from a checklist rather than a blank page.

## Screen list

### 1. Home / Role selector
- Choose: "I'm a Teacher" or "I'm a Student"
- (Post-MVP: skip this once auth/login exists)

### 2. Subject & chapter selector
- List of subjects (Math, Science, Social Science, English, Kannada)
- Chapter list per subject (from parsed syllabus data)
- Topic is not a separate selection step — it's shown as a tag on each generated question (e.g. in the question bank browser filters), not part of the selection hierarchy

### 3. Generation request screen
- Question type selector (MCQ / Short / Long)
- Marks selector (1 / 2 / 3 / 5)
- Difficulty selector (easy / medium / hard)
- Count input
- "Generate" button → loading state → results

### 4. Question bank browser
- List/grid of generated questions with filters (subject, chapter, type, marks, difficulty, topic tag)
- Search bar
- Per-question actions: edit, discard, select (for paper builder)

### 5. Paper builder (Teacher only)
- Selected questions list, reorderable (drag-and-drop or up/down controls)
- Marks per question (editable override)
- Running total marks display
- Paper title input
- "Preview" and "Export as PDF" actions

### 6. Practice mode (Student only)
- Question shown one at a time or as a list
- "Reveal answer" action per question
- Answer + explanation shown after reveal
- (Optional) simple progress indicator across the session

### 7. Export/Download screen
- PDF preview
- Download button

## Navigation flow
```
Home → Subject/Chapter Selector → Generation Request → Question Bank Browser
                                                              │
                                        ┌─────────────────────┴─────────────────────┐
                                   Paper Builder (Teacher)              Practice Mode (Student)
                                        │                                             │
                                   Export/Download                              Reveal Answers
```

## Notes for React Native (Web + Android shared codebase)
- Keep navigation logic platform-agnostic (e.g. React Navigation) so both targets share the flow.
- PDF preview/download behaves differently on web (browser download) vs Android (native file save/share) — plan a platform-specific handler behind a shared interface.
