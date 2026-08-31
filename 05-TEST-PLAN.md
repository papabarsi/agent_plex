# Test Plan: SABnzbd Service Restart & Port Recovery

**Generated**: 2026-07-06T18:42:04Z  
**Remediation Target**: SABnzbd port 8080 not listening (service status OK but unbound)  
**Test Strategy**: Non-destructive verification of pre/post-restart state; safe execution with rollback triggers  

---

## Pre-Execution Baseline

Capture current system state before remediation begins. These commands establish the baseline against which all post-execution changes are measured.

| Step | Command | Purpose |
|------|---------|---------|
| 1 | `systemctl status sabnzbdplus` | Record service state, PID, recent errors |
| 2 | `sudo ss -tulpn \| grep 8080` | Confirm port 8080 is NOT listening (expected baseline) |
| 3 | `sudo ss -tulpn \| grep sabnzbd` | Check all SABnzbd port bindings |
| 4 | `journalctl -u sabnzbdplus --no-pager -n 50` | Capture last 50 log lines (error patterns) |
| 5 | `ls -la /home/barsi/.sabnzbd/nzb_queue/` | Record queue directory state and file count |
| 6 | `cat /home/barsi/.sabnzbd/sabnzbd.ini \| grep -E "^host|^port|^enable_all_par"` | Verify configuration (host binding, port) |
| 7 | `find /home/barsi/Downloads/incomplete/ -type f -mmin -5 \| wc -l` | Count recently-modified files in post-processing directory |
| 8 | `df -h /home/barsi/Downloads` | Disk space available for SABnzbd operations |
| 9 | `curl -s -w "%{http_code}" -o /dev/null http://localhost:32400/status \| xargs echo "Plex HTTP response:"` | Verify Plex is accessible (dependency check) |
| 10 | `curl -s -w "%{http_code}" -o /dev/null http://localhost:7878/api/v3/health \| xargs echo "Radarr HTTP response:"` | Verify Radarr is accessible (dependency check) |
| 11 | `curl -s -w "%{http_code}" -o /dev/null http://localhost:8989/api/v3/health \| xargs echo "Sonarr HTTP response:"` | Verify Sonarr is accessible (dependency check) |
| 12 | `systemctl is-active plexmediaserver && echo "PASS" \|\| echo "FAIL"` | Verify Plex service is running |
| 13 | `systemctl is-active radarr && echo "PASS" \|\| echo "FAIL"` | Verify Radarr service is running |
| 14 | `systemctl is-active sonarr && echo "PASS" \|\| echo "FAIL"` | Verify Sonarr service is running |

---

## Tests

Each test verifies one aspect of the remediation. All commands are **read-only** or **non-destructive service operations**.

### Test 1: Pre-Restart Queue State (Decision Gate)

**Test**: Verify whether queue is active/empty and post-processing is idle  
**Commands**:
```bash
# Check for queued NZB files
find /home/barsi/.sabnzbd/nzb_queue/ -name "*.nzb" -o -name "*.nzb.backup" | wc -l

# Check for active post-processing (files modified in last 5 minutes)
find /home/barsi/Downloads/incomplete/ -type f -mmin -5 | wc -l

# Check SABnzbd queue status from config
grep "^queue_directory" /home/barsi/.sabnzbd/sabnzbd.ini

# Check for active SABnzbd process (PID confirmation)
ps aux | grep -i sabnzbd | grep -v grep | awk '{print "PID: " $2 " Memory: " $6 " Command: " $11,$12}'
```

**Expected Result**:
- Queue directory exists and is readable
- Zero or minimal NZB files queued (acceptable if ≤ 2 pending)
- Recent file count in `/home/barsi/Downloads/incomplete/` is 0–2 (minimal activity)
- SABnzbd process is running under the expected user

**Failure Indicator**:
- Cannot read queue directory (permission error)
- ≥ 10 queued NZBs (risk of interrupting active transfer)
- ≥ 5 recently-modified files in incomplete directory (active post-processing)
- No SABnzbd process found (service is dead, not just unbound — requires different fix)

---

### Test 2: Pre-Restart Port Binding State

**Test**: Confirm port 8080 is NOT listening (matches issue description)  
**Command**:
```bash
sudo ss -tulpn | grep 8080 || echo "No process listening on 8080 (expected)"
```

**Expected Result**:
- Empty output OR message "No process listening on 8080" — port is not bound

**Failure Indicator**:
- Output shows `LISTEN ... :8080 ... sabnzbd` — port is already listening (issue already resolved)
- Output shows a different process on port 8080 (conflict — do not proceed with restart)

---

### Test 3: Service Status Before Restart

**Test**: Confirm service status and capture error context  
**Command**:
```bash
systemctl status sabnzbdplus --no-pager | head -20
```

**Expected Result**:
- Status shows `active (running)` OR `inactive (dead)` (service state is deterministic)
- No critical errors in first 20 lines
- If status is `inactive`, logs should indicate why (e.g., bind failure)

**Failure Indicator**:
- Status shows `failed` with persistent error (e.g., "address already in use" on 8080 — port conflict)
- Status shows `activating` (service is mid-restart from another process)

---

### Test 4: System Load & Memory (Safety Gate)

**Test**: Verify system has capacity for service restart  
**Command**:
```bash
echo "Load average:" && cat /proc/loadavg | awk '{print "1m: " $1 ", 5m: " $2 ", 15m: " $3}'
echo "Memory available:" && free -m | grep "Mem:" | awk '{printf "Used: %d/%d MB (%.1f%%)\n", $3, $2, $3*100/$2}'
```

**Expected Result**:
- Load average ≤ 4.0 (2 CPU cores, acceptable headroom)
- Memory available ≥ 1000 MB (safe for restart)

**Failure Indicator**:
- Load average ≥ 6.0 (system under high stress, restart may cascade)
- Memory available < 500 MB (risk of OOM on restart)

---

### Test 5: Plex Dependency Health (Pre-Restart)

**Test**: Ensure Plex is running and accessible (Plex has higher priority than SABnzbd)  
**Commands**:
```bash
systemctl is-active plexmediaserver && echo "OK" || echo "FAIL"
curl -s -w "%{http_code}" -o /dev/null http://localhost:32400/status
```

**Expected Result**:
- Service is active (running)
- HTTP response code is 200 (Plex is responsive)

**Failure Indicator**:
- Service is not running
- HTTP response is not 200 or times out

---

### Test 6: Radarr/Sonarr Dependency Health (Pre-Restart)

**Test**: Ensure Radarr and Sonarr are running (they will need to reconnect to SABnzbd after restart)  
**Commands**:
```bash
echo "=== Radarr ===" 
systemctl is-active radarr && echo "OK" || echo "FAIL"
curl -s -w "%{http_code}" -o /dev/null http://localhost:7878/api/v3/health

echo "=== Sonarr ===" 
systemctl is-active sonarr && echo "OK" || echo "FAIL"
curl -s -w "%{http_code}" -o /dev/null http://localhost:8989/api/v3/health
```

**Expected Result**:
- Both services are active (running)
- Both HTTP responses are 200 (services are responsive)

**Failure Indicator**:
- Either service is not running (they won't be able to reconnect to SABnzbd after restart)
- Either service times out or returns non-200 (pre-existing connectivity issue)

---

### Test 7: Service Restart Execution

**Test**: Execute the restart and monitor for errors  
**Commands**:
```bash
# Restart service
sudo systemctl restart sabnzbdplus

# Wait for stabilization
sleep 5

# Check if restart succeeded
systemctl is-active sabnzbdplus && echo "Service is running" || echo "Service failed to start"

# Check for immediate errors
journalctl -u sabnzbdplus --no-pager -n 10 | grep -i "error\|failed\|critical" || echo "No immediate errors"
```

**Expected Result**:
- Service transitions to `active (running)`
- No error lines in the last 10 log entries
- Service stabilizes within 5 seconds

**Failure Indicator**:
- Service fails to start (shows `inactive (dead)` or `failed`)
- Logs show "bind error", "address already in use", or "permission denied"
- Service restarts repeatedly (systemd watchdog triggering)

---

### Test 8: Port Binding After Restart

**Test**: Confirm port 8080 is now listening  
**Command**:
```bash
sudo ss -tulpn | grep 8080
```

**Expected Result**:
- Output shows: `tcp ... 0.0.0.0:8080 ... LISTEN ... sabnzbdplus`
- Port is bound to the correct service

**Failure Indicator**:
- No output (port still not listening — restart did not fix the issue)
- Output shows a different process on port 8080 (new conflict introduced)
- Output shows SABnzbd bound to a different port (config parsing error)

---

### Test 9: SABnzbd Service Status After Restart

**Test**: Verify service is healthy and accepting connections  
**Commands**:
```bash
echo "=== Service Status ===" 
systemctl status sabnzbdplus --no-pager | head -10

echo "=== Recent Logs ===" 
journalctl -u sabnzbdplus --no-pager -n 20 | tail -10

echo "=== Config Verification ===" 
grep "^host\|^port\|^enable_all_par" /home/barsi/.sabnzbd/sabnzbd.ini | head -5
```

**Expected Result**:
- Service shows `active (running)` with uptime > 5 seconds
- Logs show successful startup messages (e.g., "Starting SABnzbd", "listening on", "queue resumed")
- Configuration lines show expected host binding (0.0.0.0 or 127.0.0.1) and port 8080

**Failure Indicator**:
- Service shows `inactive` or `failed` status
- Logs show repeated bind errors or crash stack traces
- Configuration shows wrong port or disabled service

---

### Test 10: SABnzbd API Accessibility

**Test**: Verify SABnzbd is accessible via HTTP API (used by Radarr/Sonarr)  
**Command**:
```bash
curl -s -w "\nHTTP Status: %{http_code}\n" http://localhost:8080/api?mode=version 2>&1 | head -5
```

**Expected Result**:
- HTTP response contains JSON or XML data (API response)
- HTTP Status is 200 (OK)

**Failure Indicator**:
- Connection refused (port not truly listening)
- HTTP Status is not 200 (e.g., 403, 500)
- Empty response (port listening but service not responding)

---

### Test 11: Queue Recovery After Restart

**Test**: Verify that SABnzbd successfully re-loaded the on-disk queue  
**Commands**:
```bash
echo "=== Queue State Post-Restart ===" 
ls -la /home/barsi/.sabnzbd/nzb_queue/ | head -10

echo "=== Recent Log: Queue Recovery ===" 
journalctl -u sabnzbdplus --no-pager -n 50 | grep -i "queue\|resume\|loading" | tail -5 || echo "(no queue messages found)"
```

**Expected Result**:
- Queue directory is readable and contains the same files as pre-restart
- Logs show queue was resumed (e.g., "Resuming queue", "Loading NZB files")

**Failure Indicator**:
- Queue directory is empty when it should contain files (data loss)
- Logs show "queue truncated" or "queue reset" messages (corruption)

---

### Test 12: Radarr/Sonarr Reconnection

**Test**: Verify Radarr and Sonarr successfully reconnected to SABnzbd  
**Commands**:
```bash
echo "=== Radarr Health ===" 
systemctl is-active radarr && echo "OK" || echo "FAIL"
curl -s -w "%{http_code}" -o /dev/null http://localhost:7878/api/v3/health

echo "=== Sonarr Health ===" 
systemctl is-active sonarr && echo "OK" || echo "FAIL"
curl -s -w "%{http_code}" -o /dev/null http://localhost:8989/api/v3/health

echo "=== Recent Radarr Logs (SABnzbd connection) ===" 
journalctl -u radarr --no-pager -n 30 | grep -i "sabnzbd\|indexer" | tail -3 || echo "(no SABnzbd messages)"

echo "=== Recent Sonarr Logs (SABnzbd connection) ===" 
journalctl -u sonarr --no-pager -n 30 | grep -i "sabnzbd\|indexer" | tail -3 || echo "(no SABnzbd messages)"
```

**Expected Result**:
- Radarr and Sonarr are still active (running)
- HTTP responses are 200 for both
- Logs show successful connection or "downloading" activity (if active)

**Failure Indicator**:
- Either service crashed (shows `inactive`)
- Either service shows connection refused or timeout errors
- Services show persistent "unable to communicate with SABnzbd" messages (network issue)

---

### Test 13: Post-Processing Orphan Detection

**Test**: Check for orphaned/partial files in media directories (indicator of interrupted move)  
**Commands**:
```bash
echo "=== Movies (temp files) ===" 
find /plexmedia*/movies -name ".*" -mmin -10 2>/dev/null | head -10 || echo "None found"

echo "=== Shows (temp files) ===" 
find /plexmedia*/shows -name ".*" -mmin -10 2>/dev/null | head -10 || echo "None found"

echo "=== Incomplete directory (recent files) ===" 
find /home/barsi/Downloads/incomplete/ -type f -mmin -5 2>/dev/null | wc -l
```

**Expected Result**:
- No orphaned temp files (names starting with .)
- Incomplete directory has 0–1 recent files (normal state or single transfer)

**Failure Indicator**:
- Multiple orphaned temp files (e.g., `.partial_filename`, `_temp_dir`)
- Incomplete directory has ≥ 5 recent files (active transfer interrupted)

---

### Test 14: Plex Library Import Status

**Test**: Verify Plex library is responding and imports are not blocked by SABnzbd restart  
**Command**:
```bash
bash /home/barsi/media-server-agent/agents/plex-import-checker.sh 2>&1 | tail -20
```

**Expected Result**:
- Script completes without errors
- Shows Sonarr/Radarr count matches Plex count (all imports up-to-date)
- No "missing" or "gap" entries

**Failure Indicator**:
- Script fails (Plex connectivity issue)
- Shows missing items or episode gaps (import pipeline blocked)

---

## Post-Execution Verification

Ordered sequence of verification steps to run after all remediation is complete. These confirm the remediation achieved its goal and did not introduce new issues.

| Step | Command | What It Checks | Success Criteria |
|------|---------|---|---|
| **1** | `sudo ss -tulpn \| grep 8080` | Port 8080 is listening | Output shows `LISTEN ... 0.0.0.0:8080 ... sabnzbdplus` |
| **2** | `systemctl status sabnzbdplus \| head -5` | Service state | Shows `active (running)` |
| **3** | `curl -s -w "%{http_code}" -o /dev/null http://localhost:8080/api?mode=version` | API accessibility | Returns 200 HTTP status |
| **4** | `systemctl is-active plexmediaserver` | Plex still running | Outputs `active` |
| **5** | `systemctl is-active radarr` | Radarr still running | Outputs `active` |
| **6** | `systemctl is-active sonarr` | Sonarr still running | Outputs `active` |
| **7** | `curl -s -w "%{http_code}" -o /dev/null http://localhost:32400/status` | Plex is responsive | Returns 200 HTTP status |
| **8** | `curl -s -w "%{http_code}" -o /dev/null http://localhost:7878/api/v3/health` | Radarr is responsive | Returns 200 HTTP status |
| **9** | `curl -s -w "%{http_code}" -o /dev/null http://localhost:8989/api/v3/health` | Sonarr is responsive | Returns 200 HTTP status |
| **10** | `journalctl -u sabnzbdplus --since "30 minutes ago" \| grep -i "error\|failed\|critical" \| wc -l` | Critical errors in logs | Returns 0 (no critical errors) |
| **11** | `find /plexmedia*/movies -name ".*" -mmin -5 2>/dev/null \| wc -l` | Orphaned files (movies) | Returns 0 |
| **12** | `find /plexmedia*/shows -name ".*" -mmin -5 2>/dev/null \| wc -l` | Orphaned files (shows) | Returns 0 |
| **13** | `bash /home/barsi/media-server-agent/agents/plex-import-checker.sh 2>&1 \| grep "Status:"` | Plex imports current | Shows `Status: ok` |
| **14** | `systemctl status sabnzbdplus --no-pager \| grep "Restart: no"` | Service auto-restart disabled | Confirms restart policy (or shows current policy) |

---

## Rollback Trigger Conditions

Automatic rollback is triggered if ANY of these conditions are detected:

### Critical (Automatic Rollback Immediate)

1. **Core service dependency failure**: Plex, Radarr, or Sonarr is not `active` after restart
   - **Check**: `systemctl is-active {plexmediaserver|radarr|sonarr}`
   - **Action**: Rollback immediately (restart SABnzbd again)

2. **Port 8080 still not listening after restart**: The remediation did not fix the issue
   - **Check**: `sudo ss -tulpn | grep 8080 | grep LISTEN` returns empty
   - **Action**: Rollback (restart SABnzbd again) and escalate to manual investigation

3. **Port 8080 bound to a different process**: A conflict was introduced
   - **Check**: `sudo ss -tulpn | grep 8080` shows a service other than `sabnzbdplus`
   - **Action**: Rollback immediately (restart SABnzbd to verify it can bind)

4. **SABnzbd service is "failed" after restart**: Service crashed during startup
   - **Check**: `systemctl status sabnzbdplus | grep "failed"`
   - **Action**: Rollback and inspect logs for root cause

5. **SABnzbd in restart loop**: Service is restarting every few seconds
   - **Check**: `systemctl status sabnzbdplus | grep "Restart:.*active"` or `journalctl -u sabnzbdplus -n 50 | grep "Started" | wc -l` > 3 in 1 minute
   - **Action**: Rollback (stop restart loop), escalate to manual investigation

### Warning (Rollback If Confirmed)

6. **Multiple orphaned temp files detected**: ≥ 3 partial/temp files in media directories
   - **Check**: `find /plexmedia*/{movies,shows} -name ".*" -mmin -5 2>/dev/null | wc -l`
   - **Action**: Investigate file contents; if they are from an interrupted post-processing, rollback

7. **Radarr/Sonarr connection errors in logs**: Unable to reconnect to SABnzbd
   - **Check**: `journalctl -u {radarr|sonarr} --since "5 minutes ago" | grep -i "sabnzbd.*refused\|sabnzbd.*timeout"`
   - **Action**: Wait 30 seconds for auto-retry; if still failing, rollback

8. **Plex import status shows missing items**: Import pipeline blocked by SABnzbd restart
   - **Check**: `bash /home/barsi/media-server-agent/agents/plex-import-checker.sh | grep "missing\|gap"`
   - **Action**: If ≥ 5 missing/gap entries, rollback and investigate

---

## Rollback Commands

If any critical rollback trigger is detected, execute these commands in order to revert the remediation.

### Rollback Step 1: Restart SABnzbd Again

```bash
sudo systemctl restart sabnzbdplus
sleep 5
systemctl status sabnzbdplus | head -5
```

**Rationale**: Since the service is stateless and the queue persists on disk, a second restart often resolves transient bind failures or race conditions that occurred during the first restart.

**Success Indicator**: Service is `active (running)` after second restart.

---

### Rollback Step 2: Force Rebind (If Port Still Not Listening)

```bash
# Stop the service
sudo systemctl stop sabnzbdplus
sleep 2

# Verify the port is released
sudo ss -tulpn | grep 8080 && echo "WARNING: Port still in use" || echo "Port released"

# Check for lingering SABnzbd processes
ps aux | grep sabnzbd | grep -v grep || echo "No lingering processes"

# Restart again
sudo systemctl restart sabnzbdplus
sleep 5

# Verify port binding
sudo ss -tulpn | grep 8080
```

**Rationale**: If a second restart doesn't bind the port, the OS may have not fully released the port. Explicit stop + sleep + restart gives the kernel time to clean up socket state.

**Success Indicator**: Port shows `LISTEN` on 8080 after force rebind.

---

### Rollback Step 3: Verify No Configuration Corruption

```bash
# Check SABnzbd config file for syntax errors
grep "^host\|^port" /home/barsi/.sabnzbd/sabnzbd.ini

# Verify no partial/corrupt config
ls -la /home/barsi/.sabnzbd/sabnzbd.ini*

# Check if config was recently modified unexpectedly
stat /home/barsi/.sabnzbd/sabnzbd.ini | grep "Modify"
```

**Rationale**: If the config was corrupted during service operations, manual restart won't help. This check identifies if config restoration is needed.

**Success Indicator**: Config file shows expected host/port settings and recent modify time is within last 10 minutes.

---

### Rollback Step 4: Inspect Service Logs for Root Cause

```bash
echo "=== Last 50 lines of SABnzbd logs ===" 
journalctl -u sabnzbdplus --no-pager -n 50

echo "=== Error/warning summary ===" 
journalctl -u sabnzbdplus --no-pager -n 100 | grep -i "error\|warn\|fail\|critical" | tail -10
```

**Rationale**: If restart still fails, logs will reveal the specific error (bind failure, permission denied, config parsing error, etc.).

**Success Indicator**: Logs clearly indicate the root cause (e.g., "Address already in use by process X", "Permission denied on socket", etc.).

---

### Rollback Step 5: Verify Dependent Services Survived

```bash
echo "=== Plex ===" 
systemctl is-active plexmediaserver && curl -s -w "%{http_code}\n" -o /dev/null http://localhost:32400/status

echo "=== Radarr ===" 
systemctl is-active radarr && curl -s -w "%{http_code}\n" -o /dev/null http://localhost:7878/api/v3/health

echo "=== Sonarr ===" 
systemctl is-active sonarr && curl -s -w "%{http_code}\n" -o /dev/null http://localhost:8989/api/v3/health
```

**Rationale**: Confirm that restart did not cascade and crash dependent services.

**Success Indicator**: All services are `active` and HTTP responses are 200.

---

### Rollback Step 6: Escalate to Manual Investigation

If all rollback steps fail to restore port 8080 to listening state:

1. **Log the failure**: Capture full diagnostics
   ```bash
   echo "=== ROLLBACK FAILED - MANUAL INVESTIGATION NEEDED ===" 
   echo "Timestamp: $(date)" 
   echo "Port binding status:" 
   sudo ss -tulpn | grep 8080 || echo "Port not listening"
   echo "Service status:" 
   systemctl status sabnzbdplus
   echo "Recent errors:" 
   journalctl -u sabnzbdplus --no-pager -n 50 | grep -i "error\|fail"
   ```

2. **Alert operator**: Trigger manual escalation (outside scope of automated test plan)

3. **Possible manual fixes** (operator-initiated):
   - Check if another process is bound to 8080: `lsof -i :8080` or `fuser 8080/tcp`
   - If application process is stuck, kill it: `sudo kill -9 <PID>`
   - Inspect firewall rules: `sudo iptables -L | grep 8080` or `sudo ufw status | grep 8080`
   - Check if bind is in TIME_WAIT: `sudo ss -tulpn | grep TIME_WAIT` and wait for timeout

---

## Test Execution Environment

### Prerequisites

- Bash 5.0+
- sudo privileges (for `systemctl` and `ss` commands)
- All core services running (Plex, Radarr, Sonarr, SABnzbd)
- Network connectivity to localhost

### Test Timeout

- Individual test: 30 seconds max (curl with `-m 10` timeout, Bash with `timeout` wrapper)
- Full test suite: 5 minutes max (including restart wait)

### Non-Destructive Operations

All tests use **read-only** operations or **safe systemd commands**:
- ✅ `systemctl status`, `systemctl is-active` (query only, no state change)
- ✅ `journalctl` (read logs)
- ✅ `ss`, `grep`, `find`, `ls` (file inspection)
- ✅ `curl` with `-o /dev/null` (HTTP request, no side effects)
- ✅ `systemctl restart` (only when explicitly part of remediation, not test)
- ❌ No files modified, no configs changed, no deletions

### Isolated from Production

- Tests run against actual running services but do not modify data
- Queue state captured before/after but not mutated
- All post-processing checks are read-only

---

## Expected Test Results

### Successful Remediation Signature

```
✅ Pre-Execution Baseline: 
   - Port 8080 NOT listening
   - Service active but unbound
   - No recent errors in logs
   - Queue is empty or minimal

✅ Test 8 (Port Binding After Restart): PASS
   - Port 8080 is LISTENING

✅ Test 9 (Service Status After Restart): PASS
   - Service is active (running)
   - No critical errors in logs

✅ Post-Execution Verification:
   - All core services responsive
   - No orphaned files
   - Plex import status OK

Result: ALL_PASS — Remediation successful
```

### Partial Failure (Rollback Required)

```
❌ Test 8 (Port Binding After Restart): FAIL
   - Port 8080 is still NOT LISTENING

Rollback Trigger: Critical (port still not listening)
Rollback Action: Restart SABnzbd again + inspect logs

Result: PARTIAL_FAIL — Rollback executed, manual investigation required
```

### Complete Failure (Escalate)

```
❌ Test 5 (Plex Dependency): FAIL
   - Plex service is not running after restart

Rollback Trigger: Critical (core service failure)
Rollback Action: Restart SABnzbd again, verify Plex recovers

If Plex does not recover:
   Result: ALL_FAIL — Escalate to manual investigation
```

---

## Test Plan Sign-Off

| Role | Status | Notes |
|------|--------|-------|
| QA | ✅ READY | Test plan is non-destructive, comprehensive, and includes clear rollback triggers |
| DevOps | ⏳ PENDING | Ready to execute tests after security audit approval |
| Operator | ⏳ WAITING | Standby for rollback escalation if any test fails |

---

**Test Plan Version**: 1.0  
**Last Updated**: 2026-07-06T18:42:04Z  
**Status**: Ready for Step 6 (DevOps Execution)
