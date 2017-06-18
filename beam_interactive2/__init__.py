from .connection import *
from .encoding import *
from .scene import *
from .state import *
from .keycodes import keycode
from ._util import until_event
from .discovery import *

async def create(config):
    """Helper function for the creation of connections."""
    handle = Auth(config)
    handle.authenticate()
    connection = await State.connect(
            authorization = "Bearer {}".format(handle.oauth_info["access_token"]),
            project_version_id = config.version_id)
    await connection.sync_time()
    return connection