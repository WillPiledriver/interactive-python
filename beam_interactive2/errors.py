class RequestError(Exception):
	def __init__(self, response):
		self.response = response


class NotAuthenticatedError(RequestError):
	"""Failed to connect to the Beam server."""


class UnknownError(RequestError):
	pass


class DiscoveryError(Exception):
    """Raised if some error occurs during service discovery
    that we didn't anticipate.
    """
    pass


class NoServersAvailableError(Exception):
    """Raised if Beam reports that no servers are available."""
    pass