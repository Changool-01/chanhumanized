"""
PythonAnywhere WSGI helper for changool.pythonanywhere.com.

Copy the contents of this file into the PythonAnywhere Web tab →
WSGI configuration file (usually /var/www/changool_pythonanywhere_com_wsgi.py).
"""

import os
import sys

path = "/home/changool/chanhumanized"
if path not in sys.path:
    sys.path.insert(0, path)

os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
