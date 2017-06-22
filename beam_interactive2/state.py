import collections
import asyncio
import time
from pyee import EventEmitter

from .connection import Call, Connection
from .discovery import Discovery
from .scene import Scene


class State(EventEmitter):
    """State is the state container for a single interactive session.
    It should usually be created via the static ``connect`` method::

        connection = State.connect(
            project_version_id=my_version_id,
            authorization="Bearer " + oauth_token)

    The state can work in two modes for handling delivery of events and updates.
    You can use `pump()` calls synchronously within your game loop to apply
    updates that have been queued. Alternately, you can call `pump_async()` to
    signal to that state that you want updates delivered asynchronously, as soon
    as they come in. For example:

        # Async delivery. `giveInput` is emitted as soon as any input comes in.
        state.on('giveInput', lambda call: do_the_thing(call))
        state.pump_async()

        # Sync delivery. `giveInput` is emitted only during calls to pump()
        state.on('giveInput', lambda call: do_the_thing(call))
        while True:
            my_game_loop.tick()
            state.pump()

            # You can also read queues of changes from pump(), if you prefer
            # to dispatch changes manually:
            # for call in pump(): ...

    In both modes, all incoming call are emitted as events on the State
    instance.

    :param connection: The websocket connection to interactive.
    :type connection: Connection
    """

    def __init__(self, connection):
        super(State, self).__init__()
        self._scenes = {}
        self._connection = connection
        self._enable_event_queue = True
        self._event_queue = collections.deque()
        self.participants = {}
        self.time_offset = 0
        self._controls = {}
        self.on('onParticipantJoin', self._on_participant_join)
        self.on('onParticipantLeave', self._on_participant_leave)
        self.on("onParticipantUpdate", self._on_participant_update)
        self.on('onControlUpdate', self._on_control_update)
        #self.on('giveInput', self._give_input)

    @property
    def scenes(self):
        """
        :rtype: (dict of str: Scene)
        """
        return self._scenes

    def calc_time(self):
        """
        Calculates the servers clock as a milliseconds UTC unix timestamp.
        :return: int milliseconds
        """
        return int(time.time() * 1000 + self.time_offset)


    async def sync_time(self):
        """
        Synchronizes server time with local time by storing the difference in self.time_offset.
        """
        t = await self._connection.call("getTime")
        t = t["time"]
        self.time_offset = t - (time.time() * 1000)

    def _give_input(self, call):
        packet = call.data
        username = self.participants[packet["participantID"]]["username"]
        print("<{}> {}'ed {}".format(username, packet["input"]["event"], packet["input"]["controlID"]))


    def _on_participant_join(self, call):
        packet = call.data
        for participant in packet["participants"]:
            sessionID = participant["sessionID"]
            del participant["sessionID"]
            self.participants[sessionID] = participant
        names = [p["username"] for p in packet["participants"]]
        print("[{}] joined".format(", ".join(names)))


    def _on_participant_leave(self, call):
        packet = call.data
        for participant in packet["participants"]:
            del self.participants[participant["sessionID"]]

        names = [p["username"] for p in packet["participants"]]
        print("[{}] left".format(", ".join(names)))

    def _on_participant_update(self, call):
        packet = call.data
        for participant in packet["participants"]:
            sessionID = participant["sessionID"]
            del participant["sessionID"]
            self.participants[sessionID] = participant
        names = [p["username"] for p in packet["participants"]]
        print("[{}] was updated".format(", ".join(names)))

    def get_participant(self, name):
        for p, d in self.participants.items():
            if p == name or d["username"] == name.lower():
                result = self.participants[p]
                result["sessionID"] = p
                return result
        print("Participant Not Found")
        return None

    def pump_async(self, loop=asyncio.get_event_loop()):
        """
        Starts a pump() process working in the background. Events will be
        dispatched asynchronously.

        Returns a future that can be used for cancelling the pump, if desired.
        Otherwise the pump will automatically stop once
        the connection is closed.

        :rtype: asyncio.Future
        """
        self._enable_event_queue = False

        async def run():
            try:
                while await self._connection.has_packet():
                    self.pump()
            except asyncio.CancelledError:
                self._enable_event_queue = True

        return asyncio.ensure_future(run(), loop=loop)

    def pump(self):
        """
        pump causes the state to read any updates it has queued up. This
        should usually be called at the start of any game loop where you're
        going to be doing processing of Interactive events.

        Any events that have not been read when pump() is called are discarded.

        Alternately, you can call pump_async() to have delivery handled for you
        without manual input.

        :rtype: Iterator of Calls
        """
        self._event_queue.clear()
        while True:
            call = self._connection.get_packet()
            if call is None:
                return

            self.emit(call.name, call)

            if self._enable_event_queue:
                self._event_queue.append(call)

        return self._event_queue

    async def get_scenes(self):
        """
        calls getScenes and stores the scenes in an easily accessible list. It is stored in self._scenes.
        Scenes can be accessed like self._scenes["default"]
        """
        packet = await self._connection.call("getScenes")

        scenes = packet["scenes"]
        for scene in scenes:
            sceneID = scene.pop("sceneID")
            self._scenes[sceneID] = scene
            return self._scenes

    async def get_scene(self, group=None, username=None, userID=None):
        await self.get_scenes()
        groups = await self._connection.call("getGroups")
        groups = groups["groups"]
        if group is not None:
            for g in groups:
                if g["groupID"] == group:
                    return g["sceneID"]
            return None
        if username is not None:
            userID = self.get_participant(username)
            if userID:
                pass
            else:
                print("username was not found in participants: {}".format(username))
                return None
        if userID is not None:
            result = self.participants[userID]
            result = await self.get_scene(group=result["groupID"])
            return result

    async def capture(self, tID):
        await self._connection.call("capture", params={"transactionID": tID})



    async def cooldown(self, sceneID, controlIDs, cooldown):
        """
        Triggers a cooldown for a list of control IDs.

        :param sceneID: str scene ID
        :param controlIDs: list of the controlIDs to cooldown
        :param cooldown:  cooldown time in seconds
        """
        await self.get_scenes()
        temp = []
        for control in controlIDs:
            for c in self._scenes[sceneID]["controls"]:
                if c["controlID"] == control:
                    c["cooldown"] = int(self.calc_time() + (cooldown * 1000))
                    temp.append(c)

        await self._connection.call("updateControls",
                                    params={"sceneID": sceneID, "controls": temp})

    async def apply_keycodes(self, sceneID, control_keycodes):
        """
        Applies keycodes to given controls. <Server does not currently accept this control update>
        :param sceneID: str Scene ID
        :param control_keycodes: A dict in the form of {"controlID": keycode (chr or int)}
        """
        await self.get_scenes()
        temp = []
        for controlID, keycode in control_keycodes.items():
            if type(keycode) == chr:
                keycode = ord(keycode)
            for c in self._scenes[sceneID]["controls"]:
                if c["controlID"] == controlID:
                    c["keyCode"] = keycode
                    temp.append(c)
        await self._connection.call("updateControls",
                                    params={"sceneID": sceneID, "controls": temp})

    async def create_scenes(self, *scenes):
        """
        Can be called with one or more Scenes to add them to Interactive.
        :param scenes: list of scenes to create
        :type scenes: Scene
        """
        for scene in scenes:
            self._scenes[scene.id] = scene
            scene._attach_connection(self)

        return await self._connection.call(
            'createScenes', [s._resolve_all() for s in scenes])

    def _on_scene_delete(self, call):
        if call.data['sceneID'] not in self._scenes:
            return

        self.scenes[call.data['sceneID']].delete(call)
        del self.scenes[call.data['sceneID']]

    def _on_scene_create_or_update(self, call):
        for scene in call.data.scenes:
            if scene['sceneID'] not in self._scenes:
                self._scenes[scene['sceneID']] = Scene(self, scene['sceneID'])

            self._scenes[scene['sceneID']]._apply_changes(scene, call)

    def _on_control_delete(self, call):
        if call.data['sceneID'] in self._scenes:
            self._scenes[call.data['sceneID']]._on_control_delete(call)

    def _on_control_update_or_create(self, call):
        if call.data['sceneID'] in self._scenes:
            self._scenes[call.data['sceneID']].\
                self._on_control_update_or_create(call)

    def _on_control_update(self, call):
        data = call.data
        for c in data["controls"]:
            ctrlID = c.pop("controlID")
            self._controls[ctrlID] = c

    @staticmethod
    async def connect(discovery=Discovery(), **kwargs):
        """
        Creates a new interactive connection. Most arguments will be passed
        through into the Connection constructor.

        :param discovery:
        :param kwargs:
        :return:
        """

        if 'address' not in kwargs:
            kwargs['address'] = await discovery.find()

        connection = Connection(**kwargs)
        await connection.connect()
        return State(connection)
