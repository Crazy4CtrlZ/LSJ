# Deployed Application

| Item | Value |
|---|---|
| Deployed URL | _fill in after first Render deploy_ |
| Health endpoint | `<deployed-url>/health` |
| Host | Render free tier (single web service, per render.yaml) |

## Free-tier cold-start notes
- The instance sleeps after ~15 minutes of inactivity; the next request takes ~30–60 s while it wakes.
- On the very first boot the policy index is built (BUILD_INDEX_ON_START=1), adding ~1–2 minutes once.
- For the demo video we warm the service beforehand; evaluation reports cold and warm latency separately.
