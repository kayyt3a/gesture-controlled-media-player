# Gesture Media Controller

Control music playback with hand gestures using your webcam. The program tracks your hand in real time, recognises five distinct gestures, and maps each one to a media keyboard shortcut, letting you play, pause, skip, and adjust volume in Spotify without touching the keyboard.

Built as an independent project using computer vision and hand-landmark tracking.

## Demo gestures

| Gesture | Action | Key sent |
| --- | --- | --- |
| Open hand (all fingers up) | Play / Pause | Space |
| Thumbs up (fist with thumb out) | Next track | Ctrl + Right |
| Fist (all fingers down) | Previous track | Ctrl + Left |
| Index finger only | Volume up | Ctrl + Up |
| Peace sign (index + middle) | Volume down | Ctrl + Down |

A 1.5 second cooldown sits between actions so a single held gesture does not fire repeatedly.

## How it works

The webcam feed is captured with OpenCV and passed to MediaPipe's hand-landmark detector, which returns 21 tracked points per hand. From those points the program decides which fingers are extended by comparing each fingertip's position against its knuckle, then matches the pattern to one of the five gestures. When a gesture is recognised, pyautogui sends the matching keyboard shortcut to the active window.

Because the actions are sent as keystrokes, the target application needs to be the focused window. The shortcuts above are Spotify's desktop defaults, so the project is built around controlling Spotify, but the same gestures would drive any app that uses those keys.

## Requirements

- Python 3
- A webcam
- The packages listed in requirements.txt (OpenCV, MediaPipe, pyautogui)

## Running it

First, install the dependencies once:

```bash
pip install -r requirements.txt
```

Then start the program either way:

**Option 1: Double-click (Windows).** Run `run_gesture_player.bat` to launch the program without using a terminal.

**Option 2: Terminal.** From the project folder, run:

```bash
python gesture_player.py
```

On the first run it downloads the MediaPipe hand-landmark model automatically. A window opens showing your webcam feed with the detected hand landmarks drawn on it and the current gesture labelled in the corner. Make sure Spotify is the active window so the keystrokes reach it. Press `q` to quit.

## Notes

This was an exercise in real-time computer vision: reading a video stream, extracting hand landmarks, and turning raw coordinates into reliable gesture classification. The trickiest part was making the finger-up detection robust enough to tell similar gestures apart without false triggers, which the knuckle-versus-fingertip comparison and the action cooldown both help with.
