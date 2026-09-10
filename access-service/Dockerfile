FROM python:3.12-slim-bookworm@sha256:782412e85d0f0984994c290652577d4018aff08145c85b262bb63dc0c7522254
ARG VERSION=development
ARG REVISION=unknown
LABEL org.opencontainers.image.title="CLI access management" \
      org.opencontainers.image.source="https://github.com/mossexplore/platform-cli" \
      org.opencontainers.image.version=$VERSION \
      org.opencontainers.image.revision=$REVISION
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    LISTEN_HOST=0.0.0.0 LISTEN_PORT=8008
WORKDIR /app
COPY requirements.lock ./requirements.lock
RUN python -m pip install --no-cache-dir --only-binary=:all: -r requirements.lock \
    && python -m pip check \
    && groupadd --gid 10001 cli-access \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin cli-access
COPY app ./app
USER 10001:10001
EXPOSE 8008
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-m", "app.healthcheck"]
CMD ["python", "-m", "app.serve"]
