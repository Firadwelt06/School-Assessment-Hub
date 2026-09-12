# School Assessment Hub

A professional Flask-based local-network CBT platform for schools.

## Features

- Role-based sign-in for administrators, teachers, and students.
- Subject-specific question generation from pasted notes or uploaded PDF/DOCX lesson documents.
- Gemini API integration with a local fallback when no API key is configured.
- Teacher question bank and exam builder.
- Branded CBT paper header using the administrator's school name, address, and logo.
- Student browser-based CBT examination experience.
- Automatic marking with subject and overall student rankings by class.
- Five administrator-selectable themes or an uploaded image theme.
- Manual question entry with LaTeX formula support.
- Administrator-controlled exam rewrite permissions.
- CSV import for teachers and students.
- Subject, topic, and class metadata on every question.
- SQLite storage for a simple school LAN deployment.

## Run locally

```powershell
cd "E:\Projects (Working on)\Assessment"
python -m pip install -r requirements.txt
$env:FLASK_SECRET_KEY="replace-with-a-long-random-value"
$env:GEMINI_API_KEY="your-gemini-key"  # required for Gemini generation
python app.py
```

You can alternatively create a `.env` file in the project folder:

```text
FLASK_SECRET_KEY=replace-with-a-long-random-value
GEMINI_API_KEY=your-gemini-key
GEMINI_MODEL=gemini-3.6-flash
DATABASE_PATH=assessment.db
```

Restart `python app.py` after changing `.env`; environment variables are read when the process starts.

Open `http://localhost:5000`. The Flask server binds to `0.0.0.0`, so other staff and students on the same Wi-Fi/LAN can use the host computer's LAN IP, for example `http://192.168.1.20:5000`. Allow Python/port 5000 through Windows Firewall when prompted. Everyone must be connected to the same private network; guest Wi-Fi isolation can prevent devices from seeing the host.

Demo accounts:

| Role | Username | Password |
|---|---|---|
| Admin | `admin` | `admin123` |
| Teacher | `teacher` | `teacher123` |
| Student | `student` | `student123` |

The administrator can configure the school identity from **Administration**. The logo must be PNG, JPG, JPEG, or WEBP. It is displayed on the student CBT examination page.

## Importing students

From **Administration**, upload a CSV with these columns:

```csv
username,full_name,password,class_name
ada, Ada Okafor,StudentPass1,SS2 A
bolu, Bolu Yusuf,StudentPass2,SS2 A
```

`full_name`, `password`, and `class_name` are required. `username` is optional; if omitted, the system creates one from the student's name. Students are grouped by `class_name` for ranking reports.

## Student rankings and exam timer

Teachers and administrators can open **Student Rankings** to see subject rankings within each class and overall rankings within each class. Students see a countdown timer during every CBT exam. At five minutes and one minute remaining, the timer changes color and displays a warning. When it reaches zero, the exam is submitted automatically.
The server also records the start time and rejects submissions after the configured duration. Refreshing the page does not reset the timer.

Administrators can delete teacher and student access from **Administration**. The account is disabled rather than physically removed so historical scores and rankings remain intact.

## Themes, formulas, and manual questions

Administrators can choose Ocean, Forest, Royal, Sunset, or Slate from **Administration**. They can also upload a PNG/JPG/WEBP image to use as the application background. The school logo is shown at a larger size in the navigation and examination header.

Teachers and administrators can use **Add question manually**. Enter formulas in LaTeX:

```text
Inline: \(x^2 - 5x + 6 = 0\)
Display: \[\frac{-b \pm \sqrt{b^2 - 4ac}}{2a}\]
```

The CBT pages render these formulas using MathJax when the connected device has internet access. The plain LaTeX remains readable if the LAN has no internet access.

Only an administrator can grant a completed exam a rewrite permission. The permission is visible in **Administration** beside the student's completed attempt.

For production, replace demo passwords, use a strong secret key, add HTTPS/reverse-proxy protection, and move persistence to PostgreSQL.

## Preparing lesson notes for best question generation

Use a selectable-text PDF or DOCX file, not a photograph or scanned image. A strong lesson note should include:

1. The subject, class level, lesson title, and lesson objectives.
2. Key definitions and concepts explained in complete sentences.
3. Processes or steps in the correct order.
4. Worked examples, applications, comparisons, and important facts.
5. Curriculum standards or learning outcomes where available.

Use headings and short paragraphs or bullet points. Avoid a document that contains only a topic title, repeated summaries, answer keys without explanations, or unrelated lessons. Include at least several clear paragraphs so the generator can create different questions from different concepts.

Example structure:

```text
Subject: Biology
Class: SS2
Lesson: Photosynthesis
Objectives:
- Define photosynthesis.
- Explain the role of chlorophyll.
- Describe the factors affecting the rate of photosynthesis.

Key notes:
Photosynthesis is the process by which green plants use light energy...
Chlorophyll absorbs light energy in the chloroplast...
Carbon dioxide and water are raw materials...
```

If the application reports `local (GEMINI_API_KEY is not set)`, the running Flask process cannot see the environment variable. Set it in the same PowerShell window before running `python app.py`. If it reports `local fallback (Gemini error: ...)`, the key was seen but the Gemini request or response failed; the message now includes the reason.
