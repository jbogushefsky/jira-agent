# AI - Build Story — Story Generation & Evaluation Rubric

When rewriting a Jira ticket's description, produce a story that could be implemented by an engineer
with minimal clarification. The new description must include the following sections, in order:

## Output format (Jira compatibility)
The output is sent verbatim to Jira as the new description field, so it must be plain Markdown that
Jira's renderer supports:
- Use only `##`/`###` headings, `-` bullet lists, `1.` numbered lists, `**bold**`/`*italic*`, and
  fenced code blocks.
- Do not use HTML tags, Markdown tables, footnotes, or embedded images — Jira does not reliably
  render them.
- Do not wrap the response in a code fence, and do not emit JSON — return the description as plain
  text.

## Project reference line (routing — required for PROJ tickets)
If this ticket's key starts with `PROJ-`, the **very first line** of the new description must be
exactly:

Project: dice-roll

This line is how this system resolves which local repository an "In Dev" flow should target
(`app/utils/ticket_parsing.extract_project_reference` looks for a `Project: <name>` line). Since AI
Resolve replaces the whole description, omitting this line would silently break that routing for this
ticket. Tickets whose key does not start with `PROJ-` must not have this line added. Everything below
this line follows the normal section structure, starting with the User Story below.

## 1. User Story
Use the standard format: "As a <user/persona>, I want <capability> so that <business value>."
Identify the primary persona if one is not explicitly provided.

## 2. Business Context
Briefly explain:
- Why this work is needed
- The business problem being solved
- Expected customer or business value
- Any dependencies on other systems

## 3. Functional Requirements
Write clear, testable requirements. Each requirement should:
- Describe one behavior
- Use active language ("The system shall ...")
- Avoid implementation details unless explicitly requested
- Be independently verifiable
- Include normal and edge-case behavior

Example: "The system shall reject duplicate requests using the idempotency key."

## 4. Non-Functional Requirements
Include applicable requirements for: performance, availability, reliability, scalability, security,
privacy, accessibility, observability, compliance, localization, and browser/device support.

Example: "API response time shall be under 300 ms at the 95th percentile."

## 5. Acceptance Criteria
Write thorough acceptance criteria using Given / When / Then, covering: happy path, validation
failures, error handling, permission scenarios, empty states, duplicate requests, retry behavior,
boundary conditions, invalid inputs, audit requirements, logging requirements, notifications, and
state transitions. Each acceptance criterion should verify exactly one behavior.

Example:
Given a valid request
When the user submits the form
Then the record is created
And an audit event is written.

## 6. Edge Cases
Explicitly identify edge cases (e.g. duplicate submissions, missing required fields, invalid data,
expired sessions, network failures, partial failures, timeouts, concurrent updates, large datasets,
empty results, unsupported values).

## 7. Business Rules
List explicit business rules (e.g. "Users may edit only their own records.").

## 8. Out of Scope
Clearly identify what is NOT included.

## 9. Technical Notes
If technical assumptions are provided or discoverable from the codebase, summarize: APIs involved,
events published, database changes, feature flags, backward compatibility, and migration
considerations.

## 10. Definition of Done
State that the story is complete only when: all acceptance criteria pass, unit tests are added,
integration tests pass, observability is implemented, security requirements are satisfied,
documentation is updated, feature flag behavior is verified, and no known critical defects remain.

## Acceptance Criteria Quality Rules
Every acceptance criterion must be specific, measurable, testable, independent, unambiguous, focused
on observable behavior, and free of implementation assumptions unless required. Avoid vague language
("appropriately", "correctly", "efficiently", "quickly", "user-friendly", "as needed", "where
possible") — use measurable expectations instead.

## Requirements Quality Checklist
Before finishing, verify the story answers: who is the user; what problem is being solved; why it's
valuable; what happens on success, on validation failure, and on downstream failure; what happens on
duplicate requests; what permissions are required; what should be logged and audited; what metrics
and events are involved; what errors are shown; what happens if data already exists or doesn't exist;
the performance and security expectations; and what is explicitly out of scope. If any answer is
missing, identify the gap rather than making assumptions.

## Final Story Review
Evaluate the story against these quality gates: clear business value; requirements are testable;
acceptance criteria cover the happy path, failures, and edge cases; security, performance, logging,
observability, and audit requirements are addressed; out of scope is identified; no ambiguous
wording; ready for sprint planning. If any quality gate fails, explain why and what information is
needed, in a section titled **AI RECOMMENDATIONS** at the end of the description.

Replace the ticket's entire existing description with this new content (including the `Project:`
line at the top, if applicable) — do not append to or preserve the old description.
