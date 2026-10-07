# Interviewer login

Python files here use the module docstring in `backend/AGENTS.md`. Every function and method has a one-line docstring.

One shared username and password protect the API. The password is stored as an argon2 hash. Do not log the password, the hash, or the session secret.

## Files

- `passwords.py` — hash and check the interviewer password
- `hash_password.py` — print a hash for `.env` during setup
- `routes.py` — login, logout, and session lookup
