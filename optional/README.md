# Optional production integrations

These sources preserve deployed fixes without enabling extra plugins on a fresh
installation. Existing payload plugins are still installed by the standard
installer. Review capabilities, upstream licenses and dependencies before copying
an optional plugin into an instance; generate local config through its WebUI.
Private config, relationship profiles, databases, stickers and job outputs are
intentionally absent. New plugins that need upstream image/font assets should
be installed from their manifest repository first, then receive this source overlay.

- vertex-media: explicit drawing, shared quota, delayed failure notice, read-only
  history reconciliation, bounded retry, original PNG file fallback and completion
  notification. Also requires the host recovery worker and NapCat evidence patch.
- code-tasks: background HTML/code files; requires task-runtime, not just a plugin.
- mai-life: life state, same-city coordinate cache and private sessions. Configure
  owner/friends explicitly; sleep must not block replies. Disable its duplicate
  debounce/search/drawing integrations when the corresponding dedicated plugins run.
- message-debounce-rebuild: single debounce owner. Keep Mai Life's debounce off;
  core uses fast scheduling. Private humanizer's schedule/proactive continuation
  must be off when Mai Life owns daily proactive caps.
- emoji-text-selector: prefer tagged 大肥鱼本体 stickers; fallback is permitted.
  Do not auto-delete user-managed emoji or restore manually deleted assets.
- curator: report-only destructive curation; protect own-character labels.
- impression-card: cross-session entertainment profiles remain opt-in; scheduled
  wake-ups should be off when Mai Life manages proactive contact.
- friend-request-handler: manual approval; configure an explicit admin QQ.
- random gallery: nsfw_allowed=false, sfw_allowed=true, NSFW filter enabled,
  empty group allowlist, private_allowed=false, fallback_to_sfw=false. This
  category filter is not per-image content moderation.

MaiWork was disabled in production and is not included in this source snapshot. Do not
enable it or legacy Codex drawing/Bilibili repost merely because source is present.
The removed maibot-moepix plugin is no longer shipped.

## Delivery/runtime dependencies

napcat/Dockerfile uses the same pinned upstream base and final instrumented runtime
as production (native delivery evidence and fail-closed private UID targeting).
Build separately; the default installer does not replace NapCat automatically.
maintenance/qqbridge_recovery.py is a host-only worker; inspect its fixed instance
paths and allowed actions before installing a 30-second systemd timer. It depends
on matching vertex-media code and must not be run against an unrelated account.

One start notice, exception notice after 60 seconds at most once, completion after
reliable evidence. Unknown delivery is not proof of absence: do not blindly resend.
Images share 10/day and voice 20/day. Unified TTS uses the Vertex ledger for the
shared voice cap; deploy both integrations together.

The public package does not reproduce any user's owner/friend list or city settings.
Configure those locally. Never copy live config.toml, .env, tokens or login data.

Unified TTS 3.3.5 is an optional overlay: the default payload retains its standalone upstream version. Install the 3.3.5 overlay only together with vertex-media for the shared quota module.
