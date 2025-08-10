#  LarpManager

**LarpManager** is a free and open-source platform to manage **LARP (Live Action Role-Playing)** events.
It has everything you need to run your LARP, free & open source!

> Not interested in self-hosting? Start using it right away at [https://larpmanager.com](https://larpmanager.com)!

![License: AGPL or Commercial](https://img.shields.io/badge/license-AGPL%20%2F%20Commercial-blue.svg)

---

## Licensing

LarpManager is available under a **dual license**:

- **AGPLv3** (Open Source): Use freely under AGPL terms. Modifications must be published if hosted.
- **Commercial License**: Use in closed-source/proprietary projects. Contact [commercial@larpmanager.com](mailto:commercial@larpmanager.com) for info.

See the LICENSE file for details.

---

## Quick set up

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

## Cloud

For cloud deploy, we suggest the following configuration:
- OS: Ubuntu 22.04 LTS
- A "burstable" instance (instead of memory or compute-optimized), as to allow to better handle bursts of user activity

Some typical options could be:
- EC2: t3.small / t3.medium
- GCP: e2-small / e2-medium
- Azure: B1ms / B2s

---

## Environment

Set those values:
- GUNICORN_WORKERS: Rule of thumb is number of processors * 2 + 1
- SECRET_KEY: A fresh secret key, you can use an [online tool](https://djecrety.ir/)
- ADMIN_NAME, ADMIN_EMAIL: Set your own info
- DB_NAME, DB_USER, DB_PASS, DB_HOST: The database will be generated based on those values if it does not exists
- TZ: The base timezone of the server
- GOOGLE_CLIENTID, GOOGLE_SECRET: (Optional) If you want Google SSO, follow the [django-allauth guide](https://docs.allauth.org/en/dev/socialaccount/providers/google.html)
- RECAPTCHA_PUBLIC, RECAPTCHA_PRIVATE: If you want recaptcha checks, follow the [django-recaptcha guide](https://cloud.google.com/security/products/recaptcha)

---

## Docker

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

## Install

If you're old school, a typical installation requires:
- **Database**: PostgreSQL
- **Frontend**: Npm
- **Caching**: Redis
- **Deployment**: Gunicorn + Nginx
- **Email**: Postfix
- **Utils**: Wkhtmltopdf, Imagemagick

For a setup on a Debian-like system, install the following packages:
```
python3-pip redis-server postfix git postgresql postgresql-contrib
nginx libpq-dev wkhtmltopdf nodejs build-essential
libxmlsec1-dev libxmlsec1-openssl libavif16
```

Remember to init the database:
```
python manage.py migrate
```

Load npm modules:
```
cd larpmanager/static
npm install
```

And install playwright for tests:
```
playwright install
```

---

## Deploy

In order to deploy:
1. Copy `main/settings/prod_sample.py` to `main/settings/prod.py`
2. Set the settings (standard django installation)
3. Follow the instructions of [django-allauth](https://docs.allauth.org/en/dev/socialaccount/providers/google.html) to setup login with google social provider
4. Set `postgresql` and `redis` sockets (or with port mapping, your choice)
4. Load the fixtures with `python manage.py reset`. It will create a test organization with three users, `admin` (superuser), `orga@test.it` (organizer with role access to organization and test event), `user@test.it` (simple user). The password for all of them is `banana`.
5. In `SLUG_ASSOC`, put the slug of the organization that will be loaded (by default `test`)

---

## Develop

In order to develop:

1. Copy `main/settings/dev_sample.py` to `main/settings/dev.py`
2. In `DATABASES`, put the settings for database connection
3. In `SLUG_ASSOC`, put the slug of the organization that will be loaded (by default `test`)
4. Load the fixtures with `python manage.py reset`.

---

## Contributing

Thanks in advance for contributing! Here's the steps:

1. Install and activate `pre-commit`:
   ```bash
   pip install pre-commit
   pre-commit install
   ```

2. Install and activate LFS to handle big files (like the test dump):
   ```bash
   sudo apt install git-lfs
   git lfs install
   git lfs pull
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
6. If you're creating a new feature, write a playwright test suite that covers it. Look in the `larpmanager/tests` folder to see how it's done. Run
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

### New features

If you want to develop a new feature, usually you follow this steps:
- Create a new `Feature` object that encapsulates the new functionalities. Set `overall` if it applies to whole organization.
- Create new views. Follow the standard of the prefix `orga_` if it applies to the single event, and the prefix `exe_` if it applies to the whole organization;
- Create the corresponding `AssocPermission` and/or `EventPermission`. Put the name of the views as `slug`, and the feature object as `feature`.

Before pushing your changes, run `python manage.py export_features` to update the fixtures with your new elements.

Please note that adding new fields to the existing models can be added only if they are fields used by *every* instance on that model.
If some instance of that model would not use the new field, it's best to think of an alternative solution (like using `EventConfig`, `RunConfig` or `AssocConfig`).

*Note that the corresponding `python manage.py import_features`, that reloads features and permissions from the fixtures, is run during the deploy script*


### Guidelines

Pull Requests should include **only the minimal changes necessary** to achieve their goal.
Avoid non-essential changes such as refactoring, renaming, or reformatting — **unless explicitly approved beforehand**.

This helps keep code reviews focused, reduces merge conflicts, and maintains a clean commit history.
If you believe a refactor is needed, please open an issue or start a discussion first to get approval.
