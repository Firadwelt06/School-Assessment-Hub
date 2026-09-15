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
- MySQL storage for reliable multi-user school LAN deployment.

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
DB_ENGINE=mysql
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_DATABASE=school_assessment
MYSQL_USER=school_app
MYSQL_PASSWORD=replace_with_mysql_password
HOST=0.0.0.0
PORT=5000
WAITRESS_THREADS=8
```

Restart `python app.py` after changing `.env`; environment variables are read when the process starts. In normal mode, `python app.py` now starts the Waitress production WSGI server. Set `FLASK_DEBUG=1` only for development.

Open `http://localhost:5000`. The Flask server binds to `0.0.0.0`, so other staff and students on the same Wi-Fi/LAN can use the host computer's LAN IP, for example `http://192.168.1.20:5000`. Allow Python/port 5000 through Windows Firewall when prompted. Everyone must be connected to the same private network; guest Wi-Fi isolation can prevent devices from seeing the host.

## First-time MySQL setup on Windows

Open MySQL Workbench or the MySQL command line and create the database and application user. Replace the example password with your own strong password:

```sql
CREATE DATABASE school_assessment CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE OR REPLACE USER 'school_app'@'localhost' IDENTIFIED BY 'replace_with_mysql_password';
GRANT ALL PRIVILEGES ON school_assessment.* TO 'school_app'@'localhost';
FLUSH PRIVILEGES;
```

Copy `.env.example` to `.env`, fill in the MySQL password, and keep `DB_ENGINE=mysql`. On the first start, the application creates its tables automatically:

```powershell
Copy-Item .env.example .env
python -m pip install -r requirements.txt
python app.py
```

If you already have data in `assessment.db`, stop the application, configure `.env` for MySQL, start it once to create the tables, stop it, and then run:

```powershell
python migrate_sqlite_to_mysql.py assessment.db
python app.py
```

The migration replaces the records in the configured MySQL tables with the records from the SQLite file. Keep the original `assessment.db` as a backup until you have checked users, questions, exams, attempts, reports, and settings.

For other computers on the LAN, open `http://SERVER-IP:5000`. Find the server address with `ipconfig`. The Windows Firewall must allow inbound TCP port 5000.

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

Ready-to-upload examples are included in:

- `sample_data/students_sample.csv`
- `sample_data/teachers_sample.csv`

The sample accounts use intentionally simple test passwords and should only be used in a local test environment. Teacher imports require `full_name` and `password`; `username` and `class_name` are optional for teachers.

## Student rankings and exam timer

Teachers and administrators can open **Student Rankings** to see subject rankings within each class and overall rankings within each class. The class filter also offers combined cohorts such as `SS1`, which combines `SS1 A`, `SS1 B`, and similar sections. Rankings can be narrowed by subject, exam type, and subject/overall view. Students see a countdown timer during every CBT exam. At five minutes and one minute remaining, the timer changes color and displays a warning. When it reaches zero, the exam is submitted automatically.
The server also records the start time and rejects submissions after the configured duration. Refreshing the page does not reset the timer.

Administrators can delete teacher and student access from **Administration**. The account is disabled rather than physically removed so historical scores and rankings remain intact.

## Themes, formulas, and manual questions

Administrators can choose Ocean, Forest, Royal, Sunset, or Slate from **Administration**. They can also upload a PNG/JPG/WEBP image to use as the application background. The school logo is shown at a larger size in the navigation and examination header.

Administrators can publish or unpublish exams and change each exam's type and duration from the administration page. Teachers and administrators can select multiple question-bank items when creating an exam, filter the bank by subject or class, and add illustrations to manually created or edited questions. Supported question images are PNG, JPG/JPEG, WEBP, and GIF.

Staff can open **Performance Analytics** to view charts for average performance by class/cohort, subject, and exam type, plus score distribution, student count, submission count, average score, and pass rate. Teachers see only analytics for their assigned subjects; administrators see all available data. Charts use the browser's Chart.js CDN, so an offline LAN deployment should vendor Chart.js locally.

The manual question editor also supports bulk entry: click **Add another question**, complete each question card, then click **Save all questions** to add them together.

Teachers can be assigned subjects by an administrator or through the teacher registration page. Their question bank, exams, rankings, and CSV reports are limited to those subjects; administrators retain full visibility. Administrators can manage the subject and class categories from the Administration page. Students select a class during registration and only see published exams assigned to that class.

Class categories use two levels: students are assigned to arm classes such as `SS1 A` and `SS1 B`, while teachers and exam/question filters use the general cohort `SS1`. Selecting `SS1` therefore includes both arms. Administrators manage the student arm list, and the application derives the general cohort automatically.

Teacher and student registration is designed for supervised local-network sessions and does not ask for a password. For an internet-facing deployment, replace this with verified accounts or one-time access codes.

New self-registered teachers do not have a user-facing password: the application creates a secure random internal credential and signs them in immediately. They should use the supervised registration page. Imported or administrator-created teachers continue to use the password supplied by the administrator or CSV.

Administrators can generate a shared temporary access code for each subject. The same code can be given to teachers and students for that subject, and it remains valid until the configured expiry time or until disabled by the administrator. It is currently a time-limited shared code, not a single-use-per-person token.

Formula rendering is enabled throughout question creation, editing, exam delivery, and review for all subjects. Use `\( ... \)` for inline formulas and `\[ ... \]` for display formulas.

## Administrator safeguards

Administrators can publish/unpublish or permanently remove exams, enable/disable users, and permanently remove non-administrator users. The danger-zone data reset removes application records while retaining the current administrator account. Set a strong `DATA_CLEAR_PASSWORD` environment variable before using it; the development fallback must be replaced.

## Recommended improvements and limitations

For a more professional production release, add administrator approval for self-registration, CSRF protection, scheduled exams, printable PDF report cards, question versioning, audit logs, HTTPS, and automated MySQL backups.

The current LAN design may fail or become unreliable with many simultaneous students, unstable Wi-Fi, browser refreshes during submission, lost server power, scanned PDFs without OCR, duplicate names belonging to different people, or users sharing the same device/session. Passwordless registration is convenient for supervised testing but is not suitable for an untrusted network without access codes or approval.

## Result reports

Students receive only a submission confirmation; scores are visible to teachers and administrators through the staff dashboard. Staff can download a CSV summary filtered by class and exam type. With all exam types selected, each row represents one student and includes separate score, total, and percentage columns for every completed exam type, plus overall totals. Therefore, a student who completes quizzes, midterms, and finals will appear in the same class report with all available exam-type results.

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
