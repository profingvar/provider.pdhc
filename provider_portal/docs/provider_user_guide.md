# Provider Portal — User Guide

Version 1.0 | 2026-03-25

---

## 1. What is the Provider Portal?

The Provider Portal is a secure web application where healthcare providers receive, review, and respond to service requests dispatched by PDHC (Primary and Digital Healthcare). Each provider organisation gets its own portal instance (e.g. `provider1.pdhc.se`).

Through the portal you can:

- View dispatched tasks (service requests assigned to your organisation)
- Accept or acknowledge incoming tasks
- Review care plan details linked to each task
- Submit completion reports with clinical observations
- Track submission receipts and audit history

---

## 2. Getting Your API Key

### Who provides the key?

Your API key is issued by the **PDHC system administrator**. The key is generated in the central PDHC Request Gateway and delivered to you through a secure channel (typically encrypted email or in-person handover).

### Key details

- The key is a long random string (e.g. `YfLOkY0PtmVv0Vu214zlna4D1aOmg4Nv2wo1Fixs4CE`)
- It is shown **exactly once** when created — if lost, a new key must be issued
- Keys may have an expiry date — the administrator will inform you
- Each key has scopes (`read`, `write`) that determine what you can do

### Keeping your key safe

- Store the key in a password manager or other secure vault
- Never share the key via unencrypted email, chat, or public channels
- Never commit the key to source code repositories
- If you suspect the key has been compromised, contact the PDHC administrator immediately to have it revoked and a new one issued

---

## 3. Logging In

1. Open your provider portal URL in a web browser (e.g. `https://provider1.pdhc.se`)
2. You will see the **Provider Login** screen
3. Paste your API key into the "API Key" field
4. Click **Login**

If the key is valid you will be redirected to the Dashboard. If the key is invalid, expired, or revoked, an error message will be displayed.

---

## 4. Dashboard

The dashboard shows a summary of your activity:

| Card              | Description                                      |
|-------------------|--------------------------------------------------|
| **Tasks**         | Total number of tasks assigned to you            |
| **Pending**       | Tasks awaiting your acknowledgement              |
| **Completed**     | Tasks you have finished and reported on           |
| **Receipts**      | Number of submission receipts on file             |

If sync is enabled, the dashboard also shows synchronisation status with the central PDHC system.

---

## 5. Working with Tasks

### Viewing tasks

Click **Tasks** in the navigation bar. You will see a list of all tasks assigned to your organisation, ordered by date (newest first).

You can filter tasks by status using the status filter dropdown:

| Status          | Meaning                                            |
|-----------------|----------------------------------------------------|
| `dispatched`    | New task — awaiting your acknowledgement            |
| `acknowledged`  | You have accepted the task                          |
| `in_progress`   | Work is underway                                    |
| `completed`     | Report submitted                                    |
| `cancelled`     | Task was cancelled by PDHC                          |

Click on a task row to see full details.

### Accepting a task

1. Open the task detail page
2. Optionally add notes (e.g. estimated timeline)
3. Click **Accept**
4. The task status changes to `acknowledged`

### Viewing care plan details

If the task is linked to a care plan, you can view the care plan details from the task detail page. This shows:

- Patient name
- Care plan title
- Activities with expected observations (measurement types, units, value sets)

This information guides what data you need to collect and report.

### Submitting a report

1. Open the task detail page
2. Click **Submit Report**
3. Fill in the report form:
   - **Clinical observations** (if guided by care plan): fill in each required measurement
   - **Free-form payload** (manual mode): enter relevant JSON data
   - **Notes**: optional narrative text
   - **Receipt message**: optional summary for the receipt
4. Click **Submit**
5. A receipt is generated confirming your submission

Re-submitting the same data is safe — the system is idempotent and will return the existing receipt.

---

## 6. Receipts

Click **Receipts** in the navigation bar to see all your submission receipts. Each receipt confirms:

- Which task the report was for
- When it was submitted
- The receipt status
- Any message you attached

Receipts serve as your proof of submission.

---

## 7. Audit Log

Click **Audit** in the navigation bar to review a chronological log of all actions taken on your account:

- Task acknowledgements
- Report submissions
- Key management events
- Sync operations

This provides full traceability of your interactions with the system.

---

## 8. Logging Out

Click **Logout** in the navigation bar. Your session is ended and the API key is cleared from the browser session. You will need to enter the key again to log back in.

---

## 9. Key Rotation

For security, your API key should be rotated periodically (recommended: every 90 days). Contact the PDHC system administrator to request a new key. After rotation:

- The old key stops working immediately
- You receive a new key to use going forward
- All your existing data (tasks, receipts, audit log) remains accessible with the new key

---

## 10. Getting Help

If you have questions or encounter issues:

- **Lost API key**: Contact the PDHC system administrator for a replacement
- **Cannot log in**: Verify your key has not expired or been revoked
- **Task data issues**: Contact the requesting organisation via the contact details on the task
- **Technical problems**: Contact the PDHC system administrator

---

## Glossary

| Term              | Definition                                                      |
|-------------------|-----------------------------------------------------------------|
| **API Key**       | Secret credential used to authenticate with the portal          |
| **Task**          | A service request dispatched to your organisation               |
| **Receipt token** | Unique identifier for a dispatched task                         |
| **Care plan**     | Structured clinical plan with expected observations             |
| **Receipt**       | Confirmation record generated when you submit a report          |
| **Scope**         | Permission level: `read` (view data) or `write` (modify data)  |
| **GUID**          | Globally unique identifier used internally for all records      |
