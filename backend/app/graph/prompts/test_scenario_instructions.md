## Traceability identifiers

Assign every test scenario a unique identifier so it can later be referenced from automated test
code (e.g. as a tag or comment linking a test back to the scenario it implements):
- Use the convention `{jira-ticket-number}-AC-##-TC-##`, where `{jira-ticket-number}` is this
  ticket's exact Jira key given above (e.g. `PROJ-42`).
- `AC-##`: the sequential, two-digit, zero-padded index of the acceptance criterion this scenario
  covers, in the order the acceptance criteria were listed above.
- `TC-##`: the sequential, two-digit, zero-padded scenario number **within that acceptance
  criterion** — restart at `01` for every new acceptance criterion, don't count across the whole
  ticket.
- Example for ticket `PROJ-42`: the first acceptance criterion's two scenarios are
  `PROJ-42-AC-01-TC-01` and `PROJ-42-AC-01-TC-02`; the second acceptance criterion's first scenario
  is `PROJ-42-AC-02-TC-01`.
- Never reuse a full identifier within the same ticket.
- The identifier is a plain label, not part of the scenario title or body text.
