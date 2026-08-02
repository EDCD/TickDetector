# Server Setup for TickDetector Deployment

This document describes the one-time manual setup required on the production
server before the GitHub Actions deploy workflow can run.

The deploy workflow is designed to **update an existing installation** — it will
not create directories, virtual environments, or install the systemd service
from scratch. All of that is done here.

---

## Overview

| Path | Purpose | Owner |
|------|---------|-------|
| `/opt/tick-detector/` | Application code + Python venv | `www-data:actions` |
| `/var/www/tick.edcd.io/` | Web root (HTML, CGI) | `www-data:actions` |
| `/etc/systemd/system/tick-detector.service` | Systemd unit file | `root:root` |

The GitHub Actions self-hosted runner executes as the `actions` user. Files are
owned by `www-data:actions` so that both the running service (as `www-data`) and
the deploy process (as `actions`) can read/write what they need.

---

## Steps

### 1. Create the `actions` group (if it doesn't exist)

```bash
sudo groupadd actions
```

### 2. Add the `actions` user to required groups

```bash
# The runner user needs to be in the 'actions' group (it should be already)
sudo usermod -aG actions actions

# Optionally add www-data to the actions group too, if the service needs
# to write files that the deploy might later overwrite
sudo usermod -aG actions www-data
```

### 3. Create application directory

```bash
sudo mkdir -p /opt/tick-detector
sudo chown www-data:actions /opt/tick-detector
sudo chmod 2775 /opt/tick-detector   # setgid so new files inherit the group
```

### 4. Create the Python virtual environment

```bash
sudo -u www-data python3 -m venv /opt/tick-detector/venv
# Fix group ownership so the actions user can install packages
sudo chgrp -R actions /opt/tick-detector/venv
sudo chmod -R g+rw /opt/tick-detector/venv
find /opt/tick-detector/venv -type d -exec chmod g+s {} \;
```

### 5. Create web root directories

```bash
sudo mkdir -p /var/www/tick.edcd.io/api
sudo mkdir -p /var/www/tick.edcd.io/cgi-bin
sudo chown -R www-data:actions /var/www/tick.edcd.io
sudo chmod -R 2775 /var/www/tick.edcd.io
```

### 6. Install the systemd service

This must be done manually (and any time the service file changes) because
writing to `/etc/systemd/system` requires root:

```bash
sudo cp config/tick-detector.service /etc/systemd/system/tick-detector.service
sudo systemctl daemon-reload
sudo systemctl enable tick-detector
```

> **Note:** If the service file changes in the repo, you'll need to re-run
> these commands manually, or add a separate privileged mechanism for it.
> The deploy workflow does not update the systemd unit.

### 7. Configure environment variables

Edit the installed service file to set the real database password and any
other environment-specific values:

```bash
sudo systemctl edit tick-detector
```

This creates an override file at
`/etc/systemd/system/tick-detector.service.d/override.conf` where you can set:

```ini
[Service]
Environment=TICK_DB_PASS=your_real_password_here
```

### 8. Grant limited sudo for service restart

The deploy workflow needs to restart the service. Create a sudoers drop-in
that allows just that, with no password:

```bash
sudo visudo -f /etc/sudoers.d/actions-tick-detector
```

Add the following content:

```
# Allow the actions user to restart the tick-detector service only
actions ALL=(root) NOPASSWD: /usr/bin/systemctl restart tick-detector
```

### 9. Start the service

```bash
sudo systemctl start tick-detector
sudo systemctl status tick-detector
```

---

## Verifying permissions

After setup, verify the actions user can do everything it needs without sudo:

```bash
# Switch to the actions user
sudo -u actions bash

# Can write to app directory?
touch /opt/tick-detector/.deploy-test && rm /opt/tick-detector/.deploy-test

# Can write to web root?
touch /var/www/tick.edcd.io/.deploy-test && rm /var/www/tick.edcd.io/.deploy-test

# Can install pip packages?
/opt/tick-detector/venv/bin/pip install --dry-run requests

# Can restart the service?
sudo systemctl restart tick-detector
```

---

## Updating the systemd service file

Since the deploy workflow cannot write to `/etc/systemd/system`, any changes
to `config/tick-detector.service` in the repo need to be applied manually:

```bash
sudo cp /opt/tick-detector/../<repo-checkout>/config/tick-detector.service \
        /etc/systemd/system/tick-detector.service
sudo systemctl daemon-reload
sudo systemctl restart tick-detector
```

Or from a local clone:

```bash
sudo cp config/tick-detector.service /etc/systemd/system/tick-detector.service
sudo systemctl daemon-reload
sudo systemctl restart tick-detector
```
