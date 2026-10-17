# School Assessment Hub

A professional Flask-based local-network CBT platform for schools.

Version 3.0 focuses on exam reliability: students' answers are saved to their attempt, restored after refresh, and finalized against a server-enforced timer.

## System and software requirements

### School server

- **Operating system:** Windows 10/11 64-bit or a supported 64-bit Linux distribution. Use a dedicated, reliably powered computer for a school deployment.
- **Hardware baseline:** 4 CPU cores, 8 GB RAM, and at least 10 GB of free disk space. These are practical starting points, not a promise of capacity; database size, uploaded files, and simultaneous users affect the requirements.
- **Network:** A private school LAN/Wi-Fi network with client isolation disabled, a reserved server IP address, and inbound TCP port 5000 allowed by the firewall. Internet is optional for LAN exams, but Gemini generation, package installation, hosted portals, and some formula rendering require internet access.
- **Python:** Python 3.11 or newer, 64-bit, with `pip`. Install the project dependencies from `requirements.txt`.
- **Database:** SQLite is suitable for evaluation or a small single-server installation. Use MySQL Server 8.0 or newer for a multi-user school deployment. Keep the database on a reliable drive and back it up separately.
- **Client devices:** A current browser (Chrome, Edge, Firefox, or Safari) and access to the same LAN. Students need a supported screen/browser; the app does not require a native client installation.

### Hosted AWS teacher portal (optional)

Deploying or updating the portal additionally requires an AWS account with permissions to create and update the resources listed in `teacher_portal/template.yaml`, AWS CLI v2 configured for the correct account and region, AWS SAM CLI, and Node.js 22 with npm. The portal itself runs on managed AWS services; the school does not need Node.js running on its LAN server. Review AWS pricing before deploying because free-tier availability and prices vary.

For a school with many simultaneous exam takers, use wired server networking, suitable Wi-Fi access points, and run a realistic load test before relying on the setup. The application has not been certified for a specific maximum number of simultaneous students.

## Features

- Role-based sign-in for administrators, teachers, and students.
- Subject-specific question generation from pasted notes or uploaded PDF/DOCX lesson documents.
- Gemini API integration with a local fallback when no API key is configured.
- Temporary Gemini service errors are retried before using local fallback; fallback-generated questions should be reviewed before use.
- Teacher question bank and exam builder.
- Branded CBT paper header using the administrator's school name, address, and logo.
- Student browser-based CBT examination experience.
- Attempt-scoped answer autosaving, refresh recovery, offline browser drafts, and clear connection/save status.
- Question navigator with answered/unanswered progress and staff visibility into in-progress and elapsed attempts.
- Automatic marking with subject and overall student rankings by class.
- Five administrator-selectable themes or an uploaded image theme.
- Manual question entry with LaTeX formula support.
- Administrator-controlled exam rewrite permissions.
- CSV import for teachers and students.
- Subject, topic, and class metadata on every question.
- MySQL storage for reliable multi-user school LAN deployment.
- Optional daily Cloudflare R2 backups of the database and uploaded files, with 30-day retention.
- A hosted teacher question portal with online or locally reviewed submissions, multi-question upload, and manually synchronized teacher accounts.
- Accessibility improvements including keyboard skip navigation, visible focus, screen-reader status announcements, semantic exam answer groups, accessible chart summaries, and reduced-motion support.

## Run locally

### Windows first-time installation

1. Install Python 3.11 or newer (64-bit) and select **Add Python to PATH** in the installer. Install Git if you will clone the repository.
2. Open PowerShell and clone or enter the project folder:

   ```powershell
   git clone https://github.com/Firadwelt06/School-Assessment-Hub.git
   cd School-Assessment-Hub
   ```

   If you already downloaded the project, `cd` to that folder instead.

3. Create and activate a virtual environment, then install the required packages:

   ```powershell
   py -3 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install --upgrade pip
   python -m pip install -r requirements.txt
   ```

   If PowerShell blocks activation, use `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, then activate again. Alternatively, run `.venv\Scripts\python.exe -m pip install -r requirements.txt` and `.venv\Scripts\python.exe app.py` without activating.

4. Copy the example environment file and edit it:

   ```powershell
   Copy-Item .env.example .env
   notepad .env
   ```

   For a first evaluation, set `DB_ENGINE=sqlite`. Replace `FLASK_SECRET_KEY` and `DATA_CLEAR_PASSWORD` with private, strong values. Generate a key in PowerShell with:

   ```powershell
   python -c "import secrets; print(secrets.token_urlsafe(48))"
   ```

   `GEMINI_API_KEY` is optional; without it, the app uses its local question-generation fallback. Do not commit `.env` or share its values.

5. Start the app:

   ```powershell
   python app.py
   ```

   Keep this terminal open while the app is in use. On the server, open `http://localhost:5000`. Stop the server with **Ctrl+C**. On a clean database, the initial demo sign-in is `admin` / `admin123`; immediately change the admin password and disable or replace all demo accounts before using real school data.

For MySQL, install and start MySQL Server, create the database/application user as described in [First-time MySQL setup on Windows](#first-time-mysql-setup-on-windows), and set `DB_ENGINE=mysql` plus the connection values in `.env` before first startup.

### Updating an existing installation

1. Stop the Flask/Waitress process and make a verified database and `uploads` backup.
2. Download or pull the new application version without overwriting `.env`, the database, or school uploads. If using Git, inspect `git status` before pulling so local edits are preserved.
3. Activate the virtual environment and run `python -m pip install -r requirements.txt`.
4. Review any new settings documented here against `.env.example`; retain existing secrets and database settings.
5. Start the application and test login, question entry, exam delivery, and reports before resuming school use.

### Quick start (already installed)

```powershell
cd "path\to\School-Assessment-Hub"
python -m pip install -r requirements.txt
python app.py
```

Use `.env` for settings that should persist across restarts:

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
CLOUD_BACKUP_ENABLED=0
CLOUD_BACKUP_HOUR=2
R2_ACCOUNT_ID=
R2_ACCESS_KEY_ID=
R2_SECRET_ACCESS_KEY=
R2_BUCKET=
R2_BACKUP_PREFIX=school-assessment/backups
CLOUD_PORTAL_URL=
CLOUD_PORTAL_SYNC_TOKEN=
```

Restart `python app.py` after changing `.env`; environment variables are read when the process starts. In normal mode, `python app.py` now starts the Waitress production WSGI server. Set `FLASK_DEBUG=1` only for development.

### Cloud database backups (optional)

The application can upload a backup ZIP to a private Cloudflare R2 bucket. It contains a consistent database snapshot and the contents of `uploads`. R2 encrypts objects at rest and protects transfers with TLS. Backups are retained for 30 days; the first upload runs when the application starts, followed by daily uploads at `CLOUD_BACKUP_HOUR` in the server's local time (default `2`, or 2:00 AM).

1. Create a private R2 bucket. Do not enable public access or attach a public custom domain.
2. Create an R2 API token scoped to this bucket with object read and write permissions. The application needs to list, upload, verify, and delete its own backups.
3. Copy the account ID, access key ID, and secret access key into `.env` along with the bucket name. Set `CLOUD_BACKUP_ENABLED=1`; keep the credentials private and never commit `.env`.
4. Restart the application. Check its console output for the first backup's success or any configuration/upload errors. You can run `python cloud_backup.py` to request and verify a backup manually.

The scheduled job runs in the Flask/Waitress process, so backups run only while the application is running. A SQLite archive contains `database/assessment.sqlite3`; a MySQL archive contains `database/assessment.sql`. To restore, stop the app, restore the database snapshot using the matching database engine, restore the archive's `uploads` directory, and restart the app. Test restores periodically. The free R2 allowance is 10 GB-month; if the total size of the retained backups exceeds that amount, storage charges may apply.

### Online teacher question portal

The hosted portal is separate from the school's local database. Teachers create individual portal accounts with a shared school signup code. From the portal, they can submit one question (optionally with an image up to 5 MB), paste and preview a batch, download the JSON template, or import a question JSON file. Batches are limited to 50 questions and do not include images; enter image questions one at a time so the image stays attached to its question.

The school administrator may review questions at the hosted portal's `/admin/login` page even when the school server is offline, or sync submissions to the local app and review them there. Decisions made online are copied into the local submission list and question bank on the next successful **Administration → Online question submissions → Sync now**. Decisions made locally are sent back to the portal on sync, so teachers can see the result and rejection feedback. Approval adds a question to the local bank only; the administrator must separately add it to an exam and publish that exam.

Online teacher accounts are synchronized with local teacher accounts during manual sync. A teacher created on either side can use the same username and password on both after syncing. Password changes and disabled-account status are synchronized too. If both copies have changed since their last successful sync, the app flags a conflict; an administrator must select **Keep local** or **Keep online** in the local submission/sync page. Newly imported online teachers have no local subject or class assignments: an administrator must assign both locally before they can access student results. Class assignments remain on the school server.

Exam results and student data are never uploaded to the hosted portal. Teachers can view results only on the school LAN and only for both their assigned subjects and explicitly assigned classes. The online portal stores teacher accounts and question submissions, not student results.

#### Deploy a fresh AWS portal

The AWS deployment uses API Gateway HTTP API, Lambda, on-demand DynamoDB tables, and a private S3 bucket. API Gateway gives the portal a managed HTTPS endpoint without the `workers.dev` hostname that was rejecting this app's sync requests. The endpoint is public; the portal still checks teacher sessions and the private Bearer sync token. This setup is designed for low traffic, but AWS charges may apply and free-tier eligibility varies. Check current AWS pricing for API Gateway, Lambda, DynamoDB, S3, and CloudWatch before deploying.

This deploy starts with empty AWS tables. It does **not** copy teachers, sessions, submissions, or images from the existing Cloudflare portal. Existing Cloudflare resources are left untouched.

Prerequisites: an AWS account with permission to create CloudFormation stacks, API Gateway, Lambda, IAM roles, DynamoDB tables, S3 buckets, and CloudWatch log groups; AWS CLI and AWS SAM CLI installed; and Node.js/npm available.

1. Open PowerShell in the portal project and install dependencies:

   ```powershell
   cd "E:\Projects (Working on)\Assessment\teacher_portal"
   npm install
   ```

2. Configure the AWS CLI locally and verify the selected account:

   ```powershell
   aws configure
   aws sts get-caller-identity
   ```

   Do not share or commit AWS credentials. Choose the AWS region where you want the portal data stored; the stack's API, Lambda, database tables, images, and logs are created in that region.

3. Run checks and deploy:

   ```powershell
   npm run typecheck
   npm run test:aws
   npm run deploy
   ```

   The deploy command bundles the Lambda handler and starts `sam deploy --guided`. Choose a stack name and region, allow the IAM role creation, and confirm deployment. The output includes `TeacherPortalUrl`; copy the exact HTTPS URL.

4. In the AWS Console, open **Lambda**, select the function named `<your-stack-name>-teacher-portal`, and open **Configuration → Environment variables → Edit**. Add:
   - `SCHOOL_SIGNUP_CODE`: a long signup code to share privately with teachers.
   - `SYNC_TOKEN`: a different, long random token reserved for app-to-portal sync.

   Generate a random token locally if needed:

   ```powershell
   python -c "import secrets; print(secrets.token_urlsafe(48))"
   ```

   Enter the token as its raw value—do not add `Bearer `. AWS encrypts Lambda environment variables at rest. Never put these values in source code, chat, or a committed config file.

5. Test that the API endpoint is live without sending a token:

   ```powershell
   $portal = "PASTE-THE-EXACT-TeacherPortalUrl-OUTPUT"
   curl.exe -i "$portal/api/sync/pending"
   ```

   **401 Unauthorized** is expected and confirms the sync route is reachable. A successful sync request uses `Authorization: Bearer <SYNC_TOKEN>`.

6. In the local app's `.env`, set the base URL and the same sync token:

   ```dotenv
   CLOUD_PORTAL_URL=https://your-api-id.execute-api.your-region.amazonaws.com
   CLOUD_PORTAL_SYNC_TOKEN=the-same-private-sync-token
   ```

   Do not append `/api/sync/pending` to the URL. Restart the local app, then test **Administration → Online question submissions → Sync now**.

7. Give teachers the portal URL and signup code. They must create new accounts on this fresh portal; existing Cloudflare accounts and submissions are not migrated. Leave the old Cloudflare portal in place until you have confirmed the AWS portal works and no longer need the old data.

The AWS template retains the DynamoDB tables and S3 bucket if the CloudFormation stack is deleted, to reduce accidental data loss. Review and deliberately remove retained resources if you later want to stop all related charges. Lambda logs are retained for 14 days. For a different region or service setup, review `teacher_portal/template.yaml` before deploying.

The existing Cloudflare deployment remains available with `npm run deploy:cloudflare`; do not use it for the new AWS endpoint.

Open `http://localhost:5000`. The Flask server binds to `0.0.0.0`, so other staff and students on the same Wi-Fi/LAN can use `http://lahs.local:5000` after the name is configured. The app advertises the name with Zeroconf, but `.local` discovery depends on mDNS support on each client and is not reliable on every Windows installation. For deterministic Windows access, run PowerShell as Administrator on each client:

```powershell
Start-Process PowerShell -Verb RunAs -ArgumentList '-ExecutionPolicy Bypass -File ".\setup-school-hostname.ps1" -ServerIp 192.168.1.4 -Hostname lahs.local -Wait'
```

Replace `192.168.1.4` with the server's current IPv4 address. The command opens an elevated PowerShell window because Windows protects the hosts file. Allow Python/port 5000 through Windows Firewall when prompted. This hosts-file method must be run on every Windows client; it does not configure Android or other devices. Everyone must be connected to the same private network; guest Wi-Fi isolation can prevent devices from seeing the host. Change `APP_HOSTNAME` in `.env` to the name the school wants to use. If the router supports local DNS/host records, adding the same hostname there is preferable because it works for all devices and continues to work after the server receives a new IP.

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

## Offline teacher question form

From **Question Bank**, select **Download offline form**. The downloaded `teacher-question-form.html` works without a network connection. Its main workflow is the bulk-paste area with preview and JSON download. The older one-question-at-a-time form and its local save/load controls are available in a collapsed optional section. Add shared subject, topic, class, and difficulty, paste numbered questions with A–D choices and an answer line, preview the parsed questions, and download the JSON file. Send that file to a teacher or administrator, who can import it from **Question Bank → Import offline questions** when connected to the school server. The form uses no online services and does not transfer images; images can be added later in the online editor.

To enter many questions together, use **Paste a batch of questions** in the Question Bank. Add shared subject, topic, class, and difficulty details, then paste numbered questions with A–D options and an answer line such as `Answer: B`. Preview the parsed questions, correct any flagged issues in the pasted text, preview again, and import. The app builds the JSON payload automatically; this works over the school's offline LAN and does not require a spreadsheet.

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

Administrators can generate separate access codes for teacher and student registration. New codes use a memorable word pair plus a short random suffix, are role-specific, do not depend on subject, and stop working once their configured duration expires. Existing shared access codes are migrated as student codes; generate new teacher codes for teacher registration.

Administrators can configure a shared password for teacher accounts from **Administration**. Setting or changing it resets the password for all existing teachers and applies it to future teacher registrations; student passwords are unaffected. New teachers are shown their sign-in username after registration. Because teachers share this password, distribute it securely and change it promptly if it is exposed.

Ready-to-upload examples are included in:

- `sample_data/students_sample.csv`
- `sample_data/teachers_sample.csv`

Names entered during registration, manual account creation, and CSV imports have extra whitespace normalized and all-uppercase/all-lowercase words converted to standard capitalization (for example, `ada okafor` becomes `Ada Okafor`). Existing mixed-case name parts are preserved, and names containing digits are rejected. The sample accounts use intentionally simple test passwords and should only be used in a local test environment. Teacher imports require `full_name` and `password`; `username`, `subjects`, and `classes` are optional. The `subjects` and `classes` columns accept pipe-separated values, for example `Biology|Chemistry` and `SS1 A|SS2 B`. Teachers see student results only when both the subject and class are assigned. Imported online teacher accounts start with no local assignments; an administrator must assign them in **Administration**.

## Student rankings, exam timer, and answer recovery

Teachers and administrators can open **Student Rankings** to see subject rankings within each class and overall rankings within each class. The class filter also offers combined cohorts such as `SS1`, which combines `SS1 A`, `SS1 B`, and similar sections. Rankings can be narrowed by subject, exam type, and subject/overall view.

During an exam, each answer is saved to that student's active attempt while connected. Refreshing or reopening the exam restores server-saved answers and does not reset the server-recorded timer. If the network drops, the page keeps a local recovery draft in that browser and syncs it after reconnection; the save indicator shows whether changes have reached the server. Students can use the question navigator to jump between questions and see answered/unanswered progress. Teachers and administrators see recent attempt state on their dashboard; elapsed attempts are finalized when the student reconnects or reopens the exam.

The countdown stays visible. At five minutes and one minute remaining, it changes color and displays a warning. The server enforces the configured duration and automatically finalizes saved answers at expiry. A brief network interruption can recover through the browser draft, but a device/browser loss before an offline draft syncs, a server outage, or server power loss still requires the school to restore service and use current database backups.

Administrators can delete teacher and student access from **Administration**. The account is disabled rather than physically removed so historical scores and rankings remain intact.

## Themes, formulas, and manual questions

Administrators can choose Ocean, Forest, Royal, Sunset, or Slate from **Administration**. They can also upload a PNG/JPG/WEBP image to use as the application background. The school logo is shown at a larger size in the navigation and examination header.

Administrators can publish or unpublish exams and change each exam's type and duration from the administration page. Teachers and administrators can select multiple question-bank items when creating an exam, filter the bank by subject or class, and add illustrations to manually created or edited questions. Supported question images are PNG, JPG/JPEG, WEBP, and GIF.

Staff can open **Performance Analytics** to view charts for average performance by class/cohort, subject, and exam type, plus score distribution, student count, submission count, average score, and pass rate. Teachers see only analytics for their assigned subjects; administrators see all available data. Charts use the browser's Chart.js CDN, so an offline LAN deployment should vendor Chart.js locally.

The manual question editor also supports bulk entry: click **Add another question**, complete each question card, then click **Save all questions** to add them together.

Teachers can be assigned subjects by an administrator or through the teacher registration page. Their question bank, exams, rankings, and CSV reports are limited to those subjects; administrators retain full visibility. Administrators can manage the subject and class categories from the Administration page. Students select a class during registration and only see published exams assigned to that class.

Clearing the question bank removes only questions that are not already attached to an exam. Questions used by exams are retained so clearing unused content cannot disrupt other teachers or existing exams.

Class categories use two levels: students are assigned to named arms such as `SS1Pearl` and `SS1Coral`, while exam filters can use the general cohort `SS1`. Selecting `SS1` includes both arms. Administrators manage the student arm list, and the application derives the general cohort automatically. Once an administrator has saved a class list, that list is authoritative for registration and setup forms; old student class values no longer add unexpected options.

Teacher and student registration is designed for supervised local-network sessions and does not ask for a password. For an internet-facing deployment, replace this with verified accounts or one-time access codes.

New self-registered teachers do not have a user-facing password: the application creates a secure random internal credential and signs them in immediately. They should use the supervised registration page. Imported or administrator-created teachers continue to use the password supplied by the administrator or CSV.

Administrators can generate a shared temporary access code for each subject. The same code can be given to teachers and students for that subject, and it remains valid until the configured expiry time or until disabled by the administrator. It is currently a time-limited shared code, not a single-use-per-person token.

Formula rendering is enabled throughout question creation, editing, exam delivery, and review for all subjects. Use `\( ... \)` for inline formulas and `\[ ... \]` for display formulas.

## Administrator safeguards

Administrators can publish/unpublish exams from the dashboard or Administration, change their own password from Administration, enable/disable users, and permanently remove non-administrator users. The optional legacy JSON question importer is collapsed below the bulk paste tool in Question Bank. The danger-zone data reset removes application records while retaining the current administrator account. Set a strong `DATA_CLEAR_PASSWORD` environment variable before using it; the development fallback must be replaced.

## Recommended improvements and limitations

For a more professional production release, add administrator approval for self-registration, CSRF protection, scheduled exams, printable PDF report cards, question versioning, audit logs, HTTPS, and automated MySQL backups.

The current LAN design has not been load-tested for 100 simultaneous exam takers. The default Waitress configuration uses 8 request threads, so bursts of logins, answer saves, or submissions can queue; increasing the thread count alone is not a guarantee and should be done only after testing the server hardware and MySQL under expected load. For a 100-device pilot, use a dedicated wired server, MySQL on that server or a reliable wired database host, and enough wired access points for coverage and capacity. Keep all access points on the same LAN and disable client/AP isolation so student devices can reach the server. Reserve the server's LAN address, allow inbound TCP port 5000, and rehearse with the expected number of devices, including simultaneous sign-in and submission. The school should not rely on 100-device suitability until that rehearsal succeeds. A server outage or power loss still interrupts exams; answer recovery depends on shared server persistence, and browser-local drafts are limited to the same browser/device and unsynced data. Passwordless registration is convenient for supervised testing but is not suitable for an untrusted network without access codes or approval.

For a 100-student administration checklist, create student accounts beforehand (CSV import is available), test sign-in on all device types, and publish the exam only when ready. Stagger sign-in if a full simultaneous login saturates the access point, and avoid running other high-bandwidth activity on the exam Wi-Fi.

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

If the application reports `local (GEMINI_API_KEY is not set)`, the running Flask process cannot see the environment variable. Set it in the same PowerShell window before running `python app.py`. Temporary Gemini service errors are retried before fallback; if it reports `local fallback after ... Gemini attempt(s)`, review the generated questions before including them in an exam.

## AI acknowledgment and review

The application uses AI-assisted generation to draft questions from teacher-provided lesson notes. AI-generated questions and answers may be inaccurate, incomplete, or unsuitable for a particular class. Teachers should verify the content, answer key, and curriculum alignment before using generated material in an exam; responsibility for the final assessment remains with the school and its educators.

## Frequently asked questions

### Portal sync reports HTTP 403

Check that `CLOUD_PORTAL_URL` is the exact HTTPS `TeacherPortalUrl` from the AWS stack output, with no `/api/...` suffix, and that `CLOUD_PORTAL_SYNC_TOKEN` in the local app exactly matches the Lambda `SYNC_TOKEN`. Both values are private; do not paste them into a support message. Save Lambda environment changes, restart the local app after `.env` changes, and retry **Sync now**. If the URL uses an old Cloudflare deployment, use the matching portal and token or update to the AWS URL. A `401 Unauthorized` from an unauthenticated `curl.exe` test is expected and only checks that the endpoint responds.

### Online teacher login works, but local sign-in or password does not

Run **Administration → Online question submissions → Sync now** while the local server can reach the portal. This imports new online teacher accounts and copies a one-sided password change. A password change made locally is pushed on the next sync. If the local account and online account were both changed since their last successful sync, review the conflict on that page and choose which copy should be kept. A new online teacher also needs local subject and class assignments before seeing result reports.

### Can teachers see results when the school server is offline?

No. Student accounts, exam attempts, and results stay on the school server; they are not sent to AWS. A teacher needs to connect to the school LAN and sign into the local app. The local app restricts teacher rankings, analytics, and CSV reports to the intersection of their assigned subjects and classes. Admins assign those subjects and classes in **Administration**.

### How should I upload many questions, or a question with a picture?

Use **Submit a batch of questions** in the online portal for up to 50 text-only questions. Preview before submitting; a JSON template is downloadable there, and JSON imports use the same question fields as the offline question form. To include an image, use **Submit a question** for that one question. The offline batch form can also be used without internet and imported into the local Question Bank. Questions approved in the portal enter the local question bank on the next sync; they are not automatically added to an exam.

### Why does the portal show “Something went wrong” after changing passwords?

Deploy the current `teacher_portal` code and verify `npm run typecheck` and `npm run test:aws` before deployment. Current password hashes use the shared PBKDF2 format supported by both apps; do not edit stored hashes manually. If the issue continues, inspect the Lambda's CloudWatch log for the first error and share only the error text after removing usernames, request data, tokens, and other private information.

### PowerShell says `sam` or `aws` is not recognized

Install AWS CLI v2 and AWS SAM CLI, then open a new PowerShell window so the updated PATH is loaded. Check with `aws --version` and `sam --version`. Configure the CLI with credentials issued for your AWS account and verify the selected account with `aws sts get-caller-identity`. Never send access keys or secret keys to anyone assisting with troubleshooting.

### What happens if the AWS portal stack is deleted?

The CloudFormation template retains its DynamoDB tables and image bucket to reduce accidental data loss, so deleting the stack may leave billable resources behind. To stop all charges, identify and deliberately remove retained resources in the correct AWS account and region after exporting anything you need. Check AWS billing and current service pricing; costs depend on requests, stored images/data, logs, and region.

### I cannot sign in with the initial admin account

The `admin` / `admin123` account is created only when the application database has no users. If you used a populated or migrated database, use its existing administrator account. Do not reset or replace the database just to recreate the demo account; that risks deleting school records. Contact the school's system administrator for account recovery.

### Where are local backups, and how do I restore them?

The default SQLite database is `assessment.db` in the project folder; uploaded files are in `uploads`. Stop the app before copying a manual backup. For MySQL or R2 backup/restore steps, see [Cloud database backups](#cloud-database-backups-optional) and [First-time MySQL setup on Windows](#first-time-mysql-setup-on-windows). Keep at least one backup separate from the server and test restoration before relying on it.
