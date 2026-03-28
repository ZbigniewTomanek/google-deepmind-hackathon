# Plan: Auth0 Integration

## Overview

Integrate Auth0 as a first-class authentication provider for both the MCP server
(FastMCP) and the FastAPI ingestion API. FastMCP 3.1.1 already includes
`Auth0Provider` (`OIDCProxy` subclass) — we wire it with Auth0 tenant config.
The ingestion API gets JWT validation against Auth0's JWKS endpoint. Auth0 user
identities (`sub` claim) auto-provision into NeoCortex's permission system on
first access.

## Execution Protocol

To execute this plan, follow this loop for each stage:

1. **Read the progress tracker** below and find the first stage that is not DONE
2. **Read the stage details** — understand the goal, dependencies, and steps
3. **Clarify ambiguities** — if anything is unclear or multiple approaches exist,
   ask the user before implementing. Do not guess.
4. **Implement** — execute the steps described in the stage
5. **Validate** — run the verification checks listed in the stage.
   If validation fails, fix the issue before proceeding. Do not skip verification.
6. **Update this plan** — mark the stage as DONE in the progress tracker,
   add brief notes about what was done and any deviations from the original steps
7. **Commit** — create an atomic commit with the message specified in the stage.
   Include all changed files (code, config, docs, and this plan file).

Repeat until all stages are DONE or a stage is BLOCKED.

**If a stage cannot be completed**: mark it BLOCKED in the tracker with a note
explaining why, and stop. Do not proceed to subsequent stages.

**If assumptions are wrong**: stop, document the issue in the Issues section below,
revise affected stages, and get user confirmation before continuing.

## Context for Resuming

Auth0 tenant is fully configured. All credentials are in `.env.auth0` (gitignored)
and `auth0.md` (gitignored). `.gitignore` was already updated to exclude both files.

**Auth0 tenant details** (for verification commands in later stages):
- **Domain**: `dev-vexy1xpbs6te6c53.us.auth0.com`
- **Audience**: `https://neocortex.local/api`
- **OIDC discovery**: `https://dev-vexy1xpbs6te6c53.us.auth0.com/.well-known/openid-configuration` (verified working)
- **MCP Server app** (Regular Web App): Client ID `76QXPJsPuHQYUx0pzhk1PvdMk7TtaZwO`, secret in `.env.auth0`
- **M2M app**: Client ID `cwBCgvnx4lPQFqzzXVKAW2KMgfqLtHjd`, secret in `.env.auth0`
- **M2M token test**: Already verified — token includes `sub: "cwBCgvnx4lPQFqzzXVKAW2KMgfqLtHjd@clients"`, scopes `memory:read memory:write`
- **Auth method**: MCP Server app uses `Client Secret (Post)`
- **Callback URLs**: `http://localhost:8000/auth/callback` configured
- **API permissions**: `memory:read`, `memory:write`, `admin:manage` — RBAC enabled, permissions added to access tokens
- **Roles created**: `neocortex-admin`, `neocortex-agent`, `neocortex-reader`

**Files already changed** (not yet committed):
- `.gitignore` — added `.env.auth0` and `auth0.md`
- `.env.auth0` — created with all credentials
- `auth0.md` — user's notes with M2M test results (gitignored)

**Next step**: Stage 2 — add Auth0 fields to `MCPSettings` (the `.gitignore` part of Stage 2 is already done).

## Progress Tracker

| # | Stage | Status | Notes | Commit |
|---|-------|--------|-------|--------|
| 1 | Auth0 Account & Tenant Setup | DONE | Tenant `dev-vexy1xpbs6te6c53.us.auth0.com`, API + 2 apps + 3 roles + test user created. `.env.auth0` written. OIDC discovery verified. M2M token tested. | — |
| 2 | Add Auth0 Settings to MCPSettings | DONE | Added `auth0` to auth_mode literal, added 6 Auth0 config fields to MCPSettings | `feat(auth): add Auth0 configuration fields to MCPSettings` |
| 3 | Create Auth0 Auth Provider for MCP Server | PENDING | | |
| 4 | Update Ingestion API for Auth0 JWT Validation | PENDING | | |
| 5 | Auto-Provision Auth0 Identities into Permissions | PENDING | | |
| 6 | End-to-End Validation | PENDING | | |

Statuses: `PENDING` → `IN_PROGRESS` → `DONE` | `BLOCKED`

---

## Stage 1: Auth0 Account & Tenant Setup (Manual)

**Goal**: Create an Auth0 account, tenant, API, and applications via the Auth0 dashboard.
**Dependencies**: None

This stage is entirely manual — the user follows these steps in the Auth0 web UI.
No code changes.

### Step 1.1: Create Auth0 Account & Tenant

1. Go to https://auth0.com/signup
2. Sign up (GitHub/Google/email)
3. Auth0 creates a default tenant (e.g., `dev-abc123`). Note the **tenant domain**:
   - Format: `{tenant}.{region}.auth0.com` (e.g., `dev-abc123.eu.auth0.com`)
   - Find it at: **Settings → General → Domain**

### Step 1.2: Register the NeoCortex API (Resource Server)

1. Navigate to: **Applications → APIs → + Create API**
2. Fill in:
   - **Name**: `NeoCortex Memory API`
   - **Identifier (Audience)**: `https://neocortex.local/api` (any URI, doesn't need to be reachable)
   - **Signing Algorithm**: `RS256`
3. Click **Create**
4. Go to the **Permissions** tab and add these scopes:
   - `memory:read` — Read memories (recall, discover)
   - `memory:write` — Write memories (remember, ingest)
   - `admin:manage` — Admin operations (permissions, graphs)
5. Go to the **Settings** tab:
   - Enable **"Enable RBAC"**
   - Enable **"Add Permissions in the Access Token"** (this puts permissions in the JWT)
   - Set **Access Token Lifetime** to `86400` (24 hours) for development
6. Note down the **Identifier** — this is the `audience` value

### Step 1.3: Create the MCP Server Application (Regular Web App)

This application handles the interactive OAuth flow for MCP clients (Claude Desktop, TUI, etc.).

1. Navigate to: **Applications → Applications → + Create Application**
2. Fill in:
   - **Name**: `NeoCortex MCP Server`
   - **Type**: **Regular Web Application**
3. Click **Create**
4. Go to **Settings** tab:
   - Note: **Client ID** and **Client Secret**
   - **Allowed Callback URLs**: `http://localhost:8000/auth/callback`
   - **Allowed Logout URLs**: `http://localhost:8000`
   - **Allowed Web Origins**: `http://localhost:8000`
5. Click **Save Changes**

### Step 1.4: Create a Machine-to-Machine Application (for agents/ingestion)

This application lets agents and the ingestion API authenticate without user interaction.

1. Navigate to: **Applications → Applications → + Create Application**
2. Fill in:
   - **Name**: `NeoCortex Agent M2M`
   - **Type**: **Machine to Machine**
3. Click **Create**
4. In the authorization prompt:
   - Select API: **NeoCortex Memory API**
   - Select scopes: `memory:read`, `memory:write`
5. Note: **Client ID** and **Client Secret** for this M2M app

### Step 1.5: Create Auth0 Roles

1. Navigate to: **User Management → Roles → + Create Role**
2. Create these roles:
   - **`neocortex-admin`**: Description: "Full admin access to NeoCortex"
     - Assign permissions: `memory:read`, `memory:write`, `admin:manage`
   - **`neocortex-agent`**: Description: "Standard agent with read/write"
     - Assign permissions: `memory:read`, `memory:write`
   - **`neocortex-reader`**: Description: "Read-only agent"
     - Assign permissions: `memory:read`

### Step 1.6: Create a Test User

1. Navigate to: **User Management → Users → + Create User**
2. Create a test user with email/password
3. Assign the `neocortex-admin` role to this user
4. Note the user's **user_id** (e.g., `auth0|abc123...`)

### Step 1.7: Collect Configuration Values

Create a `.env.auth0` file in the project root (gitignored) with:

```bash
# Auth0 tenant
NEOCORTEX_AUTH0_DOMAIN=dev-XXXXX.eu.auth0.com
NEOCORTEX_AUTH0_AUDIENCE=https://neocortex.local/api

# MCP Server app (Regular Web Application)
NEOCORTEX_AUTH0_CLIENT_ID=<from Step 1.3>
NEOCORTEX_AUTH0_CLIENT_SECRET=<from Step 1.3>

# M2M app (for agents/ingestion)
NEOCORTEX_AUTH0_M2M_CLIENT_ID=<from Step 1.4>
NEOCORTEX_AUTH0_M2M_CLIENT_SECRET=<from Step 1.4>

# Auth mode
NEOCORTEX_AUTH_MODE=auth0
```

**Verification**:
- [ ] Auth0 dashboard shows the API with 3 permissions defined
- [ ] Dashboard shows 2 applications (Regular Web + M2M)
- [ ] Dashboard shows 3 roles with correct permission assignments
- [ ] `.env.auth0` file created with all values filled in
- [ ] OIDC discovery works: `curl https://{domain}/.well-known/openid-configuration` returns JSON

**Commit**: No commit — manual setup only.

---

## Stage 2: Add Auth0 Settings to MCPSettings

**Goal**: Extend `MCPSettings` with Auth0 configuration fields and add `"auth0"` to the `auth_mode` literal.
**Dependencies**: Stage 1 (need to know what config values are required)

**Steps**:

1. Edit `src/neocortex/mcp_settings.py`:
   - Change `auth_mode` type from `Literal["none", "dev_token", "google_oauth"]` to
     `Literal["none", "dev_token", "google_oauth", "auth0"]`
   - Add Auth0 config fields after the Google OAuth block:
     ```python
     # Auth0 (used when auth_mode = "auth0")
     auth0_domain: str = ""        # e.g., "dev-xxx.eu.auth0.com"
     auth0_client_id: str = ""     # Regular Web App client ID
     auth0_client_secret: str = "" # Regular Web App client secret
     auth0_audience: str = ""      # API identifier (audience)
     auth0_m2m_client_id: str = ""     # M2M app client ID (for ingestion API)
     auth0_m2m_client_secret: str = "" # M2M app client secret
     ```

2. `.gitignore` — already updated with `.env.auth0` and `auth0.md` (done in Stage 1).

**Key files to read before implementing**:
- `src/neocortex/mcp_settings.py` — the settings class to modify (see `auth_mode` literal and Google OAuth fields for the pattern to follow)

**Verification**:
- [ ] `uv run python -c "from neocortex.mcp_settings import MCPSettings; s = MCPSettings(auth_mode='auth0', auth0_domain='test.auth0.com', auth0_audience='https://test'); print(s.auth_mode, s.auth0_domain)"` prints `auth0 test.auth0.com`
- [ ] Existing tests still pass: `uv run pytest tests/ -x -q`

**Commit**: `feat(auth): add Auth0 configuration fields to MCPSettings`

---

## Stage 3: Create Auth0 Auth Provider for MCP Server

**Goal**: Wire FastMCP's built-in `Auth0Provider` into the MCP server auth factory.
**Dependencies**: Stage 2

**Key files to read before implementing**:
- `src/neocortex/auth/__init__.py` — auth factory with `create_auth()`, add `"auth0"` branch here
- `src/neocortex/auth/google.py` — existing Google OAuth provider, follow this pattern
- `src/neocortex/auth/dependencies.py` — `get_agent_id_from_context()`, add auth0 branch
- `.venv/lib/python3.13/site-packages/fastmcp/server/auth/providers/auth0.py` — the built-in Auth0Provider class (extends OIDCProxy). Constructor takes: `config_url`, `client_id`, `client_secret`, `audience`, `base_url`, `required_scopes`, etc.

**Steps**:

1. Create `src/neocortex/auth/auth0.py`:
   ```python
   """Auth0 OAuth provider for NeoCortex MCP server."""

   from fastmcp.server.auth import AuthProvider
   from fastmcp.server.auth.providers.auth0 import Auth0Provider

   from neocortex.mcp_settings import MCPSettings


   def create_auth0_auth(settings: MCPSettings) -> AuthProvider:
       """Create an Auth0 provider for FastMCP.

       Uses FastMCP's built-in Auth0Provider which handles:
       - OIDC discovery from Auth0's well-known config
       - JWT token verification via Auth0's JWKS endpoint
       - OAuth authorization flow proxy
       """
       if not settings.auth0_domain:
           raise ValueError("NEOCORTEX_AUTH0_DOMAIN is required for auth0 mode")
       if not settings.auth0_client_id:
           raise ValueError("NEOCORTEX_AUTH0_CLIENT_ID is required for auth0 mode")
       if not settings.auth0_client_secret:
           raise ValueError("NEOCORTEX_AUTH0_CLIENT_SECRET is required for auth0 mode")
       if not settings.auth0_audience:
           raise ValueError("NEOCORTEX_AUTH0_AUDIENCE is required for auth0 mode")

       config_url = f"https://{settings.auth0_domain}/.well-known/openid-configuration"

       return Auth0Provider(
           config_url=config_url,
           client_id=settings.auth0_client_id,
           client_secret=settings.auth0_client_secret,
           audience=settings.auth0_audience,
           base_url=settings.oauth_base_url,
           required_scopes=["openid", "profile", "email"],
       )
   ```

2. Edit `src/neocortex/auth/__init__.py` — add `"auth0"` branch to `create_auth()`:
   ```python
   if settings.auth_mode == "auth0":
       from neocortex.auth.auth0 import create_auth0_auth
       return create_auth0_auth(settings)
   ```

3. Update the error message in `create_auth()` to include `'auth0'`.

4. Edit `src/neocortex/auth/dependencies.py` — `get_agent_id_from_context()`:
   - The existing code already handles the generic token path at the bottom
     (`token.claims.get("sub")`), so Auth0 tokens will work automatically.
   - However, add an explicit `auth0` branch for clarity and to handle
     Auth0-specific `sub` format (`auth0|xxx` or `google-oauth2|xxx`):
   ```python
   if settings.auth_mode == "auth0":
       token = get_access_token()
       if token is None:
           return "anonymous"
       sub = token.claims.get("sub")
       if sub:
           # Auth0 sub format: "auth0|abc123" or "google-oauth2|123"
           # Use the full sub as agent_id for uniqueness
           return str(sub)
       return "anonymous"
   ```

**Verification**:
- [ ] `uv run python -c "from neocortex.auth import create_auth; from neocortex.mcp_settings import MCPSettings; print('import ok')"` succeeds
- [ ] Existing tests pass: `uv run pytest tests/ -x -q`
- [ ] (After Stage 1 is done) `NEOCORTEX_AUTH_MODE=auth0 NEOCORTEX_AUTH0_DOMAIN=<domain> NEOCORTEX_AUTH0_CLIENT_ID=<id> NEOCORTEX_AUTH0_CLIENT_SECRET=<secret> NEOCORTEX_AUTH0_AUDIENCE=<aud> uv run python -c "from neocortex.auth import create_auth; from neocortex.mcp_settings import MCPSettings; a = create_auth(MCPSettings()); print(type(a))"` prints `Auth0Provider`

**Commit**: `feat(auth): add Auth0 provider for MCP server using FastMCP Auth0Provider`

---

## Stage 4: Update Ingestion API for Auth0 JWT Validation

**Goal**: Extend the FastAPI ingestion API's `get_agent_id()` dependency to validate Auth0 JWTs alongside the existing dev-token lookup.
**Dependencies**: Stage 2

**Key files to read before implementing**:
- `src/neocortex/ingestion/auth.py` — current `get_agent_id()` dependency, extend with Auth0 JWT path
- `src/neocortex/ingestion/app.py` — FastAPI app lifespan, add Auth0JWTVerifier init here
- `src/neocortex/ingestion/routes.py` — ingestion routes that use `get_agent_id` dependency (no changes needed here, just for context)

**Steps**:

1. Add `PyJWT` and `cryptography` dependencies (for RS256 JWT verification):
   ```bash
   uv add PyJWT cryptography
   ```
   (Note: `PyJWT` may already be a transitive dependency of FastMCP — check first)

2. Create `src/neocortex/ingestion/auth0_jwt.py` — Auth0 JWT verifier for FastAPI:
   ```python
   """Auth0 JWT verification for the FastAPI ingestion API."""

   import jwt
   from jwt import PyJWKClient
   from functools import lru_cache

   from neocortex.mcp_settings import MCPSettings


   class Auth0JWTVerifier:
       """Verifies Auth0 access tokens (RS256 JWTs) for the ingestion API."""

       def __init__(self, domain: str, audience: str) -> None:
           self._issuer = f"https://{domain}/"
           self._audience = audience
           self._jwks_uri = f"https://{domain}/.well-known/jwks.json"
           self._jwks_client = PyJWKClient(self._jwks_uri, cache_keys=True)

       def verify(self, token: str) -> dict:
           """Verify and decode an Auth0 JWT.

           Returns the decoded claims dict.
           Raises jwt.PyJWTError on any validation failure.
           """
           signing_key = self._jwks_client.get_signing_key_from_jwt(token)
           return jwt.decode(
               token,
               signing_key.key,
               algorithms=["RS256"],
               audience=self._audience,
               issuer=self._issuer,
           )
   ```

3. Edit `src/neocortex/ingestion/auth.py` — extend `get_agent_id()`:
   ```python
   async def get_agent_id(
       request: Request,
       credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)] = None,
   ) -> str:
       settings: MCPSettings = request.app.state.settings

       if settings.auth_mode == "none":
           return "anonymous"

       if credentials is None:
           raise HTTPException(status_code=401, detail="Missing authorization token")

       # Auth0 mode: validate JWT
       if settings.auth_mode == "auth0":
           verifier = request.app.state.auth0_verifier
           try:
               claims = verifier.verify(credentials.credentials)
               sub = claims.get("sub")
               if not sub:
                   raise HTTPException(status_code=401, detail="Token missing sub claim")
               return str(sub)
           except Exception as exc:
               raise HTTPException(status_code=401, detail=f"Invalid token: {exc}") from exc

       # Dev-token mode: static lookup
       token_map: dict[str, str] = request.app.state.token_map
       agent_id = token_map.get(credentials.credentials)
       if agent_id is None:
           raise HTTPException(status_code=401, detail="Invalid token")
       return agent_id
   ```

4. Edit `src/neocortex/ingestion/app.py` — initialize the Auth0 JWT verifier in lifespan:
   ```python
   # In the lifespan function, after settings are loaded:
   if settings.auth_mode == "auth0":
       from neocortex.ingestion.auth0_jwt import Auth0JWTVerifier
       app.state.auth0_verifier = Auth0JWTVerifier(
           domain=settings.auth0_domain,
           audience=settings.auth0_audience,
       )
   ```

5. Add permission scope checking for Auth0 tokens in ingestion routes.
   In `src/neocortex/ingestion/auth.py`, add a helper:
   ```python
   def get_auth0_permissions(request: Request, credentials: HTTPAuthorizationCredentials) -> list[str]:
       """Extract Auth0 permissions from the JWT. Returns empty list for non-auth0 modes."""
       settings: MCPSettings = request.app.state.settings
       if settings.auth_mode != "auth0":
           return []
       verifier = request.app.state.auth0_verifier
       try:
           claims = verifier.verify(credentials.credentials)
           return claims.get("permissions", [])
       except Exception:
           return []
   ```

**Verification**:
- [ ] `uv run python -c "from neocortex.ingestion.auth0_jwt import Auth0JWTVerifier; print('import ok')"` succeeds
- [ ] Existing tests pass: `uv run pytest tests/ -x -q`
- [ ] (Manual, after Stage 1) Get M2M token from Auth0:
  ```bash
  curl --request POST \
    --url https://{domain}/oauth/token \
    --header 'content-type: application/json' \
    --data '{"client_id":"<m2m_client_id>","client_secret":"<m2m_secret>","audience":"<audience>","grant_type":"client_credentials"}'
  ```
  Then use it:
  ```bash
  curl -H "Authorization: Bearer <token>" http://localhost:8001/ingest/text \
    -H "Content-Type: application/json" \
    -d '{"text": "test memory"}'
  ```
  Should return 200 with a valid response.

**Commit**: `feat(ingestion): add Auth0 JWT validation for ingestion API`

---

## Stage 5: Auto-Provision Auth0 Identities into Permissions

**Goal**: When an Auth0-authenticated user/agent accesses NeoCortex for the first time, auto-register them in `agent_registry` and grant default permissions based on their Auth0 roles/permissions.
**Dependencies**: Stage 3, Stage 4

**Key files to read before implementing**:
- `src/neocortex/permissions/protocol.py` — `PermissionChecker` protocol (especially `list_agents()`, `set_admin()`)
- `src/neocortex/auth/dependencies.py` — where to add `ensure_provisioned()` helper
- `src/neocortex/tools/remember.py` — MCP tool pattern, add `ensure_provisioned()` call after `get_agent_id_from_context()`
- `src/neocortex/tools/recall.py` — same pattern
- `src/neocortex/tools/discover.py` — same pattern
- `src/neocortex/ingestion/auth.py` — add provisioning call in auth0 branch of `get_agent_id()`

**Steps**:

1. Create `src/neocortex/auth/provisioning.py`:
   ```python
   """Auto-provisioning of Auth0 identities into NeoCortex permission system."""

   from loguru import logger

   from neocortex.permissions.protocol import PermissionChecker


   async def ensure_agent_provisioned(
       permissions: PermissionChecker,
       agent_id: str,
       auth0_permissions: list[str] | None = None,
       bootstrap_admin_id: str = "admin",
   ) -> None:
       """Ensure an Auth0 user is registered and has appropriate permissions.

       Called on first access. Maps Auth0 permissions to NeoCortex roles:
       - "admin:manage" in Auth0 permissions → is_admin in NeoCortex
       - "memory:write" → write access to personal graph (automatic via GraphRouter)
       - "memory:read" → read access (automatic for personal, explicit for shared)

       Personal graph creation is handled by GraphRouter.route_store() on first write,
       so no explicit provisioning needed there.
       """
       # Check if agent already exists in registry
       agents = await permissions.list_agents()
       existing_ids = {a.agent_id for a in agents}

       if agent_id in existing_ids:
           return  # Already provisioned

       logger.info("auto_provisioning_agent", agent_id=agent_id)

       # Register agent — promote to admin if they have admin:manage permission
       is_admin = auth0_permissions is not None and "admin:manage" in auth0_permissions
       if is_admin:
           await permissions.set_admin(agent_id, is_admin=True)
           logger.info("agent_promoted_to_admin", agent_id=agent_id)
       else:
           # Ensure agent exists in registry (set_admin upserts)
           await permissions.set_admin(agent_id, is_admin=False)
   ```

2. Wire auto-provisioning into the MCP server tools.
   Edit `src/neocortex/auth/dependencies.py` — add a provisioning call after
   extracting the agent_id. Since tools already access `ctx.lifespan_context`,
   create a helper that tools can call:
   ```python
   async def ensure_provisioned(ctx: Context, agent_id: str) -> None:
       """Auto-provision agent on first access (Auth0 mode only)."""
       settings = ctx.lifespan_context.get("settings")
       if not isinstance(settings, MCPSettings) or settings.auth_mode != "auth0":
           return
       permissions = ctx.lifespan_context.get("permissions")
       if permissions is None:
           return
       token = get_access_token()
       auth0_perms = token.claims.get("permissions", []) if token else None
       await ensure_agent_provisioned(
           permissions=permissions,
           agent_id=agent_id,
           auth0_permissions=auth0_perms,
           bootstrap_admin_id=settings.bootstrap_admin_id,
       )
   ```

3. Call `ensure_provisioned()` in each MCP tool (`remember.py`, `recall.py`, `discover.py`)
   right after `agent_id = get_agent_id_from_context(ctx)`:
   ```python
   await ensure_provisioned(ctx, agent_id)
   ```

4. Wire auto-provisioning into the ingestion API.
   Edit `src/neocortex/ingestion/auth.py` — after resolving agent_id in auth0 mode,
   call the provisioning function:
   ```python
   # After verifying the JWT and extracting sub:
   if settings.auth_mode == "auth0":
       from neocortex.auth.provisioning import ensure_agent_provisioned
       permissions = request.app.state.permissions
       auth0_perms = claims.get("permissions", [])
       await ensure_agent_provisioned(
           permissions=permissions,
           agent_id=agent_id,
           auth0_permissions=auth0_perms,
           bootstrap_admin_id=settings.bootstrap_admin_id,
       )
   ```

**Verification**:
- [ ] `uv run python -c "from neocortex.auth.provisioning import ensure_agent_provisioned; print('import ok')"` succeeds
- [ ] Existing tests pass: `uv run pytest tests/ -x -q`
- [ ] (Manual) First call with Auth0 token creates agent in registry:
  after calling `remember` or `/ingest/text`, check `agent_registry` for the new agent_id

**Commit**: `feat(auth): auto-provision Auth0 identities into NeoCortex permission system`

---

## Stage 6: End-to-End Validation

**Goal**: Verify the complete Auth0 flow works for both MCP and ingestion.
**Dependencies**: All previous stages

**Steps**:

1. Start services with Auth0 config:
   ```bash
   source .env.auth0
   export NEOCORTEX_AUTH_MODE=auth0
   export NEOCORTEX_MOCK_DB=true  # or false with docker
   ./scripts/launch.sh
   ```

2. Test M2M token acquisition:
   ```bash
   # Get an M2M access token from Auth0
   TOKEN=$(curl -s --request POST \
     --url "https://${NEOCORTEX_AUTH0_DOMAIN}/oauth/token" \
     --header 'content-type: application/json' \
     --data "{
       \"client_id\": \"${NEOCORTEX_AUTH0_M2M_CLIENT_ID}\",
       \"client_secret\": \"${NEOCORTEX_AUTH0_M2M_CLIENT_SECRET}\",
       \"audience\": \"${NEOCORTEX_AUTH0_AUDIENCE}\",
       \"grant_type\": \"client_credentials\"
     }" | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
   echo "Token: ${TOKEN:0:20}..."
   ```

3. Test ingestion API with Auth0 token:
   ```bash
   curl -s -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     http://localhost:8001/ingest/text \
     -d '{"text": "Auth0 integration test memory"}' | python -m json.tool
   ```

4. Test MCP server OIDC discovery:
   ```bash
   curl -s http://localhost:8000/.well-known/openid-configuration | python -m json.tool
   ```

5. Verify dev_token mode still works:
   ```bash
   NEOCORTEX_AUTH_MODE=dev_token NEOCORTEX_MOCK_DB=true uv run python -c "
   from neocortex.server import create_server
   from neocortex.mcp_settings import MCPSettings
   s = MCPSettings()
   srv = create_server(s)
   print('dev_token mode OK')
   "
   ```

6. Write a brief integration test in `tests/test_auth0_config.py`:
   - Test that MCPSettings accepts `auth_mode="auth0"` with valid fields
   - Test that `create_auth()` returns `Auth0Provider` when configured
     (mock the OIDC discovery HTTP call)
   - Test that `Auth0JWTVerifier` raises on invalid tokens
   - Test that `ensure_agent_provisioned` registers a new agent

**Verification**:
- [ ] M2M token request returns a valid JWT
- [ ] Ingestion API accepts the M2M token and returns 200
- [ ] MCP server serves OIDC discovery metadata
- [ ] dev_token and none modes still work
- [ ] All tests pass: `uv run pytest tests/ -x -q`

**Commit**: `test(auth): add Auth0 integration validation tests`

---

## Overall Verification

After all stages:
1. `uv run pytest tests/ -v` — all tests pass
2. `NEOCORTEX_AUTH_MODE=none NEOCORTEX_MOCK_DB=true uv run python -m neocortex` — still works
3. `NEOCORTEX_AUTH_MODE=dev_token NEOCORTEX_MOCK_DB=true uv run python -m neocortex` — still works
4. Auth0 end-to-end flow with M2M tokens works for ingestion
5. Auth0 OIDC discovery served by MCP server

## Issues

[Document any problems discovered during execution]

## Decisions

### Decision: Auth0 sub as agent_id
- **Options**: A) Use full Auth0 `sub` claim (e.g., `auth0|abc123`) B) Hash/normalize it C) Use email claim
- **Chosen**: A — Use full `sub` claim
- **Rationale**: The `sub` is guaranteed unique by Auth0. Using it directly is simplest and
  most traceable. The `|` character is safe in PostgreSQL text columns and schema naming
  can sanitize it where needed. Email may not always be present (M2M tokens have no email).

### Decision: Permission mapping strategy
- **Options**: A) Map Auth0 roles 1:1 to NeoCortex roles B) Map Auth0 permissions to graph-level access C) Auto-provision minimal access, let admin grant more
- **Chosen**: C — Auto-provision with admin escalation from Auth0 permissions
- **Rationale**: NeoCortex's permission model (per-schema read/write) is more granular than
  Auth0 roles. Auth0 roles gate coarse access (admin vs agent vs reader). Fine-grained
  schema permissions are managed via NeoCortex admin API. Auth0 `admin:manage` permission
  maps to NeoCortex admin status for bootstrapping.

### Decision: Ingestion API JWT verification
- **Options**: A) Use FastMCP's Auth0Provider for ingestion too B) Use PyJWT directly C) Use Auth0's Python SDK
- **Chosen**: B — Use PyJWT with JWKS
- **Rationale**: The ingestion API is a standalone FastAPI app, not a FastMCP server.
  FastMCP's Auth0Provider includes OAuth proxy machinery that's unnecessary for a pure
  resource server. PyJWT with `PyJWKClient` is lightweight, well-tested, and does exactly
  what we need: RS256 JWT verification against Auth0's JWKS endpoint.
