from beam_interactive2 import *
import config
import asyncio
from pygame import mixer as sound
from pykeyboard import PyKeyboard
k = PyKeyboard()

class Bot:

    def __init__(self, state_handle):
        self.state = state_handle
        self.con = self.state._connection
        self.state.on("giveInput", lambda call: self.user_input(call))
        self.state.on("onParticipantJoin", lambda call: self.assign_user(call))

        sound.init(44100, 16, 2, 4096)

        self.control_groups = [
            {
                "cooldown": 0,
                "ids": ["W", "A", "S", "D", "Jump"]
            },
            {
                "cooldown": 30,
                "ids": ["Sound 1", "Sound 2"]
            },
            {
                "cooldown": 10,
                "ids": ["test"]
            },
            {
                "cooldown": 300,
                "ids": ["spawn", "spawn2"]
            }
        ]

        self.controls = {
            "W": self.move_input,
            "A": self.move_input,
            "S": self.move_input,
            "D": self.move_input,
            "Jump": self.jump,
            "Sound 1": self.play_sound,
            "Sound 2": self.play_sound,
            "spawn":self.spawn_enemy,
            "spawn2": self.spawn_enemy
        }

        self.keyboard_buttons = {
            "W": {"down": False, "keyboard": "w"},
            "A": {"down": False, "keyboard": "a"},
            "S": {"down": False, "keyboard": "s"},
            "D": {"down": False, "keyboard": "d"},
            "Jump": {"down": False, "keyboard": " "}
        }

        self.soundboard = {
            "Sound 1": "./dogtoy.wav",
            "Sound 2": "./meow.wav"
        }

        self.user_groups = {
            "admin_group": []
        }




        self.button_states = {key:{"pressing": []} for key in self.controls.keys()}


    async def user_input(self, call):
        data = call.data
        user = data["participantID"]
        inpt = data["input"]
        ctrlID = inpt["controlID"]
        try:
            if inpt["event"] == "mousedown":
                self.button_states[ctrlID]["pressing"].append(user)
                self.button_states[ctrlID]["pressing"] = list(set(self.button_states[ctrlID]["pressing"]))
            elif inpt["event"] == "mouseup":
                self.button_states[ctrlID]["pressing"].remove(user)
            elif inpt["event"] == "move":
                print("{} moved joystick {} to ({}, {})".format(self.state.participants[user]["username"], ctrlID, inpt["x"], inpt["y"]))
            else:
                print("Unknown button event: {}".format(json.dumps(inpt)))
        except KeyError:
            if inpt["event"] == "mousedown":
                print("{} not defined in controls".format(ctrlID))
            return

        if ctrlID in self.keyboard_buttons:
            self.controls[ctrlID](user, inpt)
        else:
            if inpt["event"] == "mousedown":
                self.controls[ctrlID](data)

        if "transactionID" in data:
            await self.state.capture(data["transactionID"])

        for g in self.control_groups:
            if ctrlID in g["ids"]:
                if g["cooldown"] > 0:
                    sceneID = await self.state.get_scene(userID=user)
                    await self.state.cooldown(sceneID, g["ids"], g["cooldown"])
                break


    def move_input(self, data):
        inpt = data["input"]
        c = inpt["controlID"]
        n = len(set(self.button_states[c]["pressing"]))
        state = self.keyboard_buttons[c]["down"]
        if n == 1:
            if state == False:
                print("Keyboard {} down".format(self.keyboard_buttons[c]["keyboard"]))
                self.keyboard_buttons[c]["down"] = True
        elif n == 0:
            if state:
                print("Keyboard {} up".format(self.keyboard_buttons[c]["keyboard"]))
                self.keyboard_buttons[c]["down"] = False
        else:
            print(self.button_states)

    def jump(self, data):
        inpt = data["input"]
        if inpt["event"] == "mousedown":
            print("Jumped")


    def spawn_enemy(self, data):
        print("Spawn Enemy")
        #time.sleep(2)
        #k.type_string("`player->spawnonpc asdasdasdada 1\r", 0.01)


    async def assign_user(self, call):
        p = call.data["participants"][0]
        for g, v in self.user_groups.items():
            if v.count(p["username"].lower()) > 0:

                user = self.state.get_participant(p["username"])
                user["groupID"] = g
                await self.con.call("updateParticipants", params={"participants": [user]})

    def play_sound(self, data):
        inpt = data["input"]
        user = data["participantID"]
        ctrlID = inpt["controlID"]
        print("{} played {}".format(self.state.participants[user]["username"], ctrlID))
        sObj = sound.Sound(self.soundboard[ctrlID])
        sObj.play()


    async def setup(self):
        self.state.pump_async()
        await self.state.get_scenes()
        groups = [
            {"groupID": "admin_group",
             "etag": random_etag(),
             "sceneID": "admin"}
        ]
        #print(await self.con.call("createGroups", params={"groups": groups}))
        ck = {control: self.keyboard_buttons[control]["keyboard"] for control in self.keyboard_buttons.keys()}
        #await self.state.apply_keycodes("default", ck)
        await self.con.call("ready", params={"isReady": True})

    async def doTests(self):
        #print(await self.con.call("getGroups"))
        while True:
            await asyncio.sleep(1)


async def main():
    handle = await create(config)
    b = Bot(handle)
    await b.setup()
    await b.doTests()


async def read(bot):
    await bot.con._read()


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
    loop.close()