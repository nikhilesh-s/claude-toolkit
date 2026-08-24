---
name: claude-toolkit-sync
type: system
status: daily
why: keeps Nik's and Arnau's toolkit repos in sync automatically, twice daily
setup: launchd job com.nik.claude-toolkit-sync; Nik's repo has Arnau's as read-only upstream; sync script handles unrelated histories, hardcoded-path conflicts, symlinks; logs to ~/Library/Logs/claude-toolkit/
backup: sync scripts in this repo; LaunchAgent plist must be reinstalled on new Mac
---
Hardened Aug 2026 after force-pushed upstream broke merges (unrelated histories, 85 path conflicts). Sends email notification on failure.
