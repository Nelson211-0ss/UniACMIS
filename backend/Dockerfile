# syntax=docker/dockerfile:1

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# No apt layer: psycopg[binary] ships its own libpq, so the image needs no system
# packages. Translation catalogues (NFR-USE-01) are compiled in CI where gettext
# is available, and the .mo files are copied in — keeping this image small and
# buildable on a slow or partially-mirrored connection, which matters when the
# build runs on-site.
WORKDIR /app


FROM base AS dev

COPY requirements/ requirements/
RUN pip install --no-cache-dir -r requirements/dev.txt

COPY . .


FROM base AS prod

COPY requirements/ requirements/
RUN pip install --no-cache-dir -r requirements/prod.txt

COPY . .

RUN python manage.py collectstatic --noinput --settings=config.settings.build || true

# Runs unprivileged: an on-premise box with a small ICT team should not be
# running the app tier as root.
RUN useradd --system --create-home --shell /usr/sbin/nologin uniacmis \
    && chown -R uniacmis:uniacmis /app
USER uniacmis

EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "4", "--timeout", "60"]
