"""Django project package for Chan Humanized AI."""

# PyMySQL presents itself as MySQLdb so Django's MySQL backend works
# without compiling mysqlclient (easier on macOS and PythonAnywhere).
import pymysql

pymysql.install_as_MySQLdb()
