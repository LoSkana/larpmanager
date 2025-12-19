# LarpManager

LarpManager is a free platform to manage live-action roleplaying (LARP) events.

If you don’t want to self-host, you can use the free hosted instance at:
https://larpmanager.com

---

## Documentation

- **[Features and Permissions Guide](docs/01-features-and-permissions.md)** - How to create new features, views, and permissions
- **[Roles and Context Guide](docs/02-roles-and-context.md)** - How to structure views with context and understand role-based permissions
- **[Configuration System Guide](docs/03-configuration-system.md)** - How to add customizable settings without modifying models
- **[Localization Guide](docs/04-localization.md)** - How to write translatable code and manage translations
- **[Playwright Testing Guide](docs/05-playwright-testing.md)** - How to write and run end-to-end tests
- **[Feature Descriptions](docs/06-feature-descriptions.md)** - Complete reference of all available features
- **[Developer Instructions](#develop)** - Architecture, commands and best practices
- **[Contributing](#contributing)** - How to contribute to the project
- **[Deployment](#deploy)** - Production deployment instructions

---

## Licensing

LarpManager is distributed under a **dual license** model:

- **Open Source (AGPLv3)** — Free to use under the terms of the AGPLv3 license.
  If you host your own instance, you must publish any modifications and include a visible link to [larpmanager.com](https://larpmanager.com) on every page of the interface.

- **Commercial License** — Allows private modifications and removes the attribution requirement.
  For details or licensing inquiries, contact [commercial@larpmanager.com](mailto:commercial@larpmanager.com).

Refer to the `LICENSE` file for full terms.

---

## Quick start (Docker)

If you want an easy and fast deploy, set the environment variables see below for [instructions](#environment) on their values:

```
cp .env.example .env
```

Now time for the docker magic (see below for [instructions](#docker) on installing it):

```
docker compose up --build
```

Now create a super user:

```
docker exec -it larpmanager python manage.py createsuperuser
```

Go to `http://127.0.0.1:8264/admin/larpmanager/association/`, and create your Organization. Put as values only:
- Name: you should get it;
- URL identifier: put `def`;
- Logo: an image;
- Main mail: the main mail of the organization (duh)

Leave the other fields empty, and save.

Now expose the port 8264 (we wanted a fancy one) to your reverse proxy of choice for public access. Example configuration for nginx, place this code in `/etc/nginx/sites-available/example.com`:

```
server {
    listen 80;
    server_name example.com;

    location / {
        proxy_pass http://localhost:8264;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

Now create the symlink:

```
ln -s /etc/nginx/sites-available/example.com /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
```

Now you're ready for liftoff!

---

*Windows user*: On some cases the docker fails to start up, you might want to try

```
dos2unix scripts/entrypoint.sh
```

---

If you want some more extra juicy stuff, you can set an automatic execution of

```
docker exec -it larpmanager python manage.py automate
```

This command performs a bunch of stuff related to advanced features; it should be run each day (cron?), when low traffic is expected (night?). You _should_ combine it with the daily backup of `pgdata` and `media_data` volumes.

---

In the future, if you want to pull the latest changes of the repo, go with:

```
git pull origin main
docker exec -it larpmanager scripts/deploy.sh
```

It will perform a graceful restart.

---

### Cloud recommendations

Suggested baseline for cloud VMs:
- OS: Ubuntu 24.04 LTS (required for Python 3.12)
- Instance type: burstable instance to handle activity spikes
-
Some typical options could be:
- EC2: t3.small / t3.medium
- GCP: e2-small / e2-medium
- Azure: B1ms / B2s

---

### Environment variables

Set those values:
- GUNICORN_WORKERS: Rule of thumb is number of processors * 2 + 1
- SECRET_KEY: A fresh secret key, you can use an [online tool](https://djecrety.ir/)
- ADMIN_NAME, ADMIN_EMAIL: Set your own info
- DB_NAME, DB_USER, DB_PASS, DB_HOST: The database will be generated based on those values if it does not exists
- TZ: The base timezone of the server
- GOOGLE_CLIENTID, GOOGLE_SECRET: (Optional) If you want Google SSO, follow the [django-allauth guide](https://docs.allauth.org/en/dev/socialaccount/providers/google.html)
- RECAPTCHA_PUBLIC, RECAPTCHA_PRIVATE: If you want recaptcha checks, follow the [django-recaptcha guide](https://cloud.google.com/security/products/recaptcha)

---

### Docker installation

To install everything needed for the quick setup, install some dependencies:

```
sudo apt update
sudo apt install apt-transport-https ca-certificates curl software-properties-common
```

add docker's repo:

```
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo apt-key add -
sudo add-apt-repository "deb [arch=amd64] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable"
```

finally, install Docker:

```
sudo apt-get update
sudo apt-get install docker-ce docker-ce-cli containerd.io docker-compose-plugin
```

run it:

```
sudo systemctl start docker
sudo systemctl enable docker
```

---

## Local Setup

The typical, recommended setup is to have:
* On a server the *production* instance, managed with docker, with the real user data, CI pipeline, automated backup and all other devops best practices;
* On your local machine, a *development* instance, managed with dedicated system installations, dummy test database and local development server.

Here are the step for a local setup on your machine, required for both *Develop* and *Contributing*.

**Requirements:**
- Python 3.12 or higher
- Ubuntu 24.04 LTS recommended

For a Debian-like system: install the following packages:

```bash
# On Ubuntu 24.04 LTS
sudo apt install python3.12 python3.12-venv python3.12-dev python3-pip redis-server git \
  postgresql postgresql-contrib libpq-dev nodejs build-essential libxmlsec1-dev \
  libxmlsec1-openssl libavif16 libcairo2-dev pkg-config

# On Ubuntu 22.04 or older (requires deadsnakes PPA for Python 3.12)
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt update
sudo apt install python3.12 python3.12-venv python3.12-dev python3-pip redis-server git \
  postgresql postgresql-contrib libpq-dev nodejs build-essential libxmlsec1-dev \
  libxmlsec1-openssl libavif16 libcairo2-dev pkg-config
```

Create and activate a virtual environment:
```bash
python3.12 -m venv venv
source venv/bin/activate
```

Install Python dependencies:
```bash
pip install -r requirements.txt
```

Install and activate LFS to handle big files:
   ```bash
   sudo apt install git-lfs
   git lfs install
   git lfs pull
   ```

### Database Setup

Create the PostgreSQL database and user:
```bash
sudo -u postgres psql
```

Then run the following SQL commands:
```sql
CREATE DATABASE larpmanager;
CREATE USER larpmanager WITH PASSWORD 'larpmanager';
ALTER USER larpmanager CREATEDB;
ALTER DATABASE larpmanager OWNER TO larpmanager;
GRANT ALL PRIVILEGES ON DATABASE larpmanager TO larpmanager;
\q
```

### Django Configuration

1. Copy `main/settings/dev_sample.py` to `main/settings/dev.py`:
   ```bash
   cp main/settings/dev_sample.py main/settings/dev.py
   ```

2. The default database settings should work with the setup above. If you used different credentials, update the `DATABASES` section in `main/settings/dev.py`.

3. In `SLUG_ASSOC`, put the slug of the organization that will be loaded (default is `def`).


### Frontend Dependencies

Install npm modules for frontend functionality:
```bash
cd larpmanager/static
npm install
cd ../..
```

### Testing Setup

Install Playwright browsers for end-to-end tests:
```bash
playwright install
```


## Develop

The codebase is based on Django; if you're not already familiar with it, we highly suggest you to follow the tutorials at https://docs.djangoproject.com/.

1. Follow the steps outlined in [Local setup](#local-setup) for setting up your local *development* instance

2. Run migrations to initialize the database:
   ```bash
   python manage.py migrate
   ```

3. Load the initial test data:
   ```bash
   python manage.py reset
   ```

4. Now you can run the local server for manual testing and debugging:
```bash
python manage.py runserver
```

---

## Contributing

Thanks in advance for contributing! Here's the steps:

1. Follow the steps outlined in [Local setup](#local-setup) for setting up your local *development* instance

2. Install and activate `pre-commit`:
   ```bash
   pip install pre-commit
   pre-commit install
   ```

3. In the `main/settings/dev.py` settings file, add a `DEEPL_API_KEY` value. You can obtain a API key for the *DeepL API Free* (up to 500k characters monthly) [here](https://www.deepl.com/en/pro).

4. Create a new branch:
   ```bash
   git checkout -b prefix/feature-name
   ```
   For the prefix please follow this naming strategy:
   - *hotfix* for urgent fixes in production
   - *fix* for correction to existing functions
   - *feature* for introducing / upgrading functions
   - *refactor* for code changes not related to functions
   - *locale* for changes in translation codes.

5. When you'are ready with the code changes, to make sure that all entries have been translated (default language is English), run
   ```bash
   ./scripts/translate.sh
   ```
   This will updated all your translations, have correct the untranslated / fuzzy ones with Deepl API. In the terminal, take some time to review them before proceeding.
6. If you're creating a new feature, write a playwright test suite that covers it. Look in the `larpmanager/tests` folder to see how it's done. (Standard users are "orga@test.it" and "user@test.it", both with password "banana"). Run
   ```bash
   ./scripts/record-test.sh
   ```
   To run an instance of playwright that will record all your actions, in code that can later be inserted into the test.
7. If you're changing the model or the fixtures, run:
   ```bash
   python manage.py dump_test
   ```
   to update the dump used by tests and ci.
8. Before pushing make sure that all the tests passes using:
   ```bash
   pytest
   ```
   *Note that the tests will take some time to complete*.
9. When you're ready to push your new branch, run
   ```bash
   ./scripts/upgrade.sh
   ```
   This will execute some helpful activities like making sure you're updated with main branch, deleting old local branches, and other small things like that.

10. Go and open [a new pull request](https://github.com/loskana/larpmanager/pulls). Make sure to explain clearly in the description what's happening.


### Guidelines

Pull Requests should include **only the minimal changes necessary** to achieve their goal.
Avoid non-essential changes such as refactoring, renaming, or reformatting — **unless explicitly approved beforehand**.

This helps keep code reviews focused, reduces merge conflicts, and maintains a clean commit history.
If you believe a refactor is needed, please open an issue or start a discussion first to get approval.
