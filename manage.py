#!/usr/bin/env python
"""Django command-line entry point for Chan Humanized AI."""

import os
import sys


def main():
    """Run administrative tasks (migrate, runserver, test, etc.)."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Django is not installed. Activate .venv and pip install -r requirements.txt"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
