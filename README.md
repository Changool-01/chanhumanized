# Chan Humanized AI

Django app that rewrites AI-generated sentences and paragraphs into more natural writing.

**Public name:** Chan Humanized AI  
**Stack:** Django 5, MySQL (or SQLite for first run), HTML/CSS/JS, OpenAI `gpt-4o-mini`

This is a style rewriter. It does not claim text is “AI-free” and it does not score or evade detectors.

## Where things live

| Path | What to edit |
|---|---|
| `apps/accounts/` | User, login, register, dashboard |
| `apps/humanizer/services/` | Word count, quota, chunking, OpenAI |
| `apps/humanizer/views.py` | Workspace, JSON `/app/humanize/`, history |
| `apps/pages/` | Landing, pricing, terms, privacy |
| `templates/` | HTML |
| `static/css/tokens.css` | Colors and type |
| `static/js/workspace.js` | Humanize / copy / download |

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Put OPENAI_API_KEY in .env (required to Humanize)
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open http://127.0.0.1:8000/

SQLite is the default (`DJANGO_DB=sqlite`). For MySQL:

```bash
docker compose up -d mysql
# in .env: DJANGO_DB=mysql
python manage.py migrate
```

## Tests

```bash
python manage.py test
```

## PythonAnywhere (free demo)

1. Upload this project (git clone or zip).
2. Create a virtualenv, `pip install -r requirements.txt`.
3. Create a MySQL database in the PA dashboard.
4. Web app: WSGI file should set `DJANGO_SETTINGS_MODULE=config.settings` and `sys.path` to the project folder that contains `manage.py`.
5. Environment variables: `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=False`, `DJANGO_ALLOWED_HOSTS=yourusername.pythonanywhere.com`, `DJANGO_DB=mysql`, MySQL name/user/password/host (PA shows the host), `OPENAI_API_KEY`.
6. `python manage.py migrate` and `python manage.py collectstatic`.
7. Set a **hard monthly budget** in the OpenAI dashboard ($10–20 for a demo).

`api.openai.com` is allowlisted on free PythonAnywhere, so Humanize can work without a paid PA plan. There is no custom domain on the free plan.

Stripe Pro checkout is **not** in this build.

## Plans (in software)

- **Free:** 100,000 words/week, 500 words/request
- **Pro:** UI says Unlimited; server cap 1,000,000 words/week, 600/request (gift Pro in Django admin → Profile)

## Model choice

Default model is `gpt-4o-mini` (cheap, good for demos). To switch to `gpt-4o` for stronger quality, set in `.env`:

```bash
OPENAI_MODEL=gpt-4o
```

Cost is roughly 15x higher (input ~$2.50/1M tokens, output ~$10/1M tokens vs $0.15/$0.60 for mini). The app uses a multi-candidate + two-pass flow, so each request calls the model several times.

## Humanize flow

1. Generate **3 first-pass candidates**.
2. Score them locally for short sentences, simple words, function words, and repetition.
3. Pick the best candidate.
4. Run the **audit/tighten pass** on the best candidate.

To change the number of candidates, set in `.env`:

```bash
HUMANIZE_CANDIDATES=3
```

Set to `1` to disable candidate selection and reduce cost.

## Security

Deferred. This build uses Django’s default CSRF on forms and secrets in `.env` only.
