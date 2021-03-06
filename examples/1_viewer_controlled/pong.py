"""
We've modified our base pong game to run an interactive where the viewers
control the paddle on the right. We handle all the control setup within our
client, but you can also design your controls in the Interactive Studio!

You should provide an OAuth token to connect to interactive on the comment line.
You can get this token by going to https://interactive.beam.pro/request

Press 'q' to quit.

Run this with::

    python -m examples.1_viewer_controlled.pong <ThatLongOAuthToken>
"""

from beam_interactive2 import State, Scene, Button, keycode, until_event
from sys import argv

from ..engine import BaseGame, run


class Game(BaseGame):
    def __init__(self):
        super(Game, self).__init__()
        self._player_1 = self._create_paddle(x=0, height=self._screen_height//6)
        self._player_2 = self._create_paddle(x=self._screen_width-1,
                                             height=self._screen_height//4)
        self._interactive = None

    async def setup(self):
        """
        Called automatically by our game engine to boot the game. We'll create
        an interactive connection here! I've hard-coded a blank project to use.
        """
        try:
            interactive = await State.connect(authorization="Bearer " + argv[1],
                                              project_version_id=42489,
                                              project_sharecode='rheo1hre')
        except Exception as e:
            print("Error connecting to interactive", e)
            return

        self._interactive = interactive

        interactive.pump_async()
        await self._setup_controls()

    async def _setup_controls(self):
        """
        All the control setup! Alternately, you can design the controls in
        the Interactive Studio.
        """
        self._up_button = Button(
            control_id='up',
            text='Up',
            keycode=keycode.up,
            position=[
                {'size': 'large', 'width': 5, 'height': 5, 'x': 0, 'y': 0},
            ],
        )

        self._down_button = Button(
            control_id='down',
            text='Down',
            keycode=keycode.down,
            position=[
                {'size': 'large', 'width': 5, 'height': 5, 'x': 0, 'y': 6},
            ],
        )

        return self._interactive.scenes['default'].create_controls(
            self._up_button,
            self._down_button
        )

    async def update(self, pressed_key=None):
        if pressed_key == ord('s'):
            self._player_1.move(1)
        elif pressed_key == ord('w'):
            self._player_1.move(-1)

        if self._up_button.presses() > 0:
            self._player_2.move(1)
        elif self._down_button.presses() > 0:
            self._player_2.move(-1)

        self._ball.step(self._player_1, self._player_2)


run(Game())
