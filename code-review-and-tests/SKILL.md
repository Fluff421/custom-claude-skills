# Code Review + Write Tests Skill

## Purpose
Systematically review code diffs or functions for bugs, security vulnerabilities, style violations, and missing tests — then generate a full, repo-aware test suite covering happy paths, edge cases, and failure modes.

## When to Use This Skill
- Before submitting a pull request for human review
- When inheriting legacy code that lacks test coverage
- After writing a new function or module
- When a bug is found and you need regression tests
- For security audits of authentication, input handling, or data access code

## How It Works
Runs a structured multi-pass checklist on provided code, then generates pytest/jest/mocha test suites with proper fixtures, mocks, and assertions tailored to the detected language and framework.

## Instructions for Claude

### Code Review Pass (run in order)
1. **Correctness** — Does logic match stated intent? Off-by-one errors, wrong comparisons, flipped conditions?
2. **Security** — SQL injection, XSS, unvalidated inputs, hardcoded secrets, insecure deserialization, path traversal
3. **Performance** — N+1 queries, unnecessary loops, missing indexes, blocking I/O in async code
4. **Style** — PEP8 (Python), ESLint standard (JS), or repo's existing conventions
5. **Error Handling** — Are exceptions caught and logged? Errors propagated correctly?
6. **Test Coverage** — What is untested? What are the critical paths?

Output a structured report: CRITICAL → HIGH → MEDIUM → LOW → SUGGESTIONS

### Test Writing Pass
1. Detect language and test framework (pytest, unittest, jest, mocha, go test)
2. Identify all public functions/methods to test
3. For each function write tests for:
   - Happy path (expected inputs → expected outputs)
   - Boundary conditions (empty, null, zero, max values)
   - Error cases (invalid inputs, exceptions, timeouts)
4. Use proper fixtures and mocks for external dependencies (DB, API, filesystem)
5. Include docstrings explaining what each test verifies

## Examples

### Security fix
```python
# VULNERABLE - SQL injection
def get_user(username):
    return db.execute(f"SELECT * FROM users WHERE name = '{username}'")

# FIXED
def get_user(username):
    return db.execute("SELECT * FROM users WHERE name = ?", (username,))
