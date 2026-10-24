"""Flask blueprints for the API.

``app.py`` stays the composition root: it creates the app, registers the error
handlers and calls :func:`register_blueprints`. Each module below owns one
group of routes and the helpers only those routes need.
"""

from .system import bp as system_bp


def register_blueprints(app):
    app.register_blueprint(system_bp)
