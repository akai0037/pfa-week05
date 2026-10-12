# pfa-week05

I built a bridge for Unreal Engine 5.8 on Windows, and it works through a port. When the Unreal Editor opens, the bridge starts automatically and listens on port 9877 on my own computer. The agent writes Python code and sends it from the terminal with `ue_send.py`. Unreal runs the code live inside the open editor, so I can watch the scene change, and then it sends the result or any error back to the terminal.

There are two script. First, ensure install the bridge from the terminal to Unreal Engine 5. Next, copy 'gamecode.py' into the project's `Content/Python` folder (create the folder if it doesn't exist).Then build a new level in Unreal project and copy 'gamebuild.py' into the project which builds the whole game level. Finally, run them and press Play in Unreal. Controls: WASD to move, mouse to aim, Space or left click to attack, Shift to dash, R to restart.

I firstly asked the agent to establish a bridge to Unreal Engine like what we do in the class. Then the agent installed the bridge file and helped me open a new project and place blocks inside it for testing.
<img width="2556" height="1311" alt="2d671de1693da0b02e5bf9a71fe2dbc3" src="https://github.com/user-attachments/assets/425349d7-56c9-4b21-99d6-2093d19ac735" />

After that, I said "now, can you create a small playable top-down 3D action-adventure game in my Unreal Engine project.". So the agent ran for a long time and open my Unreal Engine to create the game.
<img width="2559" height="1521" alt="image" src="https://github.com/user-attachments/assets/5c4049f6-1985-4998-a253-375c158804cd" />
<img width="2553" height="1524" alt="image" src="https://github.com/user-attachments/assets/ad4d480a-f5de-4309-841c-3c7e0c020384" />

## video link
https://drive.google.com/file/d/1A5mWwcVRb1fgpztkzPxSYiXj_PbxwHbT/view?usp=sharing
