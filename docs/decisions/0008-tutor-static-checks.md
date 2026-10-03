# ADR 0008: The tutor reads code; it does not run it (yet)

**Status:** accepted (2026-10-03)

**Context.** Automated execution of learner code needs real isolation: CPU, memory, time
and output limits, no network, no secrets, no host data, no home control, no Docker socket.
A `subprocess` call dressed up as a sandbox would be worse than none.

**Decision.** Exercises are checked statically: the submission is parsed with `ast` and
checked for required/forbidden constructs, defined functions and calls, and the learner
pastes what their own run printed for an output comparison. Results carry
`method: "static check (code read, not executed)"` and the UI says so. Lesson examples are
curated and their outputs are verified by the test suite, so the tutor never shows an
unverified result. Progress is derived only from attempts. A real sandbox (e.g. a separate
container or `bwrap`/seccomp-based runner with hard limits) is a later, separately
validated piece; its interface is the same `check_submission` contract.

**Consequences.** Honest feedback today without unsafe execution; some mistakes (runtime
errors the AST cannot see) are only caught when the learner runs the code themselves.
