# Chawanikwa Found It

A Django web app for reuniting people with lost IDs in Zimbabwe, South Africa and the USA.

- **Public search** with no account. Results show a partly hidden name (`Tin***e M.`), the last 5 characters and the town. Never a photo, a full ID number, a phone number or the exact place.
- **Report a found ID** and **register a lost ID**. Found reports wait in a moderation queue and are not searchable until a staff member approves them.
- **Safe handover**: the owner starts a claim, an agent checks a Passport, Driver's Licence or Birth Certificate **in person**, then records the handover. The number of that alternative ID is never stored.
- **Staff dashboard** (`/staff/`) with live counts, moderation queue, owner matches (WhatsApp links that staff send themselves), claims and an audit log.

The app never claims a report is genuine. "Listed" means a team member reviewed a finder's report, nothing more.

## Countries

People choose a country on the report forms and can filter searches by country. The country decides:
phone number rules (a local `082...` number becomes `+27...`), the towns/states offered, what the
"last 5 characters" of the ID look like (Zimbabwe: letters or numbers, South Africa: 5 digits,
USA: licence or state ID, never a Social Security number), and which documents are checked at handover.
Reports only match inside the same country.

**Add another country:** add one entry to `COUNTRIES` in `reports/countries.py`. Nothing else is needed.

---

## 1. Run it on your Windows computer (VS Code + PowerShell)

**One-time installs**
1. Install **Python 3.12** from python.org. On the first installer screen tick **"Add python.exe to PATH"**.
2. Install **Visual Studio Code**, then its **Python** extension.

**Open the right folder.** In VS Code choose **File > Open Folder...** and select the folder that contains `manage.py` (the folder named `chawanikwa`). If the left sidebar shows `manage.py`, `config`, `reports` and `templates`, you are in the right place.

**Open a terminal.** Menu **Terminal > New Terminal**. It must say PowerShell, and the path must end in `chawanikwa`.

Run these one at a time:

```powershell
# Allow PowerShell to run the virtual-environment script (once per computer)
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned

# Create and activate the virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1
# Your prompt now starts with (.venv)

# Install the requirements
python -m pip install --upgrade pip
pip install -r requirements.txt

# Create your local settings file
Copy-Item .env.example .env

# Create the database tables
python manage.py migrate

# Create the first administrator (you will be asked for a username and password)
python manage.py createsuperuser

# Optional: load clearly-labelled DEMO records for a presentation
python manage.py seed_demo

# Run the tests (all should pass)
python manage.py test

# Start the development server
python manage.py runserver
```

Open **http://127.0.0.1:8000/** for the public site and **http://127.0.0.1:8000/staff/login/** for staff. Stop the server with `Ctrl+C`.

In VS Code press `Ctrl+Shift+P`, choose **Python: Select Interpreter** and pick the one inside `.venv`. Press `F5` to run or debug the server.

**Next time**, open the folder, open a terminal, run `.\.venv\Scripts\Activate.ps1`, then `python manage.py runserver`.

**More staff accounts.** Sign in at `/admin/` as the administrator, open **Users**, add a user and tick **Staff status**. Only staff can use the dashboard.

**Remove demo data:** `python manage.py seed_demo --clear`

> `runserver` is for your own computer only. Never use it to serve the public.

## 2. Database setup

- **Development:** SQLite. Nothing to set up. Leave `DATABASE_URL` empty and a `db.sqlite3` file is created.
- **Production:** PostgreSQL (on the Ubuntu server):

```bash
sudo -u postgres psql <<'SQL'
CREATE USER foundit_user WITH PASSWORD 'CHOOSE-A-LONG-RANDOM-PASSWORD';
CREATE DATABASE foundit OWNER foundit_user;
SQL
```
Then set `DATABASE_URL=postgres://foundit_user:CHOOSE-A-LONG-RANDOM-PASSWORD@127.0.0.1:5432/foundit` in `/etc/foundit.env` and run `python manage.py migrate`.

Change the schema only through migrations: `python manage.py makemigrations`, then `migrate`, and commit the generated files.

## 3. Static files

Static files (CSS, images, JS) live in `static/`. WhiteNoise serves them from the app, compressed and cache-busted. In production, after every deploy:

```bash
python manage.py collectstatic --noinput
```

## 4. Production deployment (Ubuntu 22.04/24.04, Nginx, Gunicorn, HTTPS)

```bash
sudo apt update && sudo apt install -y python3-venv python3-dev libpq-dev nginx postgresql certbot python3-certbot-nginx
sudo adduser --system --group --home /srv/foundit foundit
sudo chown foundit:www-data /srv/foundit
# copy the project to /srv/foundit/app (git clone or scp), then:
sudo -u foundit python3 -m venv /srv/foundit/venv
sudo -u foundit /srv/foundit/venv/bin/pip install -r /srv/foundit/app/requirements.txt
```

**Secrets.** Create `/etc/foundit.env` (owner root, group `foundit`, `chmod 640`). Never commit it. Use `.env.example` as the template with these values:

```
DJANGO_DEBUG=0
DJANGO_SECRET_KEY=<paste a fresh 50+ character key>
DJANGO_ALLOWED_HOSTS=foundit.example.co.zw
CSRF_TRUSTED_ORIGINS=https://foundit.example.co.zw
DATABASE_URL=postgres://foundit_user:...@127.0.0.1:5432/foundit
TRUST_PROXY=1
DJANGO_ADMIN_URL=a-secret-path-you-choose/
```
Generate a key: `python3 -c "from django.core.management.utils import get_random_secret_key as g; print(g()+g())"`. The app refuses to start in production without a proper key and allowed hosts.

**Start it:**

```bash
cd /srv/foundit/app
set -a; source /etc/foundit.env; set +a
sudo -E -u foundit /srv/foundit/venv/bin/python manage.py migrate
sudo -E -u foundit /srv/foundit/venv/bin/python manage.py collectstatic --noinput
sudo -E -u foundit /srv/foundit/venv/bin/python manage.py createsuperuser
sudo cp deploy/gunicorn.service /etc/systemd/system/foundit.service
sudo systemctl daemon-reload && sudo systemctl enable --now foundit
sudo cp deploy/nginx.conf /etc/nginx/sites-available/foundit   # edit the domain first
sudo ln -s /etc/nginx/sites-available/foundit /etc/nginx/sites-enabled/
sudo certbot --nginx -d foundit.example.co.zw
sudo nginx -t && sudo systemctl reload nginx
sudo -E -u foundit /srv/foundit/venv/bin/python manage.py check --deploy
```
`deploy/nginx.conf` sets `X-Forwarded-For` to the real client address so visitors cannot fake their IP to bypass rate limits. Set `TRUST_PROXY=1` only when Nginx is in front.

**Updating:** pull the code, `pip install -r requirements.txt`, `migrate`, `collectstatic`, `sudo systemctl restart foundit`.

**Health check:** `GET /healthz/` returns `{"status": "ok"}` when the database is reachable.

**Rate limiting.** Counters are kept per Gunicorn worker by default. For one shared limit across workers, install Redis and set `REDIS_URL`.

## 5. Backup, recovery and data retention

**Backups.** `deploy/backup.sh` makes an encrypted nightly `pg_dump`. Schedule it with `sudo -u foundit crontab -e`:

```
15 2 * * * /srv/foundit/app/deploy/backup.sh >> /srv/foundit/backup.log 2>&1
```
Also copy the backup files to a different machine or storage. A backup on the same server is lost with the server.

**Recovery:**
```bash
set -a; source /etc/foundit.env; set +a
gpg --batch --passphrase-file /srv/foundit/.backup_pass -d /srv/foundit/backups/foundit-YYYYMMDD-HHMMSS.dump.gpg > /tmp/restore.dump
sudo systemctl stop foundit
sudo -u postgres dropdb foundit && sudo -u postgres createdb -O foundit_user foundit
pg_restore --no-owner --role=foundit_user -d "$DATABASE_URL" /tmp/restore.dump
shred -u /tmp/restore.dump && sudo systemctl start foundit
```
**Practise a restore on a spare machine before you need one.**

**Retention (data minimisation).** Run daily:
```
30 3 * * * cd /srv/foundit/app && set -a && . /etc/foundit.env && set +a && /srv/foundit/venv/bin/python manage.py purge_old_records >> /srv/foundit/purge.log 2>&1
```
Defaults (change in the env file): collected or rejected found reports are deleted after 90 days, closed or matched lost registrations after 180 days, audit entries after 365 days. Preview with `python manage.py purge_old_records --dry-run`. Backups are kept 30 days, so deleted records leave backups within a month. The privacy page quotes these numbers automatically.

## 6. How the pieces fit

| Folder | What it does |
|---|---|
| `reports/` | Models (found, lost, match, claim, audit), forms and validation, matching, rate limiting, management commands |
| `search/` | Public pages: search, lost, found, claim, how it works, privacy |
| `dashboard/` | Staff-only pages and actions |
| `config/` | Settings, URLs, security headers |
| `templates/`, `static/` | HTML, CSS, JS, SVG images |
| `tests/` | Automated tests (`python manage.py test`) |

## 7. Icons

Icons are **Lucide** (ISC licence, https://lucide.dev) drawn as inline SVG, plus the WhatsApp logo from **Simple Icons** (CC0). There are no font files and nothing loads from another website, which keeps the strict Content-Security-Policy intact. All icons live in `reports/templatetags/icons.py`. To use one in a template: `{% include "partials/_icon.html" with name="search" %}`. To add one, copy its SVG markup (the part inside the `<svg>` tag) from lucide.dev into the `ICONS` dictionary in that file.

## 8. Known limits

- WhatsApp messages are **not sent automatically**. Staff press a WhatsApp link, review the text and send it. An official WhatsApp Business API integration needs a Meta account and is not included.
- Rate-limit counters are per worker unless Redis is configured.
- Verification depends on trained staff following the in-person process. Software cannot confirm identity.
- Tested with SQLite and a live Gunicorn run. Run the tests against your own PostgreSQL once before going live.
