# Frontend agent notes

TypeScript and TSX source files start with a header comment:

```typescript
/**
 * Purpose: What this file is responsible for.
 *
 * Public API:
 * - ExportedName
 */
```

Every function and component has a short JSDoc description. The browser talks only to Next.js. `/api/backend` is rewritten to the FastAPI service.

Each subfolder has its own `AGENTS.md` for what belongs there. New TypeScript and TSX files still use the header above.

Keep `package-lock.json` current; image builds use `npm ci` for reproducible installs. The pinned PostCSS override addresses source-map disclosure advisories, and the scoped Undici override removes vulnerable HTTP/multipart dependencies from `@ai-sdk/provider-utils`. Recheck these overrides when upgrading Next.js or the AI SDK; run `npm audit`, `npm test`, and `npm run build` through Docker Compose after dependency changes.

`tests/` contains mocked API helper regressions run with `npm test` through Ubuntu Docker Compose. Editor mutations use the API helper's `X-Write-Id` receipt support; preserve retry identity when a response is lost rather than inventing a new write.
