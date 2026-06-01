# Provider Portal — User Guide

> For healthcare professionals and provider administrators.
> No technical knowledge required.

---

## 1) What is the Provider Portal?

The Provider Portal is your organisation's connection to the PDHC request platform. When a healthcare professional creates a **ServiceRequest** (a care plan with instructions for your organisation), it appears automatically in your portal.

Your job is to:

1. **Review** incoming requests
2. **Accept** them
3. **Complete the work** described in the care plan
4. **Submit a report** with your findings

The portal handles all the secure data exchange with the requesting organisation — you focus on the clinical work.

---

## 2) Getting started

### 2.1 Logging in

Open the portal in your browser. You will see a login page asking for an **API key**.

Your administrator provides this key. It is a long string of letters and numbers — paste it into the field and click **Log in**.

> **Keep your API key private.** It is equivalent to a password. Do not share it via email or messaging. If you suspect it has been compromised, ask your administrator to rotate it immediately.

### 2.2 The dashboard

After login you see the dashboard with:

- **Total tasks** — all requests assigned to your organisation
- **Pending** — new requests awaiting your attention
- **Completed** — requests you have finished
- **Sync status** — whether the portal is connected to the request platform

---

## 3) Working with tasks

### 3.1 Viewing your tasks

Click **Tasks** in the navigation. You see a list of all incoming requests, newest first. Each task shows:

| Column | Meaning |
|--------|---------|
| Patient | The patient the request concerns |
| Care Plan | Title of the care plan to follow |
| Priority | Routine or urgent |
| Status | Where the task is in its lifecycle |
| Received | When the request arrived |

Use the status filter to show only pending, acknowledged, or completed tasks.

### 3.2 Task lifecycle

Every task follows these steps:

```
Pending  →  Acknowledged  →  In Progress  →  Completed
```

- **Pending (dispatched):** The request has arrived but you haven't acknowledged it yet.
- **Acknowledged:** You have accepted the request and committed to working on it.
- **In Progress:** You are actively working on the task.
- **Completed:** You have submitted your report.

### 3.3 Viewing a task

Click a task to see its full detail:

- **Patient information** — name, identifier
- **Care plan** — the goals and activities described by the requesting professional
- **Request details** — priority, dates, requesting organisation
- **Audit trail** — a log of everything that has happened with this task

### 3.4 Accepting a task

On the task detail page, click **Accept**. You can optionally add notes (e.g. "Scheduled for Tuesday").

Once accepted, the requesting organisation is notified that you are working on it.

### 3.5 Submitting a report

When you have completed the work, click **Submit Report** on the task detail page.

You will see a form where you can:

1. Enter your findings as structured observations (if the care plan specifies what to measure)
2. Or enter free-text notes describing what was done
3. Add a summary message

Click **Submit**. The report is sent securely to the requesting organisation using an encrypted authorization key. You will see a confirmation receipt.

> **You cannot edit a submitted report.** Double-check your entries before submitting. If you need to correct something, contact the requesting organisation.

---

## 4) Understanding the care plan

Each task comes with a **care plan** that describes what the requesting professional needs from you. A care plan contains:

### 4.1 Goals

What the professional wants to achieve. For example:
- "Assess patient's mobility"
- "Monitor blood pressure over 2 weeks"

### 4.2 Activities

Specific things to do. Each activity may include:
- **What to measure** — e.g., blood pressure, range of motion
- **How to respond** — numeric value, categorical choice, or free text
- **Whether it is required** — some measurements are mandatory, others optional

### 4.3 Guided vs. manual responses

If the care plan includes structured activities with defined measurements, the portal shows a **guided form** with fields for each measurement. The portal validates your entries before submission.

If the care plan is general, you can submit a **manual report** with free-text notes.

---

## 5) Receipts and audit trail

### 5.1 Receipts

Every time you submit a report, a **receipt** is created. View all receipts from the **Receipts** page. Each receipt shows:

- When the report was submitted
- A confirmation that it was delivered
- A hash of the payload (for integrity verification)

### 5.2 Audit log

The **Audit** page shows a chronological log of all actions on your tasks:

- When requests were received (sync)
- When you acknowledged a task
- When you submitted a report

This audit trail is tamper-proof and may be required for regulatory compliance.

---

## 6) Data synchronisation

The portal automatically checks for new requests from the PDHC platform. This happens in the background — you do not need to do anything.

On the dashboard, the **Sync status** section shows:

- **Last sync** — when the portal last checked for new requests
- **Requests synced** — total number of requests received since setup
- **Errors** — if something went wrong with the connection

If sync appears stuck, click **Sync Now** on the dashboard to trigger a manual check.

> **Privacy note:** When the portal checks for new requests, it first receives only a summary (no patient data). Patient data is only downloaded when a specific request is opened. This protects patient privacy in transit.

---

## 7) Troubleshooting

| Problem | What to do |
|---------|------------|
| Cannot log in | Check that your API key is correct. Ask your administrator for a new key if needed. |
| No tasks appearing | Check the sync status on the dashboard. Click "Sync Now". If errors persist, contact your administrator. |
| "Task not found" error | The task may have been reassigned or cancelled. Check with the requesting organisation. |
| Report submission failed | Check your internet connection. The portal will not lose your data — try again. |
| Sync error | Usually a temporary network issue. The portal will retry automatically. If it persists for more than an hour, contact your administrator. |

---

## 8) Glossary

| Term | Meaning |
|------|---------|
| **ServiceRequest** | A formal request from a healthcare professional to your organisation, containing a care plan and instructions |
| **Care plan** | The clinical goals and activities that describe what work needs to be done |
| **Task** | Your local working copy of a ServiceRequest — what you see in the portal |
| **Receipt** | Proof that your report was submitted and delivered |
| **API key** | Your authentication credential for the portal |
| **Sync** | The automatic process of checking for new requests from the platform |
| **Grant token** | A security key (handled automatically) that authorises data exchange for a specific request |
