# Security & Shutdown Audit Report — AI Router Stage 8 (Distributed)

---

## SECURITY AUDIT

### 1. Logging of Secrets / Sensitive Data

| Severity | File | Line | Finding |
|----------|------|------|---------|
| **MEDIUM** | `app/distributed/redis_client.py` | 41 | Redis URL logged verbatim: `logger.info(f"Connected to Redis at {self._url}")`. If `REDIS_URL` contains an embedded password (e.g. `redis://:password@host/db`), it is written to logs in cleartext. |
| **MEDIUM** | `app/main.py` | 101–103 | Env vars (including `REDIS_URL`) printed to stdout during startup: `print(f"  {var}={val}")`. If `REDIS_URL` includes credentials they leak to console/logs. |
| **LOW** | `app/api.py` | 376 | Cache key logged/broadcast includes `request.messages` — user conversation content (PII). Not a credential leak but content exposure. |
| ✅ OK | `app/logger.py` | 18–38 | `SENSITIVE_FIELDS` set and `_sanitize_value` masks `api_key`, `secret`, `password`, `token`, `authorization`. This is correct defense-in-depth. |

### 2. Unsafe Deserialization (eval / exec / pickle)

| Severity | File | Line | Finding |
|----------|------|------|---------|
| ✅ OK | *(all files)* | — | No `eval()`, `exec()`, `pickle`, `shelve`, or `yaml.load()` without `Loader`. All JSON deserialization uses safe `json.loads()`. |
| INFO | `app/distributed/dlq.py` | 58 | Uses `__import__("app.tasks.status", ...)` — dynamic import, but of a known internal module only. Not a vector. |

### 3. Command Injection

| Severity | File | Line | Finding |
|----------|------|------|---------|
| ✅ OK | *(all files)* | — | No `os.system()`, `subprocess.Popen()`, or shell execution with unsanitized user input found. |

### 4. Path Traversal

| Severity | File | Line | Finding |
|----------|------|------|---------|
| ✅ OK | *(all files)* | — | All file reads use hardcoded paths (e.g. `/proc/self/status`, `.meta/build.json`, config dir). No user-supplied path components are used. |

### 5. Redis Port Exposure & Authentication

| Severity | File | Line | Finding |
|----------|------|------|---------|
| **CRITICAL** | `docker-compose.yml` | 201–202 | Redis port `6379` is mapped to **all interfaces** (`"6379:6379"`). No `127.0.0.1:` binding. In contrast, the ollama service correctly uses `"127.0.0.1:11434:11434"`. Redis is reachable from any host that can reach the Docker host. |
| **CRITICAL** | `docker-compose.yml` | 197–212 | Redis has **no password / `--requirepass`** and no mounted `redis.conf`. Any container or external host that connects can issue arbitrary commands. |
| **CRITICAL** | `docker-compose.yml` | 211 | Redis is on the `ai-router-net` bridge, shared with all other services — so if any container is compromised, Redis is directly accessible without auth. |

### 6. Input Validation on New Runtime Endpoints

| Severity | File | Line | Endpoint | Finding |
|----------|------|------|----------|---------|
| ✅ OK | `app/api.py` | 1215–1251 | `/runtime/health`, `/runtime/workers`, `/runtime/leader`, `/runtime/queue`, `/runtime/events` | All are read-only `GET` endpoints with **no user input parameters**. No validation needed. |
| **BUG** (functional) | `app/api.py` | 1187–1212 | `_get_health()` | Creates `AsyncRedisClient()` but **never calls `.connect()`**. Every method checks `if self._redis is None: return None`. Runtime endpoints silently return empty/default data instead of actual health info. |

### 7. docker-compose.yml — Redis Summary

- **Password**: ❌ Not set (no `command: redis-server --requirepass ...`, no config file)
- **Port binding**: ❌ `"6379:6379"` → bound to `0.0.0.0:6379` (should be `"127.0.0.1:6379:6379"`)
- **Network**: On the shared bridge `ai-router-net`, accessible to all containers

---

## SHUTDOWN AUDIT

### 1. `app/worker.py` — SIGTERM/SIGINT Handling

| Severity | Lines | Finding |
|----------|-------|---------|
| **HIGH** | 101–102 | `loop.add_signal_handler(sig, lambda: loop.stop())` stops the event loop immediately but does **not** cancel the worker tasks. The `finally` block in `run_worker()` (lines 90–94) may not execute because `loop.stop()` does not raise `CancelledError` — it just halts the loop. |
| **HIGH** | 36–73 | `process_one()` has **no cancellation point**. If SIGTERM arrives while a task is being processed, the task is abandoned mid-flight: the lease is not released, no `nack` is sent, and the task may remain in RUNNING state permanently. |
| **HIGH** | 85 | Worker tasks are `asyncio.gather(*tasks)` but cancellation only propagates if the tasks are actually cancelled — `loop.stop()` does not cancel them. |
| **MEDIUM** | 96 | `stop_heartbeat()` is called on exit (line 94), but **`registry.unregister()` is never called**. The worker remains in the registry as ONLINE until heartbeat TTL expires (15s). |
| **MEDIUM** | 75–83 | `poll_loop()` uses `while True` with **no `_running` flag**. It relies solely on `CancelledError` to break, which requires explicit task cancellation. |

### 2. `app/scheduler.py` — Leadership Release on Shutdown

| Severity | Lines | Finding |
|----------|-------|---------|
| **CRITICAL** | 37–38 | Signal handler calls `loop.stop()` directly. **`scheduler.stop()` is never called.** The distributed lock and leader key remain in Redis, causing a stale leader record. |
| **CRITICAL** | 27–31 | `run_scheduler()` has `while True` with no cancellation handling. When the loop stops, the `DistributedScheduler.stop()` method (which releases the leadership lock) is never invoked. |
| **HIGH** | `distributed_scheduler.py:144–148` | `_release_leadership` exists and works correctly, but is **dead code** — nothing in `scheduler.py` calls `scheduler.stop()`. |

### 3. `app/main.py` — Distributed Lifecycle Shutdown

| Severity | Lines | Finding |
|----------|-------|---------|
| **CRITICAL** | 115–121 | `graceful_shutdown()` calls `sys.exit(0)`. Does **not** close Redis connections, stop the event bus listener, stop the scheduler, or stop heartbeats. |
| **CRITICAL** | 131–180 | Distributed components are created and started but **no references are retained** for shutdown. When `sys.exit(0)` is called, Redis connections, pubsub subscriptions, and heartbeat loops are all leaked. |
| **HIGH** | 165–175 | Services are started in a separate event loop (`_loop`), but signal handlers for SIGTERM/SIGINT are registered *after* this block. The `graceful_shutdown` handler only calls `sys.exit(0)`, so the second event loop's tasks are never awaited. |

### 4. `distributed_queue.py` — Shutdown Cleanup

| Severity | File | Finding |
|----------|------|---------|
| ✅ OK | `distributed_queue.py` | No cleanup needed — the queue is a stateless wrapper around Redis operations. Redis connection lifecycle is managed by `AsyncRedisClient`. |

### 5. `event_bus.py` — `stop_listener()` Cleanup

| Severity | Lines | Finding |
|----------|-------|---------|
| ✅ OK | 74–82 | `stop_listener()` correctly sets `_running = False`, cancels `_listener_task`, awaits it, and unsubscribes from the channel. |
| ✅ OK | 84–98 | `_listen_loop()` checks `self._running` and catches `CancelledError` to break cleanly. |
| **LOW** | 97–98 | Exception handler catches all `Exception` but not `BaseException` — `CancelledError` (which is `BaseException`) is not caught here, which is actually correct behavior for cancellation. |

### 6. `worker_registry.py` — `stop_heartbeat()` Cleanup

| Severity | Lines | Finding |
|----------|-------|---------|
| ✅ OK | 96–97 | `stop_heartbeat()` sets `_running = False`, which causes `start_heartbeat_loop()` to exit on its next iteration check. |
| **LOW** | 94 | The heartbeat loop sleeps for `_heartbeat_interval` seconds. Setting `_running = False` while the loop is sleeping won't interrupt it — the loop exits one sleep-cycle later. Not immediate. |
| **MEDIUM** | — | `stop_heartbeat()` does **not** call `unregister()`. The worker record stays in Redis with `status = ONLINE` until the heartbeat key expires (15s TTL). |

---

## MEMORY / ORPHAN TASK AUDIT

### 1. Untracked `asyncio.create_task()` Calls

| Severity | File | Line | Finding |
|----------|------|------|---------|
| **MEDIUM** | `distributed_scheduler.py` | 66–67 | `asyncio.create_task(self._leader_election_loop())` and `asyncio.create_task(self._job_execution_loop())` are **fire-and-forget**. They are not stored as instance variables, cannot be explicitly cancelled, and not awaited. If `stop()` is called, `_running` is set to `False` but the tasks continue their current iteration. |
| **LOW** | `distributed_scheduler.py` | 66–67 | If `_leader_election_loop()` crashes with an exception not caught by the `try/except` (e.g. `asyncio.CancelledError`), the task silently terminates while `_job_execution_loop` continues. The scheduler becomes a zombie — not leader, not trying to become leader. |
| ✅ OK | `event_bus.py` | 72 | `self._listener_task = asyncio.create_task(self._listen_loop())` — properly tracked and cancelled in `stop_listener()`. |
| ✅ OK | `worker.py` | 85 | Worker poll tasks stored in a list and `await asyncio.gather(*tasks)`. |

### 2. Infinite Loops Without Cancellation Mechanisms

| Severity | File | Line | Finding |
|----------|------|------|---------|
| **MEDIUM** | `worker.py` | 75–83 | `poll_loop()` uses `while True` without a `_running` flag. The only exit path is `asyncio.CancelledError`. Since the signal handler uses `loop.stop()` instead of cancelling tasks, this loop may never exit gracefully. |
| ✅ OK | `distributed_scheduler.py` | 82, 118 | Both `_leader_election_loop` and `_job_execution_loop` check `while self._running`. |
| ✅ OK | `event_bus.py` | 84 | `_listen_loop` checks `while self._running`. |
| ✅ OK | `worker_registry.py` | 89 | `start_heartbeat_loop` checks `while self._running`. |

### 3. Orphan Tasks on Exception

| Severity | File | Lines | Finding |
|----------|------|-------|---------|
| **MEDIUM** | `distributed_scheduler.py` | 66–67 | Both background tasks are isolated fire-and-forget. If `_job_execution_loop` raises an exception (its `try` at line 126 handles `Exception` in the inner loop, but an exception in the outer logic would kill the task), `_leader_election_loop` continues running but no jobs are executed — the scheduler is in a broken state. |
| ✅ OK | `worker.py` | 81–83 | The `except Exception` in `poll_loop()` catches all errors and continues, preventing orphan tasks. |

### 4. `distributed_scheduler.py` — Loop Stop on Shutdown

| Severity | Lines | Finding |
|----------|-------|---------|
| **CRITICAL** | 69–73 | `stop()` exists and sets `_running = False` then releases leadership. **But it is never called** from the entry point (`scheduler.py`). |
| **MEDIUM** | 82, 118 | Even if `stop()` were called, `_leader_election_loop` and `_job_execution_loop` could be mid-`asyncio.sleep()` (3s and 1s respectively). Setting `_running = False` doesn't interrupt the sleep. Loops exit after their current delay completes. Not a leak but delayed shutdown. |
| **LOW** | 142 | `_job_execution_loop` could be executing `queue.create_task()` (a DB write) when `_running` is set to `False`. The loop won't check until the next iteration, after the DB write completes. Acceptable behavior. |

---

## CONSOLIDATED FINDINGS SUMMARY

### CRITICAL (3)
1. **Redis exposed on 0.0.0.0 without password** — `docker-compose.yml:201-202`, `:197-212`. Any host can connect. No auth, no localhost binding.
2. **No cleanup of distributed lifecyle on shutdown** — `app/main.py:115-121`, `:131-180`. `sys.exit(0)` leaks Redis connections, pubsub, heartbeats, and scheduler leader lock.
3. **Scheduler never releases leadership on shutdown** — `app/scheduler.py:37-38`, `distributed_scheduler.py:69-73` (dead code). Stale leader key remains in Redis.

### HIGH (3)
1. **Worker abandons active tasks on SIGTERM** — `app/worker.py:101-102`. `loop.stop()` doesn't cancel tasks; leases not released; no nack sent.
2. **Worker doesn't unregister on shutdown** — `app/worker.py:94`. Only stops heartbeat, leaves `status=ONLINE` in registry.
3. **Runtime health endpoints silently return empty data** — `app/api.py:1187-1212`. `AsyncRedisClient.connect()` never called; all methods return `None`.

### MEDIUM (5)
1. **Redis URL (with possible credentials) logged** — `app/distributed/redis_client.py:41`
2. **Env vars including REDIS_URL printed at startup** — `app/main.py:101-103`
3. **Fire-and-forget create_task in DistributedScheduler** — `distributed_scheduler.py:66-67`. Tasks not tracked, can't be cancelled.
4. **Worker poll_loop has no `_running` flag** — `app/worker.py:75-83`. Only exits via CancelledError.
5. **stop_heartbeat doesn't interrupt active sleep** — `worker_registry.py:94`. Delayed shutdown by up to heartbeat_interval.

### LOW (4)
1. **Cache key logs user messages (PII)** — `app/api.py:376`
2. **stop_heartbeat doesn't call unregister()** — `worker_registry.py:96-97`
3. **Event bus exception handler doesn't catch BaseException** — `event_bus.py:97-98` (intentional, but worth noting)
4. **DistributedScheduler loops can't be interrupted mid-sleep** — `distributed_scheduler.py:116,142`

### No Issues Found In
- ✅ Unsafe deserialization (eval, exec, pickle) — none used
- ✅ Command injection — no vector found
- ✅ Path traversal — all file paths hardcoded
- ✅ Input validation on new runtime endpoints — all are parameterless GET
- ✅ `distributed_queue.py` shutdown — stateless, no cleanup needed
- ✅ `event_bus.py stop_listener` — proper cleanup of pubsub and listener task
