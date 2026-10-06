## General Engineering Standards

1. **Keep code easily testable.**

   * Prefer small, focused units with clear inputs and outputs.
   * Avoid tightly coupled code that is difficult to isolate in tests.

2. **Keep files modular and reusable.**

   * Each file should have a clear responsibility.
   * Prefer reusable components over duplicated implementations.

3. **Organize files into appropriate folders.**

   * Place files in the folder that best represents their responsibility.
   * Avoid unnecessary nesting and folder bloat.

4. **Write extensive tests.**

   * New functionality should include appropriate unit, integration, and/or end-to-end tests.
   * AI functionality should use evaluation datasets where appropriate.

5. **Keep documentation current.**

   * Update `README.md`, `ARCHITECTURE.md`, and other relevant documentation when the system changes.

6. **Use descriptive names.**

   * Prefer `tailor_resume_for_job` over `process`.
   * Avoid unexplained abbreviations.
   * Names should clearly communicate the purpose of files, classes, methods, functions, and variables.

7. **Document every file.**

   * Every source file should begin with a header containing:

     * A brief description of the file's purpose.
     * An index of its public methods/exports.
   * The exact header format for each language is defined in the applicable folder's `AGENTS.md`.

8. **Document every function and method.**

   * Every function/method should have a short description using the appropriate documentation format (docstring, YARD, JSDoc, etc.).

9. **Keep implementations simple.**

   * Choose the simplest solution that solves the current problem.
   * Do not introduce speculative abstractions or infrastructure for hypothetical future requirements.

10. **Ask for clarification when requirements are ambiguous.**

    * Do not make significant assumptions when the intended behavior is unclear.

11. **Use Git.**

    * All code and documentation changes should be tracked in Git.
    * Commit changes in logical, focused units.

12. **Keep hosting costs low.**

    * This is a portfolio project and should be designed to run inexpensively.
    * Prefer free-tier, low-cost, or self-hostable services where practical.
    * Avoid infrastructure that introduces significant recurring costs without a clear benefit.
    * Do not introduce managed services, distributed infrastructure, or additional infrastructure solely for hypothetical scale.
    * Architectural decisions should consider both technical quality and ongoing hosting cost.

---

## AI Data Privacy

User data, including IDs, credentials, financial information, and other sensitive or identifying information, must not be sent to LLM providers or Langfuse unless explicitly required.

When sensitive data must be sent to an LLM or observability system:

1. Mask or redact sensitive information before sending it.
2. Process the data using the LLM or observability system.
3. Restore the original values only within the application's trusted environment.

Prefer passing only the minimum information necessary for the task.

LLM prompts, tool responses, traces, and evaluation datasets should not contain unnecessary sensitive user information.

---

## Tools

Use **MCP** for the tool layer.

### Database Tools

Database access must be performed through purpose-specific tools.

* Do not allow the LLM to execute arbitrary SQL.
* Each database tool should be scoped to a specific table/domain.
* Sanitize and validate all arguments.
* Only return the fields the LLM actually needs.
* Avoid exposing unnecessary database fields.
* Format results so they are easy for the LLM to understand.
* The LLM should not need to provide internal database IDs when they can be resolved by the tool.
* Tools should resolve internal IDs using available context and human-readable identifiers where practical.

For example, instead of:

```text
query_database(sql)
```

prefer:

```text
find_invoices(customer_name, status)
```

The tool should handle the underlying database queries and ID resolution internally.

### Tool Definitions

Every tool description should clearly specify:

* **When to use the tool**
* **When not to use the tool**
* **Parameters and expected values**
* **One or two concise examples**

Tool descriptions should be concise enough to avoid unnecessarily increasing LLM context and token usage.

### Tool Errors

Tool errors should provide useful information to the LLM.

Errors should explain:

* What went wrong.
* Why it failed, when known.
* Whether the operation can be retried.
* What the LLM should do next, when appropriate.

Do not expose unnecessary internal implementation details.

---

# Authentication and Security

The application will be publicly accessible but is primarily a portfolio/resume project and is not expected to have real users.

Implement **one secure login**.

Do not build a complex multi-tenant authentication or authorization system unless it becomes necessary.

Despite the limited expected usage, all externally accessible functionality must still follow basic security practices:

* Secure authentication.
* Proper session handling.
* Input validation.
* Authorization checks.
* Secure handling of Xero credentials/tokens.
* No arbitrary SQL execution.
* No unrestricted LLM access to application mutations.
* Sensitive user data must not be unnecessarily sent to LLM providers or observability platforms.

---

# Tech Stack

Current preferred stack:

### Backend

* Python
* FastAPI
* PydanticAI

### Frontend

* Next.js
* TypeScript
* Easy/fast development is preferred.
* Streaming support is required.

### AI Observability

* Langfuse

### Integration

* Xero API
* MCP for the tool layer

### Hosting

The application should be designed for **low-cost hosting**.

The specific hosting architecture is intentionally not locked in yet. Prefer simple deployments and inexpensive infrastructure over Kubernetes or other complex infrastructure unless a concrete requirement justifies them.

The remaining infrastructure and supporting technologies are intentionally **not locked in yet**. Choose additional technologies based on actual requirements, simplicity, and hosting cost rather than adding infrastructure speculatively.
