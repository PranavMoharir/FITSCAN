# Deploying FITSCAN publicly (Oracle Cloud Always Free)

This guide puts FITSCAN on the internet at `https://<name>.duckdns.org`, behind a password, running 24/7 on a free
Oracle Cloud virtual machine, with its own **new, synthetic demo database**. Your laptop can be off. Nothing in it is
specific to one person: every account, password and address is chosen during the steps.

The application is unchanged: the same Docker Compose stack runs on the server, with one extra service in front.

```text
 Internet ──HTTPS──► Caddy (proxy, ports 80/443 only) ──► frontend   (landing page and application)
                     password · TLS · headers ·       └─► api ──► PostgreSQL, Redis ──► worker
                     rate and size limits                  (none of these is published)
```

## What is free, and what could cost money

Checked on 22 November 2026 against Oracle's [Always Free resources](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm) page.

| Resource | Always Free allowance | FITSCAN uses |
|---|---|---|
| Ampere A1 (Arm) compute | 1,500 OCPU hours and 9,000 GB hours a month: **2 OCPUs and 12 GB of memory in total** (halved from 4 OCPUs and 24 GB on 15 June 2026) | One VM, 2 OCPUs, 4 GB |
| Block storage | 200 GB in total; each boot volume is at least 47 GB | One 50 GB boot volume |
| Outbound data | 10 TB a month | A few GB |
| Domain and certificate | DuckDNS sub-domain (free); Let's Encrypt certificate (free, renewed by Caddy) | Both |

- **Charges.** A Free Tier account that is never upgraded cannot create paid resources. Costs are possible only if you upgrade to Pay As You Go and then go beyond the allowance (more OCPUs or memory, more storage, other services), or create volumes outside your home region. Do not upgrade unless you mean to pay.
- **Sign-up needs a credit or debit card** for identity verification. The 30-day trial credit that comes with a new account is temporary; the Always Free allowance above is not part of it.
- **Idle reclamation.** Oracle may reclaim an Always Free VM if, over 7 days, its CPU (95th percentile), network and memory use are all below 20%. FITSCAN's containers use about 0.6 GB of memory when idle (measured), so on a 4 GB VM the memory condition is normally not met; on a 12 GB VM it would be. This is not a guarantee: keep backups (below) and check the VM's metrics after the first week.
- **Capacity.** A1 capacity is sometimes exhausted in a region ("Out of capacity"). Try another availability domain, or try again later. The home region you choose at sign-up cannot be changed, and A1 is not offered in South Korea North (Chuncheon). Always Free storage must be in the home region.
- **Backups.** Five volume backups are included. A backup of the boot volume is the quickest way back if the VM is ever reclaimed.
- **No SLA.** Oracle can change the free allowance, as it did in June 2026.

Other free options were rejected because they cannot run FITSCAN's background worker or keep its data: Render's free tier has no background workers, sleeps after 15 minutes and deletes free PostgreSQL databases after 30 days; Vercel's Hobby plan runs only short serverless functions (no worker, Redis or database) and is for non-commercial use; Fly.io and Railway offer trial credit only; Koyeb's free instance has 512 MB, sleeps after an hour and cannot keep files; Google Cloud's free e2-micro has 1 GB of memory.

## Steps that need you (accounts and decisions)

1. **Oracle Cloud account:** sign up for the Free Tier at oracle.com/cloud/free, verify the card, choose a home region near you.
2. **DuckDNS name:** sign in at duckdns.org (GitHub, Google and others are offered), create a sub-domain such as `fitscan-demo`, and note the token shown on the page.
3. **Repository access for the server:** none for a public repository; a private one needs a read-only deploy key (step 4).
4. **The login** for the password prompt: a user name and a long random password, kept in a password manager.

## 1. Create the virtual machine

In the Oracle Cloud console: **Compute → Instances → Create instance**.

| Setting | Value |
|---|---|
| Image | Canonical Ubuntu 24.04, labelled "Always Free Eligible" (the aarch64 build is chosen automatically for A1) |
| Shape | `VM.Standard.A1.Flex`, **2 OCPUs, 4 GB memory** (shows "Always Free-eligible"; A1 allows 1–64 GB per OCPU) |
| Boot volume | 50 GB |
| Networking | A public subnet, with a public IPv4 address assigned |
| SSH keys | Upload your public key (password login is disabled) |

Then open the firewall of the subnet: **Networking → Virtual cloud networks → your VCN → Security lists → Default security list → Add ingress rules**:

| Source | Protocol | Port | Why |
|---|---|---|---|
| `0.0.0.0/0` | TCP | 80 | HTTP, redirected to HTTPS; Let's Encrypt's check |
| `0.0.0.0/0` | TCP | 443 | HTTPS |
| `0.0.0.0/0` | UDP | 443 | HTTP/3 (optional) |

Port 22 (SSH) is open by default; if you can, restrict its source to your own IP address. Do **not** open 5432, 6379, 8000 or 5173: nothing listens there on the server.

## 2. Point the DuckDNS name at the server

Copy the VM's public IP address from its details page, then either enter it on duckdns.org or run (anywhere):

```bash
curl "https://www.duckdns.org/update?domains=<name>&token=<duckdns-token>&ip=<vm-public-ip>"
```

The answer is `OK`. `nslookup <name>.duckdns.org` should then return the VM's address.

## 3. Install Docker on the server

```bash
ssh ubuntu@<vm-public-ip>
sudo apt-get update && sudo apt-get install -y ca-certificates curl git
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker "$USER"   # then log out and in again
```

`docker compose version` must show 2.24.4 or newer.

Oracle's Ubuntu images also have a host firewall (iptables) that allows only SSH. It does not block the proxy: Docker
publishes ports 80 and 443 through its own forwarding rules (not the `INPUT` chain) and puts them in front of the image's
rules every time it starts. If HTTPS cannot be reached in step 7 although the security list allows it, check that Docker's
rules come first, and restart Docker if they are missing:

```bash
sudo iptables -L FORWARD -n --line-numbers | head -6   # Docker's chains (DOCKER-USER, DOCKER-FORWARD or DOCKER) before any REJECT
sudo systemctl restart docker                           # re-creates Docker's rules; the containers start again by themselves
```

Do not run `sudo netfilter-persistent save` while Docker is running: it would copy Docker's own rules into the firewall
that is loaded at boot.

### Prepare the server for 4 GB of memory (once, before the first build)

**Swap.** Building the images while other containers run can need more than 4 GB. Check with `free -h`; if `Swap` shows
`0B`, add a 4 GB swap file:

```bash
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab   # keep it after a reboot
swapon --show                                                # /swapfile, 4G
```

**Log rotation.** Docker keeps container logs without a size limit. The setting applies to containers created after the
restart, so make it before step 6. On a new server `/etc/docker/daemon.json` does not exist yet; if it does, add the two
settings to it instead of replacing it:

```bash
echo '{"log-driver": "json-file", "log-opts": {"max-size": "10m", "max-file": "5"}}' | sudo tee /etc/docker/daemon.json
sudo systemctl restart docker
sudo docker info --format '{{.LoggingDriver}}'               # json-file
```

Each container then keeps at most five log files of 10 MB.

**Memory overcommit for Redis.** Redis saves its data in the background with a copy of its own process. Without this
setting a save can fail when memory is tight, and Redis then refuses new jobs until a save succeeds. It is Redis's own
recommendation:

```bash
echo 'vm.overcommit_memory = 1' | sudo tee /etc/sysctl.d/99-fitscan-redis.conf
sudo sysctl --system
sysctl vm.overcommit_memory                                  # vm.overcommit_memory = 1
```

## 4. Get the code

Create a read-only deploy key on the server and add it to the repository (GitHub → the repository → **Settings → Deploy keys → Add deploy key**, "Allow write access" left off):

```bash
ssh-keygen -t ed25519 -f ~/.ssh/fitscan_deploy -N "" -C "fitscan server"
cat ~/.ssh/fitscan_deploy.pub   # paste this into the deploy key form
GIT_SSH_COMMAND="ssh -i ~/.ssh/fitscan_deploy -o IdentitiesOnly=yes" git clone git@github.com:<owner>/FITSCAN.git
cd FITSCAN
git config core.sshCommand "ssh -i ~/.ssh/fitscan_deploy -o IdentitiesOnly=yes"   # for later `git pull`
```

If the repository is public, no key is needed: `git clone https://github.com/<owner>/<repository>.git FITSCAN`, then
`cd FITSCAN`.

## 5. Configure

```bash
cp deploy/production.env.example .env
chmod 600 .env
openssl rand -hex 24                                        # a PostgreSQL password (hex: safe inside a URL)
openssl rand -base64 24                                     # the login password: store it in your password manager
docker run --rm -it caddy:2.11.9-alpine caddy hash-password # type the login password; prints its bcrypt hash
nano .env
```

In `.env`, replace every `<...>`: `FITSCAN_DOMAIN` (the host name only), `BASIC_AUTH_USER`, `BASIC_AUTH_HASH` (keep the
single quotes) and `POSTGRES_PASSWORD`. Leave `AUTO_REMATCH=false`: in production, match runs start by hand. The login
password itself never goes into a file on the server, only its hash.

Then check the file. The check reads it as text and prints key names only, never a value. It fails on a `<...>`
placeholder left in, a hash without single quotes, a database password that is short or not URL-safe, a host name with
`https://` or a path, `AUTO_REMATCH` other than `false`, a key set twice, Windows line endings, or a `.env` tracked by Git:

```bash
bash deploy/check-env.sh        # must end with "All checks passed"; fix every FAIL line and run it again
```

## 6. Start

Always use both `-f` files. A short alias, saved so that it also works in later SSH sessions, does that; every command
below uses it:

```bash
echo "alias dc='docker compose -f docker-compose.yml -f docker-compose.prod.yml'" >> ~/.bashrc
source ~/.bashrc
dc config --quiet && echo "configuration OK"   # checks both files and .env; prints no values
```

The alias needs the `docker` group from step 3 (`id -nG` lists it after logging in again). Without the group, write
`sudo docker compose` in the alias instead.

Build the images **one at a time**, then start the stack. `up --build` would build all four at once, which can run a 4 GB
server out of memory; one after the other, `worker` also reuses the Python layers that `api` has just built:

```bash
dc build proxy       # compiles Caddy with its rate-limit plugin
dc build frontend
dc build api
dc build worker      # installs Tesseract and downloads headless Chromium: the slowest
dc up -d
```

The first builds are slow; later starts take seconds. The stack runs as the Compose project `fitscan-prod`, so its
volumes (`fitscan-prod_pgdata`, `fitscan-prod_uploads`, ...) start new and empty and are separate from any local
development stack.

```bash
dc ps              # every service "healthy"; only proxy shows ports (80, 443)
dc logs -f proxy   # "certificate obtained successfully" for your domain
```

## 7. Check it

```bash
curl -s https://<name>.duckdns.org/api/health                # {"status":"ok","database":"ok","redis":"ok"} (public)
curl -s -o /dev/null -w "%{http_code}\n" https://<name>.duckdns.org/api/candidates   # 401: password required
curl -s -o /dev/null -w "%{http_code}\n" -u '<login>' https://<name>.duckdns.org/api/docs   # 404: docs are off
```

The health check is under `/api/`. Without the prefix, `https://<name>.duckdns.org/health` is an ordinary path of the
frontend: it asks for the login and then returns the application's HTML page, not JSON.

Open `https://<name>.duckdns.org` in a browser: it asks for the login, then shows the landing page; the application is at
`/app`. The API is at `https://<name>.duckdns.org/api/...`.

Then check the worker's tools on the ARM64 VM (OCR, the headless browser used for JavaScript pages, and Celery):

```bash
dc exec worker tesseract --version | head -1
dc exec worker python -c "from playwright.sync_api import sync_playwright as s; p = s().start(); b = p.chromium.launch(); print('chromium', b.version); b.close(); p.stop()"
dc exec worker celery -A app.worker.celery_app inspect ping
```

All three were also checked on ARM64 before release, under emulation. There, Chromium ran only with its JavaScript JIT
switched off, because the emulator cannot run it; the second command confirms the normal launch on real hardware.

## 8. Load synthetic demo data (never real resumes)

The server's database starts empty and is separate from your laptop's: never copy a local database, backup or upload
folder to the server. Use only invented data:

1. **Jobs.** In the application: **New crawl** → Fake Python Jobs (`https://realpython.github.io/fake-jobs/`, up to 110
   pages). Public postings from a Greenhouse or Lever board can be added the same way.
2. **Resumes.** On your laptop, generate the synthetic PDFs: `cd backend && python -m tests.resume_pdfs sample-resumes`
   (one column, two columns, a skills table, a scanned page, an encrypted and a corrupt file; the people are invented).
   Upload them with **Upload resumes**. Do not upload any real person's resume, including your own.
3. **Matches.** **Recompute matches** after the crawl and the uploads. Production keeps `AUTO_REMATCH=false`, so no match
   run starts by itself.

The optional mock site (static and JavaScript pages) is off in production. To crawl it once:

```bash
echo "CRAWLER_PRIVATE_HOST_ALLOWLIST=mock-site" >> .env
dc --profile demo up -d mock-site api worker
# crawl http://mock-site:8080/static/index.html and http://mock-site:8080/dynamic/index.html in the UI, then:
sed -i '/^CRAWLER_PRIVATE_HOST_ALLOWLIST=/d' .env
dc stop mock-site && dc up -d api worker
```

## What the proxy enforces

| Control | Setting (deploy/caddy/Caddyfile) |
|---|---|
| HTTPS | Let's Encrypt certificate, renewed automatically; HTTP redirects to HTTPS; HSTS for one year |
| Access | HTTP Basic authentication (bcrypt hash) for everything except `GET /api/health` |
| API documentation | `/api/docs`, `/api/redoc`, `/api/openapi.json` answer 404 at the proxy; the API itself also runs with `API_DOCS_ENABLED=false` |
| Rate limits, per client address | 600 requests a minute; 30 `POST` requests a minute; 10 resume uploads per 10 minutes (then 429 with `Retry-After`) |
| Request size | 52 MiB for resume uploads (the API's own limit is 50 MiB), 1 MiB for everything else (then 413) |
| Timeouts | 5 minutes to receive a request body, 10 minutes to send a response (long exports stream), 2 minutes idle |
| Caching | `Cache-Control: no-store` on every API response (candidates, logs, exports) |
| Headers | `Content-Security-Policy` (scripts, fonts and API calls from the same origin only; no framing), `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, `Cross-Origin-Opener-Policy`; no `Server` header |
| Network | Only the proxy publishes ports; PostgreSQL, Redis, the API, the worker and the frontend are reachable only inside Docker |
| CPU | The proxy may use at most one of the two CPUs (`cpus: 1.0` in docker-compose.prod.yml): each wrong password costs about 1 s of bcrypt work, so a flood of login attempts cannot starve the API, the database and the worker |

The application keeps its own protections: uploaded resumes are stored under random names and never served, responses
never contain file paths or resume text, failures show no stack traces, and logs contain no resume words. Job details and
logs reach the browser sanitised: no credentials, internal host names, IP addresses, paths, personal data or storage
names, with progress (counts, public URLs, retries, failure summaries) kept.

## Operating the server

| Task | Command |
|---|---|
| Logs | `dc logs -f --tail 100 proxy api worker` |
| Update to the latest commit | `git pull`, then `bash deploy/check-env.sh`, then the four `dc build` commands and `dc up -d` from step 6; `docker image prune -f` then removes the old images |
| Back up and restore the database | See [Backups and restore](#backups-and-restore) below |
| Delete old uploads (dry run first) | `dc exec api python -m app.services.upload_retention`, then add `--delete` |
| Change the login | Make a new hash (step 5), put it in `.env`, run `bash deploy/check-env.sh`, then `dc up -d proxy` |
| Stop (data is kept in volumes) | `dc down`. Never `dc down -v`: it deletes the database, the uploads and the certificates |
| Operating-system updates | `sudo apt-get update && sudo apt-get upgrade` (Ubuntu also installs security updates automatically) |

## Backups and restore

Backups go to `~/backups`, outside the repository folder, so a dump can never end up in Git; the folder and the dumps
are readable only by you. [`deploy/backup.sh`](backup.sh) writes each dump under a temporary name, checks that it can be
read, and only then gives it its final name, so a failed dump never looks like a good one. It deletes dumps older than
14 days (`BACKUP_KEEP_DAYS`), takes the database name and user from the `db` container, and prints no values.

```bash
bash deploy/backup.sh   # Backup written: /home/ubuntu/backups/fitscan-<date>_<time>.dump (...)
```

**Daily backups.** A systemd timer runs the script every day at 03:00 server time (UTC) and catches up on a run missed
while the server was off. It needs neither cron (not installed on the Oracle image) nor the `docker` group. The unit
assumes the user `ubuntu` and `/home/ubuntu/FITSCAN`; edit
[`deploy/systemd/fitscan-backup.service`](systemd/fitscan-backup.service) first if yours differ.

```bash
sudo cp deploy/systemd/fitscan-backup.service deploy/systemd/fitscan-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now fitscan-backup.timer
sudo systemctl start fitscan-backup.service      # one backup now, to test the unit
journalctl -u fitscan-backup -n 5 --no-pager     # "Backup written: ..."
systemctl list-timers fitscan-backup.timer       # the next run
```

A dump on the VM is lost with the VM, so copy the dumps to your laptop regularly (add `-i <private-key>` if your SSH key
is not the default one):

```bash
scp "ubuntu@<vm-public-ip>:~/backups/fitscan-*.dump" .
```

**Check that a dump can be restored** (once, after the first backup). This restores into a separate, temporary database
and deletes it again; the live database is not touched. `<file>` is a dump in `~/backups` (`ls ~/backups`):

```bash
dc exec -T db sh -c 'createdb -U "$POSTGRES_USER" restore_check'
dc exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d restore_check --no-owner' < ~/backups/<file>
dc exec -T db sh -c 'psql -U "$POSTGRES_USER" -d restore_check -Atc "select count(*) from skills"'   # 147 or more
dc exec -T db sh -c 'dropdb -U "$POSTGRES_USER" restore_check'
```

**Restore the live database from a dump.** This replaces everything in it. Stop the API and the worker first, so that
nothing writes during the restore; `--single-transaction` applies the whole dump or nothing:

```bash
dc stop api worker
dc exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner --single-transaction' < ~/backups/<file>
dc up -d
```

**Uploaded resumes** are in the `uploads` volume, not in the database. To keep them as well:

```bash
dc exec -T api tar -C /data/uploads -czf - . > ~/backups/uploads-$(date +%F).tgz
dc exec -T api tar -C /data/uploads -xzf - < ~/backups/uploads-<date>.tgz          # restore
```

The certificates (`caddy_data`) need no backup: Caddy requests new ones if the volume is lost. An Oracle boot-volume
backup covers all volumes at once, because they are stored on the boot volume: **Compute → Instances → the VM → Boot
volume → Boot volume backups → Create**. Five volume backups are free in total; delete the oldest before making a sixth,
and do not attach a backup policy (the built-in policies keep more than five).

If Redis ever exits on the VM with "Your kernel has a bug that could lead to data corruption during background save"
(Redis's ARM64 self-test), update the kernel (`sudo apt-get update && sudo apt-get full-upgrade && sudo reboot`). Do not
silence it with `ignore-warnings`. Ubuntu 24.04's kernel already contains the fix (from 2020), so this is not expected
on the VM. It does appear wrongly under emulation, for example when ARM64 images are run on an x86 laptop.

Limits of this setup: the login is one shared password (no user accounts, and a browser keeps it until it is closed);
rate limits are per IP address; and HSTS means browsers will insist on HTTPS for this host name for a year.
