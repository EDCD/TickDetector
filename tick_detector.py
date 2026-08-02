#!/usr/bin/env python3
"""
Elite Dangerous BGS Tick Detector

A single Python service that:
1. Connects to the EDDN relay and listens for journal messages with faction
   influence data.
2. Stores influence change observations in MySQL RDS (minimal working data).
3. Periodically runs DBSCAN clustering on influence change timestamps to
   detect the BGS tick.
4. On tick detection, updates static JSON files served by Apache and records
   the tick in the database.

Configuration is via environment variables (see below).
"""

import json
import logging
import os
import signal
import sys
import time
import zlib
from datetime import datetime, timezone, timedelta

import mysql.connector
import zmq

# ---------------------------------------------------------------------------
# Configuration (environment variables)
# ---------------------------------------------------------------------------
DB_HOST = os.environ.get("TICK_DB_HOST", "localhost")
DB_PORT = int(os.environ.get("TICK_DB_PORT", "3306"))
DB_USER = os.environ.get("TICK_DB_USER", "tick_detector")
DB_PASS = os.environ.get("TICK_DB_PASS", "")
DB_NAME = os.environ.get("TICK_DB_NAME", "tick_detector")

# Path to the web root where static files are served by Apache
WEB_ROOT = os.environ.get("TICK_WEB_ROOT", "/var/www/tick.edcd.io")

# EDDN relay address
EDDN_RELAY = os.environ.get("TICK_EDDN_RELAY", "tcp://eddn.edcd.io:9500")

# Detection parameters (matching the original defaults)
FRESHNESS = int(os.environ.get("TICK_FRESHNESS", "14400"))  # seconds
THRESHOLD = int(os.environ.get("TICK_THRESHOLD", "5"))       # min cluster size
DELTA = int(os.environ.get("TICK_DELTA", "7500"))            # DBSCAN epsilon (seconds)

# How often to run tick detection (seconds)
DETECT_INTERVAL = int(os.environ.get("TICK_DETECT_INTERVAL", "60"))

# Max age of EDDN messages to accept (seconds)
MAX_MESSAGE_AGE = 6000

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("tick_detector")

# ---------------------------------------------------------------------------
# Globals
# ---------------------------------------------------------------------------
running = True


def signal_handler(signum, frame):
    global running
    log.info(f"Received signal {signum}, shutting down...")
    running = False


signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGHUP, signal_handler)


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------
def get_db_connection():
    """Create a new MySQL connection."""
    return mysql.connector.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASS,
        database=DB_NAME,
        autocommit=True,
    )


def ensure_schema(conn):
    """Create tables if they don't exist."""
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS `ticks` (
            `time` VARCHAR(30) NOT NULL,
            PRIMARY KEY (`time`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS `influence` (
            `id` BIGINT AUTO_INCREMENT PRIMARY KEY,
            `system_id` BIGINT NOT NULL,
            `faction` VARCHAR(256) NOT NULL,
            `influence` DOUBLE NOT NULL,
            `first_seen` DATETIME NOT NULL,
            `last_seen` DATETIME NOT NULL,
            `count` INT NOT NULL DEFAULT 1,
            `delta` INT DEFAULT NULL,
            INDEX `idx_system_faction` (`system_id`, `faction`),
            INDEX `idx_first_seen` (`first_seen`),
            INDEX `idx_delta` (`delta`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cursor.close()


# ---------------------------------------------------------------------------
# EDDN message processing
# ---------------------------------------------------------------------------
def process_message(msg_bytes, conn):
    """Process a single EDDN message. Returns True if data was stored."""
    try:
        raw = zlib.decompress(msg_bytes)
        parsed = json.loads(raw)
    except (zlib.error, json.JSONDecodeError):
        return False

    # Ban EDDiscovery due to bad data issues
    if parsed.get("header", {}).get("softwareName") == "EDDiscovery":
        return False

    # Only process journal/1 schema
    if parsed.get("$schemaRef") != "https://eddn.edcd.io/schemas/journal/1":
        return False

    message = parsed.get("message", {})
    header = parsed.get("header", {})

    # Only accept game version 4+
    try:
        if float(header.get("gameversion", "0").split(".")[0]) < 4:
            return False
    except (ValueError, TypeError):
        pass

    system_id = message.get("SystemAddress")
    factions = message.get("Factions")
    timestamp_str = message.get("timestamp")
    gw_timestamp_str = header.get("gatewayTimestamp")

    if not all([system_id, factions, timestamp_str, gw_timestamp_str]):
        return False

    # Check message freshness
    try:
        msg_time = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        gw_time = datetime.fromisoformat(gw_timestamp_str.replace("Z", "+00:00"))
        age_seconds = (gw_time - msg_time).total_seconds()
    except (ValueError, TypeError):
        return False

    if abs(age_seconds) > MAX_MESSAGE_AGE:
        return False

    # Store influence data
    cursor = conn.cursor()
    stored = False
    for faction_data in factions:
        faction_name = faction_data.get("Name")
        influence_val = faction_data.get("Influence", 0)

        if not faction_name or influence_val <= 0:
            continue

        set_influence(cursor, system_id, faction_name, influence_val, msg_time)
        stored = True

    cursor.close()
    return stored


def set_influence(cursor, system_id, faction, influence, msg_time):
    """Store or update influence data, matching the original algorithm."""
    msg_time_str = msg_time.strftime("%Y-%m-%d %H:%M:%S")

    # Check if we already have this exact influence value for this system/faction
    cursor.execute("""
        SELECT id, first_seen, last_seen
        FROM influence
        WHERE system_id = %s AND faction = %s AND influence = %s
        ORDER BY first_seen DESC
        LIMIT 1
    """, (system_id, faction, influence))

    row = cursor.fetchone()

    if row:
        row_id, first_seen, last_seen = row
        # If this message is older than last_seen, extend the observation window
        if msg_time_str < str(first_seen):
            cursor.execute("""
                UPDATE influence SET first_seen = %s, count = count + 1, delta = NULL
                WHERE id = %s
            """, (msg_time_str, row_id))
        elif msg_time_str > str(last_seen):
            cursor.execute("""
                UPDATE influence SET last_seen = %s, count = count + 1, delta = NULL
                WHERE id = %s
            """, (msg_time_str, row_id))
        else:
            cursor.execute("UPDATE influence SET count = count + 1 WHERE id = %s", (row_id,))
        update_delta(cursor, system_id, faction)
    else:
        # New influence value for this system/faction
        cursor.execute("""
            INSERT INTO influence (system_id, faction, influence, first_seen, last_seen, count)
            VALUES (%s, %s, %s, %s, %s, 1)
        """, (system_id, faction, influence, msg_time_str, msg_time_str))
        update_delta(cursor, system_id, faction)


def update_delta(cursor, system_id, faction):
    """Calculate time deltas between consecutive influence observations."""
    cursor.execute("""
        SELECT id, first_seen, last_seen
        FROM influence
        WHERE system_id = %s AND faction = %s AND influence > 0
        ORDER BY first_seen DESC
    """, (system_id, faction))

    rows = cursor.fetchall()
    if len(rows) > 1:
        for j in range(len(rows) - 1):
            newer_first_seen = rows[j][1]
            older_last_seen = rows[j + 1][2]
            delta_seconds = int((newer_first_seen - older_last_seen).total_seconds())
            cursor.execute("UPDATE influence SET delta = %s WHERE id = %s", (delta_seconds, rows[j][0]))


# ---------------------------------------------------------------------------
# DBSCAN tick detection
# ---------------------------------------------------------------------------
def dbscan_1d(data, eps, min_pts):
    """
    Simple 1D DBSCAN implementation.
    data: list of numeric values (unix timestamps)
    eps: maximum distance between points in a cluster
    min_pts: minimum number of points to form a cluster
    Returns: list of clusters, where each cluster is a list of data values
    """
    if not data:
        return []

    sorted_data = sorted(enumerate(data), key=lambda x: x[1])
    n = len(sorted_data)
    visited = [False] * n
    clusters = []

    for i in range(n):
        if visited[i]:
            continue

        # Find all neighbours within eps
        neighbours = []
        for j in range(n):
            if abs(sorted_data[i][1] - sorted_data[j][1]) <= eps:
                neighbours.append(j)

        if len(neighbours) < min_pts:
            continue

        # Expand cluster
        cluster = set(neighbours)
        visited[i] = True
        expand = list(neighbours)

        while expand:
            point = expand.pop()
            if visited[point]:
                continue
            visited[point] = True

            point_neighbours = []
            for j in range(n):
                if abs(sorted_data[point][1] - sorted_data[j][1]) <= eps:
                    point_neighbours.append(j)

            if len(point_neighbours) >= min_pts:
                for pn in point_neighbours:
                    if pn not in cluster:
                        cluster.add(pn)
                        expand.append(pn)

        cluster_values = sorted([sorted_data[idx][1] for idx in cluster])
        clusters.append(cluster_values)

    # Sort clusters by their earliest timestamp
    clusters.sort(key=lambda c: c[0])
    return clusters


def detect_tick(conn):
    """Run tick detection. Returns new tick timestamp string if detected, else None."""
    cursor = conn.cursor()

    # Get the last known tick
    cursor.execute("SELECT `time` FROM ticks ORDER BY `time` DESC LIMIT 1")
    row = cursor.fetchone()

    if row:
        last_tick_str = row[0]
        # Parse the ISO timestamp
        try:
            last_tick = datetime.fromisoformat(last_tick_str)
        except ValueError:
            last_tick = datetime.now(timezone.utc) - timedelta(days=30)
    else:
        last_tick = datetime.now(timezone.utc) - timedelta(days=30)

    start_str = last_tick.strftime("%Y-%m-%d %H:%M:%S")

    # Query influence changes since last tick with valid deltas
    cursor.execute("""
        SELECT DISTINCT system_id, first_seen, delta
        FROM influence
        WHERE first_seen >= %s
          AND influence > 0
          AND delta IS NOT NULL
          AND delta <= %s
    """, (start_str, FRESHNESS))

    rows = cursor.fetchall()
    cursor.close()

    if not rows:
        return None

    # Convert first_seen timestamps to unix epoch for clustering
    data = []
    for _, first_seen, _ in rows:
        epoch = first_seen.timestamp()
        data.append(epoch)

    if not data:
        return None

    # Run DBSCAN
    clusters = dbscan_1d(data, DELTA, THRESHOLD)

    new_ticks = []
    for i, cluster in enumerate(clusters):
        if i >= 1:  # Skip the first cluster (it's the "current state" before tick)
            tick_time = datetime.fromtimestamp(cluster[0], tz=timezone.utc)
            new_ticks.append(tick_time)

    return new_ticks


def save_tick(conn, tick_time):
    """Save a detected tick to the database."""
    tick_str = tick_time.strftime("%Y-%m-%dT%H:%M:%S+00:00")
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT IGNORE INTO ticks (`time`) VALUES (%s)", (tick_str,))
        cursor.close()
        return tick_str
    except mysql.connector.Error:
        cursor.close()
        return None


def purge_old_influence(conn):
    """Remove influence data older than 7 days to keep the table lean."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM influence WHERE last_seen < %s", (cutoff,))
    deleted = cursor.rowcount
    cursor.close()
    if deleted > 0:
        log.info(f"Purged {deleted} old influence records")


# ---------------------------------------------------------------------------
# Static file publishing
# ---------------------------------------------------------------------------
def publish_tick(tick_str):
    """Update the static files served by Apache."""
    api_dir = os.path.join(WEB_ROOT, "api")
    os.makedirs(api_dir, exist_ok=True)

    # Update /api/tick (just the timestamp in quotes)
    tick_file = os.path.join(api_dir, "tick")
    with open(tick_file, "w") as f:
        f.write(json.dumps(tick_str))

    # Update index.html
    update_index_html(tick_str)

    log.info(f"Published tick: {tick_str}")


def update_index_html(tick_str):
    """Regenerate the index.html with the latest tick time."""
    html_path = os.path.join(WEB_ROOT, "index.html")
    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Elite Dangerous BGS Tick Detector</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: #1a1a2e;
            color: #e0e0e0;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            margin: 0;
        }}
        .container {{
            text-align: center;
            padding: 2rem;
        }}
        h1 {{
            color: #f39c12;
            margin-bottom: 0.5rem;
        }}
        .tick-time {{
            font-size: 2rem;
            color: #3498db;
            margin: 1rem 0;
            font-family: monospace;
        }}
        .info {{
            color: #888;
            font-size: 0.9rem;
        }}
        a {{
            color: #3498db;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Elite Dangerous BGS Tick Detector</h1>
        <p class="info">Last detected tick:</p>
        <div class="tick-time" id="tick">{tick_str}</div>
        <p class="info">
            API: <a href="/api/tick">/api/tick</a> |
            <a href="/api/ticks">/api/ticks</a>
        </p>
        <p class="info">Auto-refreshes every 60 seconds.</p>
    </div>
    <script>
        // Poll for updates every 60 seconds
        setInterval(async () => {{
            try {{
                const resp = await fetch('/api/tick');
                const tick = await resp.json();
                const el = document.getElementById('tick');
                if (tick !== el.textContent) {{
                    el.textContent = tick;
                    document.title = 'NEW TICK - Elite Dangerous BGS Tick Detector';
                    setTimeout(() => {{ document.title = 'Elite Dangerous BGS Tick Detector'; }}, 30000);
                }}
            }} catch (e) {{}}
        }}, 60000);
    </script>
</body>
</html>
"""
    with open(html_path, "w") as f:
        f.write(html_content)


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
def main():
    log.info("Starting Elite Dangerous BGS Tick Detector")
    log.info(f"EDDN relay: {EDDN_RELAY}")
    log.info(f"MySQL: {DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME}")
    log.info(f"Web root: {WEB_ROOT}")
    log.info(f"Detection params: freshness={FRESHNESS}, threshold={THRESHOLD}, delta={DELTA}")

    # Connect to MySQL and ensure schema
    conn = get_db_connection()
    ensure_schema(conn)

    # Publish current latest tick on startup
    cursor = conn.cursor()
    cursor.execute("SELECT `time` FROM ticks ORDER BY `time` DESC LIMIT 1")
    row = cursor.fetchone()
    cursor.close()
    if row:
        publish_tick(row[0])

    # Set up ZeroMQ subscriber
    ctx = zmq.Context()
    sock = ctx.socket(zmq.SUB)
    sock.setsockopt(zmq.RCVHWM, 50)
    sock.setsockopt(zmq.SUBSCRIBE, b"")
    sock.setsockopt(zmq.RCVTIMEO, 5000)  # 5 second timeout on recv
    sock.connect(EDDN_RELAY)
    log.info("Connected to EDDN relay")

    last_detect_time = 0
    last_purge_time = 0
    messages_processed = 0

    while running:
        # Receive EDDN messages (non-blocking with timeout)
        try:
            msg = sock.recv()
            try:
                process_message(msg, conn)
                messages_processed += 1
            except mysql.connector.Error as e:
                log.warning(f"Database error processing message: {e}")
                # Reconnect
                try:
                    conn.close()
                except Exception:
                    pass
                conn = get_db_connection()
        except zmq.Again:
            # Timeout - no message received, that's fine
            pass
        except zmq.ZMQError as e:
            if not running:
                break
            log.error(f"ZMQ error: {e}")
            time.sleep(5)
            continue

        # Run tick detection periodically
        now = time.time()
        if now - last_detect_time >= DETECT_INTERVAL:
            last_detect_time = now
            try:
                new_ticks = detect_tick(conn)
                if new_ticks:
                    for tick_time in new_ticks:
                        tick_str = save_tick(conn, tick_time)
                        if tick_str:
                            log.info(f"New tick detected: {tick_str}")
                            publish_tick(tick_str)
            except mysql.connector.Error as e:
                log.error(f"Database error during tick detection: {e}")
                try:
                    conn.close()
                except Exception:
                    pass
                conn = get_db_connection()

            if messages_processed > 0:
                log.debug(f"Processed {messages_processed} messages since last check")
                messages_processed = 0

        # Purge old influence data every hour
        if now - last_purge_time >= 3600:
            last_purge_time = now
            try:
                purge_old_influence(conn)
            except mysql.connector.Error as e:
                log.warning(f"Error purging old data: {e}")

    # Cleanup
    log.info("Shutting down...")
    sock.close()
    ctx.term()
    conn.close()
    log.info("Goodbye.")


if __name__ == "__main__":
    main()
