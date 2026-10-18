# Bridge backend — container image.
#
# Sized for Render's free tier: one small image, no build-time database access, and it listens
# on whatever $PORT the platform injects. Migrations are NOT run at container start — see the
# note at the bottom, because two replicas racing to `alter table` is how demos break.

FROM python:3.14-slim

# uv resolves from uv.lock, so the image gets exactly the locked versions. Only the binary is
# copied; there is no pip/venv juggling.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH

WORKDIR /app

# Dependencies first: this layer only rebuilds when the lockfile changes, so a code push reuses
# it and the build stays quick.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

# Then the application. alembic/ and supabase/ ship along so `uv run alembic upgrade head`
# works inside a running container when you do want to migrate by hand.
COPY alembic.ini pyproject.toml ./
COPY alembic ./alembic
COPY app ./app
COPY supabase ./supabase
COPY scripts ./scripts

RUN uv sync --frozen --no-dev

# Never run as root in a container that sits on the public internet.
RUN useradd --create-home --uid 1001 bridge
USER bridge

# Render routes the service's public hostname to $PORT. `--proxy-headers` matters because TLS
# ends at the platform, and Supabase redirect URIs are built from the visible host.
EXPOSE 10000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-10000} --proxy-headers --forwarded-allow-ips='*'"]

# Migrations, deliberately manual. On Render with more than one instance, an entrypoint that
# runs `alembic upgrade head` has two containers racing the same DDL; and the hosted project is
# managed through the dashboard anyway (see README, "Alembic and the transaction pooler").
#
#   docker run --rm -e DATABASE_URL=... bridge-backend uv run alembic upgrade head
