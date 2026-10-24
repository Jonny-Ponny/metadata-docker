"""Log endpoints: read the application log and clear it."""

import re

from flask import Blueprint, jsonify, request

from auth import token_required
from errors import _server_error
from logger_config import LOG_DIR, log_info

bp = Blueprint('logs', __name__)


@bp.route('/api/logs', methods=['GET'])
@token_required
def get_logs():
    """Get log entries with filtering options"""
    try:
        # Get query parameters
        lines = request.args.get('lines', default=100, type=int)
        lines = max(1, min(lines, 1000))
        level = request.args.get('level', default=None, type=str)
        search = request.args.get('search', default=None, type=str)

        log_file = LOG_DIR / "app.log"

        if not log_file.exists():
            return jsonify({
                "logs": [],
                "total": 0,
                "message": "No logs found"
            })

        # Read log file
        with open(log_file, 'r', encoding='utf-8') as f:
            all_logs = f.readlines()

        # Filter by level if specified
        if level:
            # Match the pattern [LEVEL] in the log
            level_pattern = f"[{level.upper()}]"
            all_logs = [log for log in all_logs if level_pattern in log]

        # Filter by search term if specified
        if search:
            all_logs = [log for log in all_logs if search.lower() in log.lower()]

        # Get last N lines (most recent)
        recent_logs = all_logs[-lines:]

        # Parse logs into structured format
        parsed_logs = []
        for log in recent_logs:
            # Parse timestamp, level, and message from format: [2024-01-01 12:34:56] [INFO] message
            log_line = log.strip()

            # Try to match the pattern [timestamp] [level] message
            match = re.match(r'\[(.*?)\] \[(.*?)\] (.*)', log_line)

            if match:
                parsed_logs.append({
                    'timestamp': match.group(1),
                    'level': match.group(2),
                    'message': match.group(3)
                })
            else:
                parsed_logs.append({'raw': log_line})

        return jsonify({
            "logs": parsed_logs,
            "total": len(all_logs),
            "displayed": len(recent_logs),
            "filters": {
                "level": level,
                "search": search
            }
        })

    except Exception as e:
        return _server_error(e, 'Could not read the logs.')


@bp.route('/api/logs/clear', methods=['POST'])
@token_required
def clear_logs():
    """Clear all logs"""
    try:
        log_file = LOG_DIR / "app.log"
        if log_file.exists():
            log_file.write_text("")
            log_info("Logs cleared by user")
        return jsonify({"message": "Logs cleared successfully"})
    except Exception as e:
        return _server_error(e, 'Could not clear the logs.')
