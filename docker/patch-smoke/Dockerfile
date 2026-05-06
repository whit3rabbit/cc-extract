FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /work

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates libstdc++6 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY ccsilo ./ccsilo
COPY tools ./tools

RUN python -m pip install --upgrade pip \
    && python -m pip install -e .

ENTRYPOINT ["python", "tools/check_patch_releases.py"]
CMD ["--latest", "--run-smoke"]
