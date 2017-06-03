from .connection import *
from .encoding import *
from .scene import *
from .state import *
from .keycodes import keycode
from ._util import until_event
from .discovery import *

def create(config):
    """Helper function for the creation of connections."""
    handle = Auth(config)
    handle.authenticate()
    d = Discovery()
    connection = Connection(
            address = Discovery.find(d),
            authorization = "Bearer {}".format(handle.oauth_info["access_token"]),
            project_version_id = config.version_id)

    return connection