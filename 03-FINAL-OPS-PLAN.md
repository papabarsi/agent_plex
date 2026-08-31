# System Health Analysis & Remediation Plan

### STATUS: ISSUES_FOUND

---

### Issues Identified

- **Issue**: SABnzbd service status shows "OK" but port 8080 is NOT LISTENING
- **Severity**: warning
- **Source**: Health Report (ports section), generated 2026-07-06T17:12:01Z
- **Evidence**: Services report `sabnzbdplus: OK`, but Ports section shows `sabnzbd (:8080): NOT LISTENING`. Service has not restarted recently (Restarts log shows 0 events), indicating the process is stuck or unbound rather than mid-recovery.

---

### Remediation Plan

- **Action**: Safely restart SABnzbd service with pre- and post-restart verification
  
  **Step 1: Pre-restart queue check (off-API, since port 8080 is down)**
  - Inspect on-disk queue state: `ls -la /home/barsi/.sabnzbd/nzb_queue/` and `cat /home/barsi/.sabnzbd/sabnzbd.ini | grep -E "queue|current"` — determine if any jobs are queued
  - Check for active post-processing: `find /home/barsi/Downloads/incomplete/ -type f -mmin -5 | head -20` — if recently-modified files exist, post-processing is in-flight
  - Decision: Only proceed with restart if no recent file activity in `/home/barsi/Downloads/incomplete/` (or accept documented small risk of resuming a partial unpack, which SABnzbd recovers on restart)
  
  **Step 2: Verify current port binding**
  - `sudo ss -tulpn | grep 8080` — confirm port is not listening (expected)
  - `systemctl status sabnzbdplus` — check service state and any error messages
  
  **Step 3: Restart the service**
  - `sudo systemctl restart sabnzbdplus`
  - Wait 5 seconds for service to stabilize
  
  **Step 4: Confirm port is listening**
  - `sudo ss -tulpn | grep 8080` — should show LISTEN state on 8080
  
  **Step 5: Post-restart verification**
  - `systemctl status sabnzbdplus` — confirm service is active/running
  - Check for orphaned partial files in media directories: `find /plexmedia*/movies -name ".*" -mmin -5` and `find /plexmedia*/shows -name ".*" -mmin -5` — if any recent temp/partial files found, investigate their content (may indicate interrupted move)
  - Monitor SABnzbd logs: `journalctl -u sabnzbdplus -n 50 --no-pager` — watch for binding errors or queue-resume messages

- **Risk**: low
  - Service is stateless; queue persists on disk and resumes after restart
  - Pre-check mitigates risk of interrupting mid-post-processing (the only scenario where a restart could leave partial files)
  - Radarr/Sonarr auto-recover on SABnzbd reconnection; no sequencing required
  - Plex (high priority, Nice=-1) is unaffected; SABnzbd runs at Nice=15 (lowest priority)
  
- **Rollback**: If the restart causes cascading failures:
  - `sudo systemctl restart sabnzbdplus` again (service will resume same state)
  - Check Radarr/Sonarr logs for SABnzbd connection errors; they auto-retry and will resume on port 8080 availability
  - No configuration files are modified, so no config restoration required
  
- **Expected Outcome**: Port 8080 listening and responding; SABnzbd WebUI and API accessible; Radarr/Sonarr successfully push NZBs to SABnzbd; Health Report shows `sabnzbd (:8080): listening` on next run

---

### Skipped Items

- **Plex HTTP errors to .plex.direct domains** — INFO severity, not actionable. These are transient attempts to reach Plex cloud infrastructure for remote access; local Plex service is listening (`:32400`) and functioning normally. Plex Import Check shows all content synced (18/18 Sonarr, 99/99 Radarr), so not a media sync problem.

- **Radarr/Sonarr "PendingReleaseService|Removing failed releases" log messages** — Matches known baseline (normal maintenance cleanup, not critical errors). Log samples are Debug-level messages, not errors.

- **SABnzbd filesystem errors (March–May historical entries)** — Matches known baseline (transient file locks during post-processing, typically resolved on next run). Dates predate current health report by 2+ months.

- **System service errors (port 8090 bind failures, trip-brochures.service failures)** — Not part of core media stack (Plex, Radarr, Sonarr, SABnzbd). Appear to be external/user services; out of scope for this remediation.

- **RAID 2 of 5 degraded** — Known hardware limitation, not software-remediable. Does not affect current availability (arrays are functioning).

- **Docker "not_available"** — Expected baseline state. Agent stack deployment is optional and independent of media services.

- **Disk usage (61–70% on /plexmedia*, 32% on /)** — All volumes under 90% threshold; no action required. Capacity is sufficient for current workload.

- **Load average (1.55 / 1.81 / 1.93) and Memory (60%)** — Within normal operating range for this workload; no action required.
