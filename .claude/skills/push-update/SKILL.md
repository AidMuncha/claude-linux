---
name: push-update
description: Publish a new Claude Linux version so every installed copy shows "New Update Required". Use when the user says "push a new update", "release", or "ship this".
---

Claude Linux apps check `claude_linux/update_url.txt` (a manifest address) on start and every 6 hours. A newer signed
version there makes every installed copy show the "New Update Required" dialog with Download now + a progress bar.

Do these in order; stop and tell the user if any step fails.

1. **Ask what changed** in one line (this becomes the dialog's notes) and whether the update is required (default) or optional (`--optional`, users get a Later button).
2. **Pick the version**: current is in `claude_linux/version.py`. Default to a patch bump (1.0.0 -> 1.0.1); bigger for new features. It must be higher than the current one.
3. **Run the whole test suite**: `tests/run_tests.sh`. Do not release if anything fails.
4. **Build**: `python3 release.py <version> --notes "<notes>" [--optional]`. This bumps the version, builds and signs `dist/claude-linux-<version>.tar.gz`, writes `dist/latest.json` and a fresh `dist/claude-linux-installer.sh`.
5. **Publish**: with GitHub set up, add `--publish` to the step-4 command (it commits and pushes). Otherwise upload everything in `dist/` to the folder the address in `update_url.txt` points to. If `update_url.txt` is empty, hosting is not set up yet: say so and ask the user where to host (GitHub Releases/Pages, a Gist, their own server). Uploading publishes to the internet, so confirm with the user first.
6. **Verify**: fetch the live manifest and run it through `claude_linux/update.py` (`fetch_manifest`, `download`, `verify_signature`) to confirm users would accept it.
7. Remind the user: the signing key is `~/.local/share/claude-linux-release/private.pem` - it must be backed up and never shared; without it nobody can be updated.

Never edit `update_pubkey.pem` or regenerate the key: installed apps trust only that key, and a different one would lock every user out of updates.
