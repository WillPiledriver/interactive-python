from .errors import *
from requests import Session, codes
from os.path import isfile
import time
import json
import asyncio
import websockets
import collections

from .log import logger
from .encoding import Encoding, TextEncoding


class Call:
    def __init__(self, connection, payload):
        """
        A Call is an incoming message from the Interactive service.
        :param connection: the connection
        :param payload:
        """
        self._connection = connection
        self._payload = payload

    @property
    def name(self):
        """
        :return: The name of the method being called.
        :rtype: str
        """
        return self._payload['method']

    @property
    def data(self):
        """
        :return: The payload of the method being called.
        :rtype: dict
        """
        return self._payload['params']

    def reply_error(self, result):
        """
        Submits a successful reply for the call.
        :param result: The result to send to tetrisd
        """
        self._connection.reply(self._id, result=result)

    def reply_error(self, error):
        """
        Submits an errorful reply for the call.
        :param error: The error to send to tetrisd
        """
        self._connection.reply(self._id, error=error)


class Connection:
    """
    The Connection is used to connect to the Interactive server. It connects
    to a provided socket address and provides an interface for making RPC
    calls. Example usage::
        connection = Connection(
            address=get_interactive_address(),
            authorization="Bearer {}".format(my_oauth_token),
            interactive_version_id=1234)
    """

    def __init__(self, address=None, authorization=None,
                 project_version_id=None, project_sharecode=None,
                 extra_headers={}, loop=asyncio.get_event_loop(), socket=None,
                 protocol_version="2.0"):

        if authorization is not None:
            extra_headers['Authorization'] = authorization
        if project_version_id is not None:
            extra_headers['X-Interactive-Version'] = project_version_id
        if project_sharecode is not None:
            extra_headers['X-Interactive-Sharecode'] = project_sharecode
        extra_headers['X-Protocol-Version'] = protocol_version

        self._socket_or_connector = socket or websockets.client.connect(
            address, loop=loop, extra_headers=extra_headers)
        self._socket = None

        self._loop = loop
        self._encoding = TextEncoding()
        self._awaiting_replies = {}
        self._call_counter = 0

        self._recv_queue = collections.deque()
        self._recv_await = None
        self._recv_task = None

    async def connect(self):
        """
        Connects to the Interactive server, waiting until the connection
        if fully established before returning. Can throw a ClosedError
        if something, such as authentication, fails.
        """

        if not hasattr(self._socket_or_connector, '__await__'):
            self._socket = self._socket_or_connector
        else:
            self._socket = await self._socket_or_connector

        # await a hello event
        while True:
            packet = await self._read_single()
            if packet['type'] == 'method' and packet['method'] == 'hello':
                break

            self._recv_queue.append(packet)

        self._recv_task = asyncio.ensure_future(self._read(), loop=self._loop)

    def _fallback_to_plain_text(self):
        if isinstance(self._encoding, TextEncoding):
            return  # we're already falling back

        self._encoding = TextEncoding()
        asyncio.ensure_future(
            self.set_compression(TextEncoding()), loop=self._loop)

    def _decode(self, data):
        """
        Converts the packet data to a string,
        decompressing it if necessary. Always returns a string.
        """
        if isinstance(data, str):
            return data

        try:
            return self._encoding.decode(data)
        except Exception as e:
            self._fallback_to_plain_text()
            logger.info("error decoding Interactive message, falling back to"
                        "plain text", extra=e)

    def _encode(self, data):
        """
        Converts the packet data to a string or byte array,
        compressing it if necessary.
        """
        try:
            return self._encoding.encode(data)
        except Exception as e:
            self._fallback_to_plain_text()
            logger.warn("error encoding Interactive message, falling back to"
                        "plain text", extra=e)

        return data

    def _handle_recv(self, data):
        """
        Handles a single received packet from the Interactive service.
        """

        if data['type'] == 'reply':
            if data['id'] in self._awaiting_replies:
                self._awaiting_replies[data['id']]. \
                    set_result(data['result'])
                del self._awaiting_replies[data['id']]

            return

        self._recv_queue.append(Call(self, data))
        if self._recv_await is not None:
            self._recv_await.set_result(True)
            self._recv_await = None

    def _send(self, payload):
        """
        Encodes and sends a dict payload.
        """
        self._socket.send(self._encode(json.dumps(payload)))

    async def _read_single(self):
        """
        Reads a single event off the websocket.
        """
        try:
            raw_data = await self._socket.recv()
        except (asyncio.CancelledError, websockets.ConnectionClosed) as e:
            if self._recv_await is None:
                self._recv_await = asyncio.Future(loop=self._loop)
            self._recv_await.set_result(False)
            raise e

        return json.loads(self._decode(raw_data))

    async def _read(self):
        """
        Endless read loop that runs until the socket is closed.
        """
        while True:
            try:
                data = await self._read_single()
            except (asyncio.CancelledError, websockets.ConnectionClosed):
                break  # will already be handled
            except Exception as e:
                logger.error("error in interactive read loop", extra=e)
                break

            if isinstance(data, list):
                for item in data:
                    self._handle_recv(item)
            else:
                self._handle_recv(data)

    async def set_compression(self, scheme):
        """Updates the compression used on the websocket this should be
        called with an instance of the Encoding class, for example::
            connection.set_compression(GzipEncoding())
        You can, optionally, await on the resolution of method, though
        doing so it not at all required. Returns True if the server agreed
        on and executed the switch.

        :param scheme: The compression scheme to use
        :type scheme: Encoding
        :return: Whether the upgrade was successful
        :rtype: bool
        """
        result = await self.call("setCompression", {'scheme': [scheme.name()]})
        if result['scheme'] == scheme.name():
            self._encoding = scheme
            return True

        return False

    def reply(self, call_id, result=None, error=None):
        """
        Sends a reply for a packet id. Either the result or error should
        be fulfilled.

        :param call_id: The ID of the call being replied to.
        :type call_id: int
        :param result: The successful result of the call.
        :param error: The errorful result of the call.
        """
        packet = {'type': 'reply', 'id': call_id}
        if result is not None:
            packet['result'] = result
        if error is not None:
            packet['error'] = result

        self._send(packet)

    async def call(self, method, params, discard=False, timeout=10):
        """
        Sends a method call to the interactive socket. If discard
        is false, we'll wait for a response before returning, up to the
        timeout duration in seconds, at which point it raises an
        asyncio.TimeoutError. If the timeout is None, we'll wait forever.

        :param method: Method name to call
        :type method: str
        :param params: Parameters to insert into the method, generally a dict.
        :param discard: ``True`` to not request any reply to the method.
        :type discard: bool
        :param timeout: Call timeout duration, in seconds.
        :type timeout: int
        :return: The call response, or None if it was discarded.
        :raises: asyncio.TimeoutError
        """

        packet = {
            'type': 'method',
            'method': method,
            'params': params,
            'id': self._call_counter,
        }

        if discard:
            packet['discard'] = True

        self._call_counter += 1
        self._send(packet)

        if discard:
            return None

        future = asyncio.Future(loop=self._loop)
        self._awaiting_replies[packet['id']] = future

        try:
            return await asyncio.wait_for(future, timeout, loop=self._loop)
        except Exception as e:
            del self._awaiting_replies[packet['id']]
            raise e

    def get_packet(self):
        """
        Synchronously reads a packet from the connection. Returns None if
        there are no more packets in the queue. Example::
            while await connection.has_packet():
                dispatch_call(connection.get_packet())

        :rtype: Call
        """
        if len(self._recv_queue) > 0:
            return self._recv_queue.popleft()

        return None

    async def has_packet(self):
        """
        Blocks until a packet is read. Returns true if a packet is then
        available, or false if the connection is subsequently closed. Example::
            while await connection.has_packet():
                dispatch_call(connection.get_packet())

        :rtype: bool
        """
        if len(self._recv_queue) > 0:
            return

        if self._recv_await is None:
            self._recv_await = asyncio.Future(loop=self._loop)

        return await self._recv_await

    async def close(self):
        """Closes the socket connection gracefully"""
        self._recv_task.cancel()
        await self._socket.close()


class Auth:

    def __init__(self, config=None, client_id=None,
                 auth_conf_filename=None, client_secret=None):
        super().__init__()
        if config == None:
            self.client_id = client_id
            self.auth_conf_filename = auth_conf_filename
            self.client_secret = client_secret
        else:
            self.client_id = config.client_id
            self.auth_conf_filename = config.auth_conf_filename
            self.client_secret = config.client_secret

        self.url_base = "https://mixer.com/api/v1/"

        self.oauth_info = self.read_oauth()


    def read_oauth(self):
        """
        Reads the authorization keys from the authorization config file defined in config

        :return:
        Returns dict
        """
        if isfile(self.auth_conf_filename):
            try:
                with open(self.auth_conf_filename, "r") as f:
                    return json.loads(f.read())
            except Exception as e:
                print("Something terribly wrong has happened when trying to read auth file. ERROR TYPE: {}\nResetting Authorization configuration.".format(type(e)))
                return None
        else:
            return None

    def write_oauth(self):
        """
        Writes authorization keys (json) to the authorization config file.

        """
        try:
            with open(self.auth_conf_filename, "w") as f:
                f.write(json.dumps(self.oauth_info))
        except Exception as e:
            print(
                "Something terribly wrong has happened when trying to write the auth file. ERROR TYPE: {}".format(type(e)))
            raise e

    def _join(self, endpoint):
        """
        Generates URL for the API.

        :param endpoint:
        The endpoint URI

        :return:
        Returns the full URL.
        """
        return self.url_base + endpoint

    def authenticate(self):
        """
        This should be called before your main code. This method authorizes the client via shortcode if the
        client doesn't already have the correct auth keys.  Uses the refresh token to generate a new auth key
        when called.

        OAuth tokens are held in self.oauth_info.
        """
        session = Session()

        if self.oauth_info is None:
            d = {
                "client_id": self.client_id,
                "scope": "interactive:robot:self",
                "client_secret":  self.client_secret
            }

            response = session.post(self._join("oauth/shortcode"), data=d)
            if response.status_code == 200:
                response = response.json()
                shortcode = response["code"]
                handle = response["handle"]
                print("Shortcode is {} please enter this code at https://mixer.com/go".format(shortcode))

                response = session.get(self._join("oauth/shortcode/check/{}".format(handle)))
                while(response.status_code != 404):
                    if response.status_code == 200:
                        break
                    elif response.status_code == 403:
                        raise UnknownError(response.content)
                    else:
                        time.sleep(2.5)
                    response = session.get(self._join("oauth/shortcode/check/{}".format(handle)))

                if response.status_code == 404:
                    print("Shortcode token expired. Try again.")
                    raise UnknownError("Time expired.")

                code = response.json()["code"]

                d = {
                    "grant_type": "authorization_code",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "code": code
                }
                response = session.post(self._join("oauth/token"), data=d)

                if response.status_code == 200:
                    print("Success!")
                    self.oauth_info = response.json()
                    self.write_oauth()
                else:
                    print("Authorization failed when grabbing token. STATUS CODE: " + str(response.status_code))
                    raise RequestError(response.json())
            else:
                print("Authorization failed during shortcode generation. STATUS CODE: " + str(response.status_code))
                raise RequestError(response.json())
        else:
            d = {
                "grant_type": "refresh_token",
                "refresh_token": self.oauth_info["refresh_token"],
                "client_id": self.client_id,
                "client_secret": self.client_secret
            }

            response = session.post(self._join("oauth/token"), data=d)

            if response.status_code == 200:
                print("Refresh token used successfully and access token has been updated.")
                self.oauth_info = response.json()
                self.write_oauth()
            else:
                print("Refresh token failed somehow. Resetting authorization config.")
                self.oauth_info = None
                self.authenticate()