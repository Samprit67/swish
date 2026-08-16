# syntax=docker/dockerfile:1
FROM python:3.12-slim AS build
WORKDIR /app
COPY pyproject.toml README.md ./
COPY swish ./swish
RUN pip install --no-cache-dir --prefix=/install .

FROM python:3.12-slim
LABEL org.opencontainers.image.title="Swish" \
      org.opencontainers.image.description="Estimate an NBA player's trade value from his stats and contract" \
      org.opencontainers.image.licenses="MIT"

RUN useradd --create-home --uid 1000 swish && mkdir /data && chown swish:swish /data
COPY --from=build /install /usr/local
USER swish

# The Basketball-Reference page cache lives here — mount a volume to keep it.
ENV SWISH_CACHE=/data/cache.db \
    SWISH_HOST=0.0.0.0 \
    SWISH_PORT=8770
VOLUME /data
EXPOSE 8770

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8770/api/health').status==200 else 1)"

ENTRYPOINT ["swish"]
CMD ["serve", "--no-open"]
