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

`tests/` contains mocked API helper regressions run with `npm test` through Ubuntu Docker Compose. Editor mutations use the API helper's `X-Write-Id` receipt support; preserve retry identity when a response is lost rather than inventing a new write.
