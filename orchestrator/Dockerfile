ARG ARG_PYTHON_TAG=3-slim
ARG FROM_IMAGE=python:${ARG_PYTHON_TAG}

FROM $FROM_IMAGE

LABEL org.opencontainers.image.authors="infrastructure@horizen.io"

ARG ARG_WORKDIR=/app
ARG ARG_VIRTUAL_ENV=/opt/venv
ARG ARG_GOSU_VERSION=1.17
ARG ARG_MIGRATION_REPO=https://github.com/HorizenOfficial/horizen-migration.git
ARG ARG_MIGRATION_COMMITTISH=1.3.1

ENV VIRTUAL_ENV="$ARG_VIRTUAL_ENV" \
    GOSU_VERSION="$ARG_GOSU_VERSION" \
    PATH="$ARG_VIRTUAL_ENV/bin:$ARG_WORKDIR:$PATH" \
    WORKDIR="$ARG_WORKDIR" \
    PYTHONUNBUFFERED=1 \
    MIGRATION_REPO="$ARG_MIGRATION_REPO" \
    MIGRATION_COMMITTISH="$ARG_MIGRATION_COMMITTISH"

WORKDIR $WORKDIR

SHELL ["/bin/bash", "-c"]

COPY ./requirements.txt ./pyproject.toml ./orchestrator.py ./entrypoint.sh ./

RUN set -eEuo pipefail  \
    && mv entrypoint.sh /usr/local/bin/entrypoint.sh \
    && chmod +x /usr/local/bin/entrypoint.sh orchestrator.py \
    && mkdir -p "$VIRTUAL_ENV" \
    && apt-get -qq update && DEBIAN_FRONTEND=noninteractive apt-get -qqy dist-upgrade \
    && savedAptMark="$(apt-mark showmanual)" \
    && DEBIAN_FRONTEND=noninteractive apt-get -qqy install --no-install-recommends git \
    && if ! command -v gosu &> /dev/null; then \
      if ! command -v gpg2 &> /dev/null; then \
        DEBIAN_FRONTEND=noninteractive apt-get install -qqy --no-install-recommends gnupg2 dirmngr ca-certificates curl; \
      fi \
      && dpkgArch="$(dpkg --print-architecture | awk -F- '{ print $NF }')" \
      && curl -sSfL "https://github.com/tianon/gosu/releases/download/$GOSU_VERSION/gosu-$dpkgArch" > /usr/local/bin/gosu \
      && curl -sSfL "https://github.com/tianon/gosu/releases/download/$GOSU_VERSION/gosu-$dpkgArch.asc" > /usr/local/bin/gosu.asc \
      && export GNUPGHOME="$(mktemp -d)" \
      && ( gpg2 --batch --keyserver hkps://keys.openpgp.org --recv-keys B42F6819007F00F88E364FD4036A9C25BF357DD4 || \
       gpg2 --batch --keyserver hkps://keyserver.ubuntu.com:443 --recv-keys B42F6819007F00F88E364FD4036A9C25BF357DD4 || \
       gpg2 --batch --keyserver pgp.mit.edu --recv-key B42F6819007F00F88E364FD4036A9C25BF357DD4 ) \
      && gpg2 --batch --verify /usr/local/bin/gosu.asc /usr/local/bin/gosu \
      && ( gpgconf --kill dirmngr || true ) \
      && ( gpgconf --kill gpg-agent || true ) \
      && rm -rf "$GNUPGHOME" /usr/local/bin/gosu.asc \
      && unset GNUPGHOME \
      && chmod +x /usr/local/bin/gosu \
      && gosu --version; \
    fi \
    && python -m venv "$VIRTUAL_ENV" \
    && . "$VIRTUAL_ENV/bin/activate" \
    && python -m pip install --no-cache-dir --upgrade --require-virtualenv pip \
    && python -m pip install --no-cache-dir --require-virtualenv --require-hashes -r requirements.txt \
    && python -m pip install --no-cache-dir --require-virtualenv . \
    && git clone --branch "$MIGRATION_COMMITTISH" --single-branch "$MIGRATION_REPO" --depth 1 ./horizen-migration \
    && python -m pip install --no-cache-dir --require-virtualenv -r ./horizen-migration/dump-scripts/python/requirements.txt \
    && python -m pip install --no-cache-dir --require-virtualenv -e ./horizen-migration/dump-scripts/python \
    && apt-mark auto '.*' &> /dev/null && [ -z "$savedAptMark" ] || apt-mark manual $savedAptMark &> /dev/null \
    && DEBIAN_FRONTEND=noninteractive apt-get purge -qqy --auto-remove -o APT::AutoRemove::RecommendsImportant=false \
    && rm -rf /var/cache/apt/archives/*.deb /var/lib/apt/lists/* /root/.cache /tmp/*

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]

CMD ["orchestrator"]
