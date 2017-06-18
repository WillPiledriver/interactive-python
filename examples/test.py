from beam_interactive2 import *
import config
import asyncio
from pygame import mixer as sound

class Bot:

    def __init__(self, state_handle):
        self.state = state_handle
        self.con = self.state._connection
        self.state.on("giveInput", lambda call: self.user_input(call))

        sound.init(44100, 16, 2, 4096)

        self.control_groups = [
            {
                "cooldown": 0,
                "ids": ["W", "A", "S", "D", "Jump"]
            },
            {
                "cooldown": 30,
                "ids": ["Sound 1", "Sound 2"]
            }
        ]

        self.controls = {
            "W": self.move_input,
            "A": self.move_input,
            "S": self.move_input,
            "D": self.move_input,
            "Jump": self.jump,
            "Sound 1": self.play_sound,
            "Sound 2": self.play_sound
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

        self.button_states = {key:{"pressing": []} for key in self.controls.keys()}


    async def user_input(self, call):
        user = call.data["participantID"]
        inpt = call.data["input"]
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
                self.controls[ctrlID](user, inpt)

        for g in self.control_groups:
            if ctrlID in g["ids"]:
                if g["cooldown"] > 0:
                    await self.state.cooldown("default", g["ids"], g["cooldown"])
                break


    def move_input(self, user, inpt):
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

    def jump(self, user, inpt):
        if inpt["event"] == "mousedown":
            print("Jumped")

    def play_sound(self, user, inpt):
        ctrlID = inpt["controlID"]
        print("{} played {}".format(self.state.participants[user]["username"], ctrlID))
        sObj = sound.Sound(self.soundboard[ctrlID])
        sObj.play()


    async def setup(self, controls):
        self.state.pump_async()
        ck = {control: self.keyboard_buttons[control]["keyboard"] for control in self.keyboard_buttons.keys()}
        await self.state.apply_keycodes("default", ck)
        await self.con.call("ready", params={"isReady": True})

    async def doTests(self):
        await self.state.get_scenes()
        while True:
            await asyncio.sleep(1)


async def main(controls):
    handle = await create(config)
    b = Bot(handle)
    await b.setup(controls)
    await b.doTests()


async def read(bot):
    await bot.con._read()



controls = [
    {
        "controlID": "Test 3",
        "kind": "button",
        "text": "Test 3",
        "cost": 0,
        "position": {
            "size": "large",
            "width": 3,
            "height": 1,
            "x": 0,
            "y": 10
        }
},

    {
        "controlID": "Test 4",
        "kind": "button",
        "text": "Test 4",
        "cost": 0,
        "position": {
            "size": "large",
            "width": 3,
            "height": 1,
            "x": 0,
            "y": 15
        }
}

]


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main(controls))
    loop.close()