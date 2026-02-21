# agent-2fa-hook

Policy-based approval hook with optional WebAuthn verification and a Lit dashboard UI.

## Quick Start

1. Install deps:
```bash
npm install
```
2. Build server + dashboard UI:
```bash
npm run build
```
3. Run dashboard:
```bash
npm run dashboard
```

Use `http://localhost:2222` for WebAuthn enrollment. Do not use `127.0.0.1`.

## Agent Attribution

Set `AGENT_2FA_AGENT_ID` per agent process to tag audit entries with agent identity.

Example:
```bash
AGENT_2FA_AGENT_ID=agent-1 npm run dashboard
```

## Useful Commands

- `npm run dashboard`: start dashboard and open browser
- `npm run dashboard:no-open`: start dashboard without opening browser
- `npm run dev:ui`: run Vite UI dev server from `src/ui`
- `npm run test`: run full test suite
- `npm run smoke`: build + dashboard smoke tests
- `npm run smoke:e2e`: API + hook integration checks

## Manual Dashboard Verification

1. Policy flow:
- Open `#/policy`
- Add/edit/reorder/delete rules
- Save policy and refresh
- Confirm persisted rules reload correctly

2. Credentials flow:
- Open `#/credentials`
- Click `Enroll Passkey`
- Complete platform biometric prompt
- Confirm credential appears in list
- Delete credential and confirm it disappears

3. Audit flow:
- Trigger hook decisions
- Open `#/audit`
- Verify entries appear
- Verify tool-name and decision filters
- Verify pagination controls
