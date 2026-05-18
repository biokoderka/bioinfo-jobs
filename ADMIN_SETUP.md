# Admin Setup Guide

## One-time setup (10 minutes)

### 1. Generate admin password hash

Open your browser console (F12) and run:
```javascript
crypto.subtle.digest('SHA-256', new TextEncoder().encode('YOUR_PASSWORD_HERE'))
  .then(b => console.log([...new Uint8Array(b)].map(x=>x.toString(16).padStart(2,'0')).join('')))
```

Copy the output hash.

### 2. Create a GitHub Fine-Grained Token

Go to: **github.com → Settings → Developer settings → Personal access tokens → Fine-grained tokens**

Settings:
- **Repository access:** Only `bioinfo-jobs`
- **Permissions:**
  - `Issues` → Read and write
  - `Contents` → Read and write (for Actions to commit jobs.json)

Copy the token (starts with `github_pat_...`)

### 3. Update submit.html

In `docs/submit.html`, replace:
```
const GITHUB_OWNER = "YOUR_USERNAME";
const GITHUB_TOKEN = "YOUR_GITHUB_FINE_GRAINED_TOKEN";
```

### 4. Update admin.html

In `docs/admin.html`, replace:
```
const GITHUB_OWNER = "YOUR_USERNAME";
const GITHUB_TOKEN = "YOUR_GITHUB_FINE_GRAINED_TOKEN";
const ADMIN_PASSWORD_HASH = "REPLACE_WITH_SHA256_OF_YOUR_PASSWORD";
```
Paste the hash from step 1.

### 5. Update approve-job.yml

In `.github/workflows/approve-job.yml`, replace `YOUR_USERNAME` in:
```yaml
if: |
  ...
  github.event.comment.user.login == 'YOUR_USERNAME'
```
And in the confirmation comment URL.

### 6. Create GitHub labels

Go to: **github.com/YOUR_USERNAME/bioinfo-jobs/issues/labels**

Create these labels:
- `job-submission` (color: `#b44fff`)
- `pending-review` (color: `#ffd166`)
- `approved` (color: `#06d6a0`)

### 7. Push and deploy

```bash
git add . && git commit -m "✦ Add submission & admin system" && git push
```

---

## How it works

```
User fills submit.html
  → GitHub Issue created with label [job-submission, pending-review]
  → You get notified (GitHub notifications)

You open admin.html
  → Enter password
  → See all pending submissions
  → Click "Approve" or "Reject"

On Approve:
  → Admin panel adds /approve comment to issue
  → GitHub Actions (approve-job.yml) triggers
  → Job extracted from issue and added to docs/jobs.json
  → Commit pushed automatically
  → Issue closed with confirmation comment

On Reject:
  → Issue closed
  → Job never appears publicly
```

## Security notes

- The admin password is hashed (SHA-256) — the plaintext is never stored
- The GitHub token is in client-side JS — use a **fine-grained token** with minimum permissions (issues:write only for submit.html)
- `admin.html` is a public URL but password-protected — for extra security, rename it to something less obvious
- The `/approve` command only works from YOUR GitHub username (enforced in the workflow)
