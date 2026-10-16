FROM oven/bun:1.3.5-slim@sha256:6111acec4c5a703f2069d6e681967c047920ff2883e7e5a5e64f4ac95ddeb27f
WORKDIR /app
COPY deploy/localjev/src ./src
COPY deploy/localjev/package.json ./package.json
COPY deploy/localjev/LICENSE ./LICENSE
USER bun
ENV LOCALJEV_HOST=0.0.0.0 LOCALJEV_PORT=8080
CMD ["bun", "run", "src/index.ts"]
