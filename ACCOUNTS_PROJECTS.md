# Accounts and projects — CCA-Lab 0.15.0

## First startup

Copy `.env.example` to `.env`. Set `SECRET` to a random value of at least 32 characters (generate one with `python -c "import secrets; print(secrets.token_hex(32))"`). Set `CCA_LAB_ADMIN_USERNAME` and `CCA_LAB_ADMIN_PASSWORD` (12–256 characters). There is no built-in password. The API and worker must receive the same environment and data directory.

The first startup creates the initial site administrator and **Default project**. An existing current-schema workspace becomes that project's content; files and job snapshots remain in place. It is accessible only to the initial administrator until they add members. Fresh installations receive an empty Default project. Bootstrap credentials are only used when the account registry is empty; changing them later does not reset the account. Change passwords in the UI. After successful bootstrap, remove the bootstrap password from the deployment environment if desired.

Compose reads `.env` automatically. Direct Python launches must export it in both terminals, for example `set -a; source .env; set +a` (quote shell-sensitive values). Restart both API and worker when updating. Do not leave an older unauthenticated API running against the same data directory.

For remote use, serve through HTTPS and set `CCA_LAB_COOKIE_SECURE=true`. Keep `SECRET` stable between restarts and identical across API processes. Rotating it invalidates all sessions. Keep `.env` private and out of version control.

## Account workflow

Users can register with a unique, case-insensitive username (3–64 letters, digits, dots, underscores or hyphens) and a password. Set `CCA_LAB_ALLOW_REGISTRATION=false` to disable self-registration. Site administrators can still create accounts in **Users**, enable/disable accounts, reset passwords and grant/revoke site-administrator status. Users can change their own password and sign out from the sidebar.

Registration grants no existing project access. Any active user can create a project and becomes its administrator. Project administrators add other registered, active users by username in **Members**; no email invitation is sent. Select a project in the sidebar to change workspace. Project switches reload the page, closing open dialogs.

| Permission | Project admin | Regular user | View-only |
|---|---|---|---|
| View project content, logs, reports and downloads | Yes | Yes | Yes |
| Create/edit/delete connections, tasks, data, evaluations and predictions | Yes | Yes | No |
| Start, pause, resume or cancel jobs | Yes | Yes | No |
| Rename project; add/remove members; change project roles | Yes | No | No |

Site administration is a separate account-level permission. It does not automatically grant access to every project's content. Site administrators can reset other accounts' passwords, so treat this as a trusted operator role. The last active site administrator and the last active administrator of each project cannot be removed or disabled. Assign another administrator first. Accounts are deactivated rather than deleted, preserving membership/history. Project deletion is not provided.

## Enforcement and session behavior

Permissions are checked on the server for every API request, including direct download and chart URLs. UI controls reflect the selected role. Existing sessions lose project access immediately when membership is removed; an already-authorized in-flight response can finish. Removing access does not erase previously downloaded files or cancel already submitted jobs. Those jobs remain project resources.

Passwords use salted scrypt hashes. Random sessions are stored server-side as keyed hashes and expire after 12 hours. The cookie is HttpOnly and SameSite=Strict; HTTPS deployments enable Secure as described above. Mutating requests require an `X-CSRF-Token` matching the session, and cross-origin browser writes are rejected. Logout, password changes/resets and account administration revoke sessions. Login/registration attempts are limited per account name and peer IP (30 per 15 minutes). Shared proxy IPs share that limit.

API clients log in using `POST /api/auth/login` with JSON `username` and `password`, retain the returned cookie and CSRF token, then list `/api/projects`. Supply `X-Project-ID` for workspace routes and `X-CSRF-Token` for mutations. Browser download/image URLs use `?project_id=…` with the same session cookie. A project ID alone grants no access. `/api/health` without a project is public for container health checks; a scoped health request requires membership. API documentation remains public; actual API operations are protected.

## Storage, workers and operating limits

`CCA_LAB_DATA/accounts.sqlite` contains users, memberships and sessions. The Default project keeps its current database/files at the data root. New projects each have a separate database and files under `projects/<project-id>/`. Cross-project resource IDs cannot be resolved through another project's database. Back up the entire data directory consistently, including the account registry and every project directory; stop both services for a simple filesystem backup. Restore with the deployment SECRET, or rotate it deliberately to force fresh logins.

`python -m cca_lab.worker` runs a supervisor that discovers projects and starts one coordinator process per project. Each coordinator retains the endpoint-aware job scheduler and request concurrency. Different projects execute independently, so jobs aimed at the same physical LLM server from different projects can run concurrently. Capacity limits are per project, not global. Process and memory consumption grow with the number of projects; this release is intended for a single-server research team, not unrestricted public multi-tenant hosting. No per-user quotas, MFA, SSO or email password recovery are included.

Project editors can configure LLM destinations reachable by the host. Only environment-variable names explicitly listed in `CCA_LAB_ALLOWED_API_KEY_ENVS` may be selected for API keys; the default is `LLM_API_KEY`. Add comma-separated names if necessary. Never allow application secrets such as `SECRET` or bootstrap credentials. Allowlisted LLM credentials and reachable model services are shared operator-managed infrastructure: project isolation does not allocate separate infrastructure credentials. Limit registration/membership and host network access accordingly. API request logs include user/project IDs, not passwords or session tokens.
