# CLAUDE.md

## Project Overview

<!-- Brief description of what this project does, its purpose, and key stakeholders -->

## Tech Stack

<!-- Fill in your actual stack -->

## Architecture Principles

### Layered Architecture
- **Controllers/Handlers** — Handle protocol concerns only (HTTP, gRPC, CLI). Parse input, call services, return responses. No business logic
- **Services** — All business logic lives here. Services never import from handlers
- **Repositories/Data Access** — All database queries go here, nowhere else. Return domain objects, not raw rows
- **Domain Models** — Plain objects/types representing business entities. No framework or infrastructure dependencies

### Dependency Direction
- Dependencies flow inward: handlers → services → repositories → domain
- Never import from an outer layer into an inner layer
- Use dependency injection for cross-cutting concerns (logging, metrics, auth)

### Module Boundaries
- Each feature is self-contained with its own handlers, services, repositories, and types
- Shared utilities should be minimal — if only one feature uses it, it belongs in that feature
- No circular dependencies between feature modules. If two features need to communicate, extract a shared service or use events

### Separation of Concerns
- Configuration lives in one place, loaded at startup, and passed explicitly
- Side effects (I/O, network, filesystem) happen at the edges, not deep in business logic
- Pure functions for business rules wherever possible

## Code Quality Standards

### Error Handling
- Use typed/structured errors with error codes — not raw strings
- Never catch and swallow errors silently. Log or rethrow
- Validate all external input at system boundaries (API routes, queue handlers, CLI args) using a schema validation library
- Internal function calls between trusted layers don't need redundant validation
- Fail fast on unrecoverable errors. Don't add retry logic unless the failure is transient

### Database
- Every schema change requires a migration — never modify the database manually
- Use transactions for operations that touch multiple tables
- Add indexes for columns used in WHERE clauses or JOINs on tables expected to grow
- N+1 queries are bugs. Use joins or batch queries
- Use parameterized queries exclusively — no string interpolation in SQL

### API Design
- Consistent resource naming and response shapes across all endpoints
- Paginate all list endpoints with sensible defaults and max limits
- Return meaningful error responses with codes, not just status numbers
- Version your API when breaking changes are unavoidable

### Testing
- Unit tests for all service-layer business logic
- Integration tests for API endpoints and data access against a real test database
- E2E tests for critical user flows only — keep these minimal and stable
- Test behavior, not implementation details
- Don't mock the database — use a test database with transaction rollback or cleanup
- Tests must be deterministic — no dependence on external services, wall clock, or random state

### Performance
- No blocking/synchronous work in request handlers that takes >100ms — offload to background jobs
- Cache expensive computations/queries with appropriate TTLs
- Set connection pool sizes explicitly — don't rely on defaults
- Measure before optimizing. Don't add complexity for hypothetical performance gains

### Security
- Never log secrets, tokens, passwords, or PII
- Validate and sanitize all user input at system boundaries
- Use parameterized queries — never build SQL/commands from user input via string concatenation
- Apply rate limiting to public-facing endpoints
- Follow the principle of least privilege for service accounts and API keys
- Keep dependencies updated. Audit for known vulnerabilities regularly

## Conventions

### Naming
- Follow the language's idiomatic naming conventions consistently
- Be descriptive — clarity over brevity. `getUserByEmail` over `getUser` or `fn1`
- Database tables: plural, snake_case
- Booleans: prefix with `is`, `has`, `should`, `can`

### Git
- Branch format: `<type>/<ticket-id>-<short-description>` (e.g., `feat/PROJ-123-add-billing`)
- Commit messages: conventional commits (`feat:`, `fix:`, `chore:`, `refactor:`, `test:`, `docs:`)
- One logical change per PR. Keep PRs reviewable (<400 lines when possible)
- Squash merge to main
- Checkin without co-authered by claude comment

### Code Style
- Prefer immutable variables where the language supports it
- Use early returns to reduce nesting
- Keep functions short (~40 lines max). Extract helpers when longer
- Use async/await over callback chains
- Colocate types with the code that uses them. Only centralize truly shared types
- Delete dead code — don't comment it out

## What NOT To Do

### Code fixing
- Don't try proposing new solutions, unless you ran out of all possibilities and you are sure that it is the best solution
- Don't make too many code changes to fix issues, unless it is absolutely necessary

### Other
- Don't add debug logging to committed code — use the structured logger
- Don't catch all errors with a generic handler that hides bugs
- Don't use escape hatches to bypass the type system (e.g., `any`, unsafe casts, `# type: ignore`)
- Don't store business logic in UI components or route handler files
- Don't add dependencies without evaluating size, maintenance status, and security
- Don't write speculative code — no abstractions, feature flags, or config for things that aren't needed yet
- Don't duplicate logic — if the same rule exists in two places, extract it
- Don't hardcode environment-specific values — use configuration
