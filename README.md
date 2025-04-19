#  LarpManager

**LarpManager** is a free and open-source platform to manage **LARP (Live Action Role-Playing)** events.
It supports organizers in every step: managing registrations, payments, characters and logistics.

> Not interested in self-hosting? Start using it right away at [https://larpmanager.com](https://larpmanager.com)

![License: AGPL or Commercial](https://img.shields.io/badge/license-AGPL%20%2F%20Commercial-blue.svg)

---

## 🛡️ Licensing

LarpManager is available under a **dual license**:

- **AGPLv3** (Open Source): Use freely under AGPL terms. Modifications must be published if hosted.
- **Commercial License**: Use in closed-source/proprietary projects. Contact [commercial@larpmanager.com](mailto:commercial@larpmanager.com) for info.

See the LICENSE file for details.

---

## Install

A typical installation requires:
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
python manage.py makemigrations larpmanager
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

In the future, when you want to update with the latest updates of the master branch, run
   ```bash
   ./scripts/deploy.sh
   ```
This will update the code, the virtual env requirements, the npm modules, the static files, the language translations, the features and permissions.

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

2. In the `main/settings/dev.py` settings file, add a `DEEPL_API_KEY` value. You can obtain a API key for the *DeepL API Free* (up to 500k characters monthly) [here](https://www.deepl.com/en/pro).

3. Create a new branch:
   ```bash
   git checkout -b prefix/feature-name
   ```
   For the prefix please follow this naming strategy:
   - *hotfix* for urgent fixes in production
   - *fix* for correction to existing functions
   - *feature* for introducing / upgrading functions
   - *refactor* for code changes not related to functions
   - *locale* for changes in translation codes.

4. When you'are ready with the code changes, make sure that all entries have been translated (default language is English.) Run
   ```bash
   ./scripts/translate.sh
   ```
   This will updated all your translations, have correct the untranslated / fuzzy ones with Deepl API. In the terminal, take some time to review them before proceeding.
5. If you're creating a new feature, write a playwright test suite that covers it. Look in the `larpmanager/tests` folder to see how it's done. Run
   ```bash
   ./scripts/record-test.sh
   ```
   To run an instance of playwright that will record all your actions, in code that can later be inserted into the test.
6. Before pushing make sure that all the tests passes using:
   ```bash
   pytest
   ```
   *Note that the tests will take some time to complete*.
7. When you're ready to push your new branch, run
   ```bash
   ./scripts/upgrade.sh
   ```
   This will execute some helpful activities like making sure you're updated with master branch, deleting old local branches, and other small things like that.
8. Go and open [a new pull request](https://github.com/loskana/larpmanager/pulls). Make sure to explain clearly in the description what's happening.

### New features

If you want to develop a new feature, usually you follow this steps:
- Create a new `Feature` object that encapsulates the new functionalities. Set `overall` if it applies to whole organization.
- Create new views. Follow the standard of the prefix `orga_` if it applies to the single event, and the prefix `exe_` if it applies to the whole organization;
- Create the corresponding `AssocPermission` and/or `EventPermission`. Put the name of the views as `slug`, and the feature object as `feature`.

Before pushing your changes, run `python manage.py export_features` to update the fixtures with your new elements.

*Note that the corresponding `python manage.py import_features`, that reloads features and permissions from the fixtures, is run during the deploy script*


### Guidelines

Pull Requests should include **only the minimal changes necessary** to achieve their goal.
Avoid non-essential changes such as refactoring, renaming, or reformatting — **unless explicitly approved beforehand**.

This helps keep code reviews focused, reduces merge conflicts, and maintains a clean commit history.
If you believe a refactor is needed, please open an issue or start a discussion first to get approval.
