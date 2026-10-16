# LocalJev server adapter

Vendored from https://github.com/githubnext/localjev at
`3f23e36e1a3bff46c7e83e8e3781d3512bc82021` (MIT; see LICENSE).
Only the dependency-free API runtime, tests and build metadata are included.
Local changes: explicit `LOCALJEV_OUTPUT_MODE=json_object` for cloud APIs without
strict JSON Schema support. The schema remains in the system prompt; local
validation and bounded malformed-output repair apply in both modes.

Run `bun install --frozen-lockfile`, `bun run typecheck`, `bun test` here to verify.
The server image runs Bun 1.3.5 without installing development dependencies.
