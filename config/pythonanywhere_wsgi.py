"""
PythonAnywhere WSGI helper.

On PythonAnywhere, open the Web tab → WSGI configuration file and
replace its contents with something like this (fix the paths):

    import os
    import sys

    path = "/home/YOURUSERNAME/ai"
    if path not in sys.path:
        sys.path.insert(0, path)

    os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
    from django.core.wsgi import get_wsgi_application
    application = get_wsgi_application()

This module is not used by `runserver`. It exists as a copy-paste reference.
"""
