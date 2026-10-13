# pfa-week05

## Which app, and which way

I built a bridge for Unreal Engine 5.8 on Windows, and it works through a port. When the Unreal Editor opens, the bridge starts automatically and listens on port 9877 on my own computer. The agent writes Python code and sends it from the terminal with `ue_send.py`. Unreal runs the code live inside the open editor, so I can watch the scene change, and then it sends the result or any error back to the terminal.

## How to run it

### What's in this repo

| File | What it is |
|---|---|
| `claude_bridge.py` | **The listener.** It runs inside Unreal and listens on port 9877 for code from the terminal. |
| `init_unreal.py` | Starts the listener automatically every time Unreal opens. |
| `ue_send.py` | **The sender.** Run it in a terminal to send a Python script to Unreal and get the result back. |
| `install.bat` | Copies the listener files to where Unreal looks for them. |
| `gamesetup.py`, `gamebuild.py`, `gamecode.py` | The scripts the agent wrote to make my game (setup, level build, game logic). |

### 1. Install the listener (once)

You need Unreal Engine 5 and Python 3 on Windows.

1. Download this repo (**Code → Download ZIP**) and unzip it.
2. Double-click **`install.bat`**. It copies `claude_bridge.py` and `init_unreal.py` into
   `Documents\UnrealEngine\Python\`. Unreal runs `init_unreal.py` from that folder whenever it starts.
   (No .bat? Copy those two files there by hand. Create the folder if it doesn't exist.)
3. Open your Unreal project. Go to **Edit → Plugins**, search for **Python Editor Script Plugin**,
   turn it on, and restart Unreal.
4. Open **Window → Output Log**. You should see:
   `[claude_bridge] watching ...\claude_bridge\inbox and 127.0.0.1:9877`
   That means the listener is running.

### 2. Test the connection

Open a terminal in the repo folder and run:

```
python ue_send.py --ping
```

If it prints `pong from Unreal 5.x...`, everything is connected. Try one real command:

```
python ue_send.py -c "print(len(actors.get_all_level_actors()), 'actors in this level')"
```

### 3. Let your agent use it

Start your agent (I used Claude Code) in the repo folder and tell it:

> You can control my open Unreal Editor. Write Python for Unreal's `unreal` module, save it as a .py file,
> and run it with `python ue_send.py <file>`. `actors`, `level`, `assets`, `tools` and `snap(name)` are already loaded.

Then ask it for things in plain words.

### 4. Rebuild my game (optional)

1. Copy `gamecode.py` into your project's `Content\Python\` folder and **rename it to `td_game.py`** (the game is loaded with `import td_game`).
2. With Unreal open, run `python ue_send.py gamesetup.py`. This makes the materials, a game mode and an empty level, TD_Arena.
3. Run `python ue_send.py gamebuild.py`. This builds the arena.
4. Run `python ue_send.py -c "import td_game; td_game.install()"`, then press **Play**.

Controls: WASD to move, mouse to aim, Space or left click to attack, Shift to dash, R to restart.

### If it doesn't connect

- `Could not reach Unreal on 127.0.0.1:9877`: Unreal isn't open, or the Python plugin is off. Check step 1.4.
- No `[claude_bridge]` line in the Output Log: the two files aren't in `Documents\UnrealEngine\Python\`.
  If your Documents folder is synced to OneDrive, check there.
- A command times out: a popup is open in Unreal. Close it and try again.

## What I asked for

I firstly asked the agent to establish a bridge to Unreal Engine like what we do in the class. Then the agent installed the bridge file and helped me open a new project and place blocks inside it for testing.
<img width="2556" height="1311" alt="2d671de1693da0b02e5bf9a71fe2dbc3" src="https://github.com/user-attachments/assets/425349d7-56c9-4b21-99d6-2093d19ac735" />

After that, I said "now, can you create a small playable top-down 3D action-adventure game in my Unreal Engine project.". So the agent ran for a long time and open my Unreal Engine to create the game.
<img width="2559" height="1521" alt="image" src="https://github.com/user-attachments/assets/5c4049f6-1985-4998-a253-375c158804cd" />
<img width="2553" height="1524" alt="image" src="https://github.com/user-attachments/assets/ad4d480a-f5de-4309-841c-3c7e0c020384" />

## Video link
https://drive.google.com/file/d/1A5mWwcVRb1fgpztkzPxSYiXj_PbxwHbT/view?usp=sharing
