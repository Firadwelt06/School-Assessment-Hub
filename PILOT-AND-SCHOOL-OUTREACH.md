# School pilot and outreach guide

This guide is a practical starting point for introducing School Assessment Hub to the school where you currently study/work, then approaching other schools. Adapt the dates, currency, prices, and responsibilities with each school before making an offer.

## Be clear about what is ready

The current app is a Flask assessment platform designed primarily to run on a school's local network. It includes student exams, teacher and administrator accounts, question and exam management, and staff results/reporting. A school server can keep LAN exams available when internet service is unreliable.

Do not present the current version as an already-finished cloud subscription product. In particular, confirm these points before promising them:

- The optional hosted teacher portal is separate from the main exam app; it does not by itself make student exams or results available online from anywhere.
- The main app does not yet have whole-application licensing. If licensed to a school, access should expire for the entire app—not only student or teacher features—and must not be presented as permanent access.
- For an offline school server, plan for a signed license file verified locally, with a defined expiry date, advance warnings, renewal/grace behavior, and a documented policy for data access and export after expiry.
- Confirm what a teacher can access remotely and how fresh the results are before promising online score access.
- Agree who supplies, secures, and maintains the school server, local network, backups, and internet connection.

Use demo data for demonstrations. Do not copy real student records into a demo, personal device, or third-party service without the school's explicit approval and an agreed data-handling process.

## Part 1: Prepare before approaching the current school

### 1. Identify the decision-makers

Find out who should review a pilot: for example, the principal/head teacher, ICT lead, examinations officer, and one or two teachers who would use it. Ask the school who must approve software, student-data handling, network access, and any payment.

### 2. Prepare a short, safe demonstration

Prepare a demo with fictional students and sample questions. Show:

1. A teacher creating or reviewing questions and an exam.
2. A student opening and completing a short exam on the school network.
3. A teacher or administrator reviewing the resulting attempt and report.
4. What the student sees if the connection is interrupted, and what the app does and does not support offline.
5. How the school administrator creates a backup and where it is stored.

Use a spare/test database, not the live school database. Do not expose credentials, API keys, `.env` values, or production endpoints while presenting.

### 3. Bring a one-page pilot proposal

Include:

- The school problem the pilot is intended to address.
- Pilot start/end dates and participating classes, subjects, teachers, and approximate student count.
- Required server, network, devices, and a named school contact.
- What you will provide (installation, orientation, support, review meetings).
- What the school will provide (server/network access, staff time, approvals, test participants).
- How student data will be accessed, backed up, retained, and deleted/exported at the end.
- Known limitations, downtime plan, support contact/hours, and what is out of scope.
- Pilot fee, what it includes, and what a post-pilot subscription would cost or how that quote will be calculated.
- Success measures and the date when both sides will decide whether to continue.

Ask the school to approve the pilot and data-handling arrangements in writing before using real student information.

## Part 2: Run a limited pilot

### Suggested sequence

1. **Agree the scope.** Start with one or two classes and a small set of teachers. Keep the pilot small enough to support personally.
2. **Check the environment.** Confirm the server, power, network coverage, browser/device compatibility, and firewall access. Test with the school's actual devices and Wi-Fi.
3. **Prepare recovery.** Take a backup before setup, establish who can make backups, and test restoring a backup in a non-production environment. Decide how teachers will proceed if the server or network is unavailable during an exam.
4. **Train staff.** Show teachers how to create/review an exam, check student access, find results, export reports if needed, and report a problem.
5. **Run a rehearsal.** Use fictional accounts and a short mock exam. Test student sign-in, simultaneous device use, submission, results, and backup/restore.
6. **Run the agreed real pilot.** Have a school contact available. Record issues without putting student names or scores into informal notes.
7. **Check in regularly.** Hold a short weekly check-in with participating teachers and a final review with the decision-makers.
8. **Close the pilot deliberately.** Export records the school needs, agree what data is retained or deleted, document unresolved issues, and get a written decision on renewal or closure.

### Measure whether it worked

Agree targets with the school before the pilot. Useful measures include:

- Number of planned exams completed successfully.
- Student sign-in and submission success rate.
- Number and severity of interruptions, and time to recover.
- Time teachers spend preparing exams and reviewing results.
- Whether teachers can find the scores and reports they need.
- Teacher/student feedback and support requests.
- Whether the school is willing to pay for continued use.

Do not use a successful demo as proof of performance at full-school scale. Test realistic simultaneous usage before expanding.

## Part 3: Discuss price with the pilot school

First understand the school's budget and procurement process. Ask whether it prefers a one-time setup cost, an annual fee, or both. Explain what is included and which costs are separate.

### A simple offer structure

- **Pilot:** A fixed, limited-period fee for setup, orientation, and agreed support. If you choose to offer a free pilot, keep its duration, participants, support, and data handling just as clearly limited.
- **Conversion credit:** If the school subscribes within an agreed period after the pilot (for example, 30 days), credit the pilot fee toward its first annual subscription.
- **Annual subscription:** Price by active student band, with a stated maximum number of students and named included services. Annual pricing is easier for a school to budget than charging per exam.
- **One-time setup/onboarding:** State whether installation, data import, and training are included or separately priced.
- **Optional services:** Quote hardware, internet, messaging, travel, custom development, and third-party cloud charges separately. Never imply these are included unless they are.

### Work out a sustainable price

Before quoting, estimate the yearly cost of support time, updates, backups, travel, hosting (if any), and payment fees. Decide how many schools you can support, then set a price that covers those costs and your time. Do not base the price only on the cost of a small server; support, reliability, and data stewardship also take work.

For each offer, write down:

- Student limit and whether it counts enrolled or active students.
- Subscription period and renewal date.
- Included setup, training, support hours, backup responsibility, and response expectations.
- What happens to school data if the subscription ends.
- Renewal price and any price-change notice period.
- Taxes, payment charges, and third-party costs, if applicable.

Do not promise a fixed market price until you know the school's size, procurement requirements, local currency, infrastructure, and expected support needs. Put the final quote and terms in writing.

## Part 4: Approach other schools

### Questions to learn whether they need it

Ask first; do not begin with a long feature list.

1. How do you currently prepare, deliver, mark, and report exams?
2. Which part takes the most staff time or causes the most errors?
3. How many students and teachers would use an assessment system, and how many might take an exam at the same time?
4. Do students have reliable devices and Wi-Fi? What happens when internet access drops?
5. Do teachers need results only on campus, or also when they are away from school?
6. Who should be allowed to see scores, and how are teachers assigned to classes or subjects?
7. What reports, exports, or parent/student communications do you need?
8. What server, IT support, backup, and recovery arrangements do you already have?
9. What student-data, privacy, security, and retention requirements must a supplier meet?
10. Who approves a pilot and budget, what is the purchasing process, and when could a trial begin?
11. What would make you consider the pilot successful enough to pay for?

### Short pitch

> **School Assessment Hub helps schools prepare and deliver browser-based exams on the school network, then review student attempts and results. It is designed for school-managed deployments, so a local-network exam can continue without depending on every student having a reliable internet connection.**
>
> **I’d like to learn how your school currently runs exams and where teachers lose the most time. If the fit is right, we can agree on a small, time-limited pilot with sample-data testing, staff orientation, clear data safeguards, and success measures before discussing a longer-term subscription.**

Adapt the pitch to the school's answers. Do not promise remote results, a particular maximum number of simultaneous students, a formal certification, or a subscription/license feature that has not been built and tested.

### Short follow-up

> Thank you for discussing your assessment process with me. Based on what you shared, I propose a pilot for **[classes/subjects]** from **[start date]** to **[end date]**, for up to **[student count]** students and **[teacher count]** teachers. It includes **[setup/training/support]** and costs **[amount and currency]**. We will review **[success measures]** on **[review date]**. If the school continues within **[conversion window]**, **[pilot-fee credit]** will be applied to the first annual subscription. The attached scope lists responsibilities, data handling, limitations, and costs not included.

## First-time school discount

Use a discount that rewards early adoption without making the regular price unclear. A practical starting offer is:

- **20% off the first year's subscription only** for the first **three** schools that sign by **[date]**.
- Keep setup, hardware, travel, and third-party service charges outside the discount unless you explicitly choose otherwise.
- State the normal renewal price in the quote; renewals are at the then-agreed standard rate.
- Do not stack the discount with other promotions. If you prefer a pilot-fee credit, say whether it can be combined with the discount.
- Limit the offer by a real number of schools or a real expiry date, and record the terms in the agreement.

The percentage and limit above are suggested starting terms, not a researched local-market price. Validate affordability with schools and check that the discounted amount still covers your costs and support time before offering it.

## Before calling it a subscription product

The app's current school-server model and a multi-school hosted SaaS product are different offerings. Before selling recurring licenses at scale, plan and test school data separation, secure account administration, license validation and renewal, billing records, backup/restore per school, support and incident handling, and a reliable update process. A locally hosted license should not depend on constant internet access if schools need LAN exams during outages. Get appropriate legal/privacy advice for the locations where schools and students are based.

Likewise, a software use license is not an accreditation certificate. Only claim certification or regulatory approval after the relevant independent body has actually granted it.
