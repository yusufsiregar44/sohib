# Stockbit authentication and session lifecycle

## Scope and evidence

The inspected research endpoints worked in an already signed-in Stockbit browser. A supported public API key issuance flow, token refresh contract, expiry policy and unattended login flow have NOT been verified. The existence of web-app endpoints does not establish a public API contract. Do not invent OAuth scopes, token URLs or cookie names.

Canonical service: https://stockbit.com/ . Treat user-supplied redirect links as navigation aids, never as destinations for submitting credentials. Verify the actual Stockbit login origin before entry.

## Credential boundary

The harness needs authenticated provider access; the language-model agent does not need the password, cookies or tokens. A provider-side session manager owns these secrets. Model tools accept research arguments only and receive normalized data or an authentication status.

- Store an optional login username/password in OS Keychain or a deployment secret manager, outside git, prompts, research memory and catalogue fixtures. Never collect credentials in chat.
- Keep browser state in a dedicated protected profile. Cookies/storage state and bearer tokens are credentials: encrypt persisted state, restrict file permissions and scope access to the session manager.
- If automated credential entry is implemented, retrieve credentials only inside the login worker, submit only to the verified service origin, and disable screenshots, DOM dumps and request logging around credential entry. It remains an unimplemented integration until the login flow is inspected.
- Prefer an initial user-assisted login in that dedicated profile. The worker can subsequently reuse the authorized session. Do not copy arbitrary cookies from unrelated browser profiles or send session state to model providers.
- Cookies and tokens stay on their original approved provider origins. Never forward Authorization headers or cookies across redirects; use an explicit origin allowlist discovered from the login flow.

## State machine

UNCONFIGURED → LOGIN_REQUIRED → AUTHENTICATING → READY → EXPIRED → LOGIN_REQUIRED.
AUTHENTICATING can enter USER_ACTION_REQUIRED for OTP, MFA, CAPTCHA or other interactive challenges. READY can enter FORBIDDEN for entitlement failures; reauthentication must not be used to bypass these.

- Login: verify origin, provision credentials/session, perform normal sign-in, then validate with one inexpensive authorized research read. Do not assume a page redirect alone proves authentication.
- Read requests: inject required authentication inside the adapter. Log endpoint templates and status, never headers, cookies, signed URLs or response bodies that may include secrets.
- Expiry: classify 401, login redirects and login HTML as authentication failures. Stop affected tasks and return AUTH_EXPIRED. Attempt refresh only once if a legitimate refresh flow has been discovered and tested; otherwise request user-assisted login.
- Challenges: pause only session-dependent work and return AUTH_CHALLENGE. User completes OTP/MFA or other required steps through the service. Never disable or bypass challenges.
- Concurrency: single-flight session renewal; all workers use a session generation identifier so stale sessions are not repeatedly reused. Use a separate session boundary per account.
- Revocation: disconnect stops queued provider calls, clears harness-owned session material and invokes provider logout/revocation only where verified. Rotate leaked credentials through the normal service flow.

## Secret-free observability

Track state, last successful validation, expiration time only if known, failure code and session generation. Redact password, OTP, Authorization, Cookie, Set-Cookie, access/refresh tokens and token-bearing query parameters before logging. Raw evidence capture uses an allowlist of public research fields. Test redaction on errors and traces as well as success paths.

## Still to verify before implementation

- Actual login steps, authentication origins, challenge behavior and supported session reuse.
- Whether each research endpoint requires cookies, authorization headers or both; CSRF handling where relevant.
- Expiry, legitimate refresh/logout behavior and entitlement differences.
- Service rules and account permission for automated access, observed rate limits and unattended use.

No credentials were requested, stored or extracted to create this document. This is a lifecycle design, not a claim that automated Stockbit login is implemented.
