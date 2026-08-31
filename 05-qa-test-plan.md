### TEST_PLAN

### Pre-Execution Baseline

Capture current system state before any remediation (none is planned). Run these commands to establish baseline health metrics:

**Core Services**
- `systemctl is-active plexmediaserver` — Plex service status
- `systemctl is-active radarr` — Radarr service status
- `systemctl is-active sonarr` — Sonarr service status
- `systemctl is-active sabnzbdplus` — SABnzbd service status

**Listening Ports**
- `ss -tlnp | grep :32400` — Plex listening port
- `ss -tlnp | grep :7878` — Radarr listening port
- `ss -tlnp | grep :8989` — Sonarr listening port
- `ss -tlnp | grep :8080` — SABnzbd listening port

**Storage**
- `df -h /plexmedia` — Primary media storage usage
- `df -h /plexmedia2` — Secondary media storage usage
- `df -h /plexmedia3` — Tertiary media storage usage

**System Health**
- `cat /proc/loadavg` — System load average
- `free -m` — Memory usage
- `docker compose -f /home/barsi/projects/media/docker-compose.yml ps` — Agent stack container status

### Tests

No remediation actions proposed in plan 01-ops-plan.md → no remediation tests to execute.

The plan's status is HEALTHY with NO_ISSUES. All core services (Plex, Radarr, Sonarr, SABnzbd) are operating normally. Skipped items (health-report parse error, SABnzbd critical log detail) are observability gaps, not service faults, and require manual infrastructure review rather than software remediation.

### Post-Execution Verification

Not applicable. No remediation actions are being executed in this cycle.

### Rollback Trigger Conditions

None. No changes will be applied to the system. Rollback is not triggered.

### Rollback Commands

None. No remediation actions to reverse.

---

**Notes**

- **Health Report Parse Error**: The health-report JSON failed to parse at line 8 column 43 (invalid control character). This is a monitoring infrastructure issue documented in the plan's skipped items; it does not indicate a service problem.
- **SABnzbd Critical Flag**: SABnzbd reported Critical: 1, but the sample errors are dated 2026-03 through 2026-05 (outside the 6-hour review window). Import checks confirm the download→Plex chain is intact (104/104 movies, 22/22 series in Plex).
- **RAID Degraded**: 2 of 5 RAID disks are degraded. This is a known hardware condition, not a software fault.

**Pipeline handoff**: This test plan is ready for Step 6 (DevOps execution). Since no remediation actions are defined, Step 7 (QA Test Execution, Mode 2) will run the baseline verification commands above to confirm system state.
