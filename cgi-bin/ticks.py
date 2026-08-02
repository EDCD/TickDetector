#!/usr/bin/env python3
"""
CGI script for /api/ticks endpoint.

Returns tick history as a JSON array of {"TIME": "..."} objects,
filtered by optional start and end query parameters.

Query params:
    start - date in YYYY-MM-DD format (default: 2014-12-16)
    end   - date in YYYY-MM-DD format (default: today)

Example:
    /api/ticks?start=2024-01-01&end=2024-06-30
"""

import cgi
import json
import os
import sys
from datetime import date

import mysql.connector

# Database configuration (same env vars as the main service)
DB_HOST = os.environ.get("TICK_DB_HOST", "localhost")
DB_PORT = int(os.environ.get("TICK_DB_PORT", "3306"))
DB_USER = os.environ.get("TICK_DB_USER", "tick_detector")
DB_PASS = os.environ.get("TICK_DB_PASS", "")
DB_NAME = os.environ.get("TICK_DB_NAME", "tick_detector")


def main():
    # Parse query parameters
    params = cgi.FieldStorage()
    start = params.getvalue("start", "2014-12-16")
    end = params.getvalue("end", date.today().isoformat())

    # Basic input validation
    try:
        start_date = date.fromisoformat(start)
        end_date = date.fromisoformat(end)
    except ValueError:
        print("Content-Type: application/json")
        print("Access-Control-Allow-Origin: *")
        print()
        print(json.dumps({"error": "Invalid date format. Use YYYY-MM-DD."}))
        return

    # Query the database
    try:
        conn = mysql.connector.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASS,
            database=DB_NAME,
        )
        cursor = conn.cursor()
        cursor.execute(
            "SELECT `time` FROM ticks WHERE DATE(`time`) BETWEEN %s AND %s ORDER BY `time` ASC",
            (start_date.isoformat(), end_date.isoformat()),
        )
        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        ticks = [{"TIME": row[0]} for row in rows]
    except mysql.connector.Error as e:
        print("Content-Type: application/json")
        print("Access-Control-Allow-Origin: *")
        print()
        print(json.dumps({"error": "Database unavailable"}))
        sys.exit(0)

    # Output response
    print("Content-Type: application/json")
    print("Access-Control-Allow-Origin: *")
    print()
    print(json.dumps(ticks))


if __name__ == "__main__":
    main()
