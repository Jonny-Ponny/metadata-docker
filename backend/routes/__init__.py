"""Flask blueprints for the API.

``app.py`` stays the composition root: it creates the app, registers the error
handlers and calls :func:`register_blueprints`. Each module below owns one
group of routes and the helpers only those routes need.
"""

from .addons import bp as addons_bp
from .downloads import bp as downloads_bp
from .logs import bp as logs_bp
from .system import bp as system_bp
from .tags import bp as tags_bp
from .text import bp as text_bp


def register_blueprints(app):
    app.register_blueprint(system_bp)
    app.register_blueprint(addons_bp)
    app.register_blueprint(downloads_bp)
    app.register_blueprint(tags_bp)
    app.register_blueprint(logs_bp)
    app.register_blueprint(text_bp)
