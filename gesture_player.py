import cv2
import mediapipe as mp
import pyautogui
import time
import threading
import multiprocessing
import pystray
from PIL import Image, ImageDraw
import sys, os, json, math

try:
    import winreg          # Windows-only; used for launch-on-startup
except ImportError:
    winreg = None

def resource_path(filename):
    if hasattr(sys, "_MEIPASS"):          # running as a PyInstaller .exe
        return os.path.join(sys._MEIPASS, filename)
    return filename                        # running as a normal script


class _FakeHands:
    def __init__(self, max_num_hands=1, min_detection_confidence=0.7):
        BaseOptions = mp.tasks.BaseOptions
        HandLandmarker = mp.tasks.vision.HandLandmarker
        HandLandmarkerOptions = mp.tasks.vision.HandLandmarkerOptions
        VisionRunningMode = mp.tasks.vision.RunningMode
        import urllib.request, os
        MODEL_PATH = resource_path("hand_landmarker.task") 
        if not os.path.exists(MODEL_PATH):
            print("Downloading model...")
            urllib.request.urlretrieve(
                "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task",
                MODEL_PATH
            )
        self._detector = HandLandmarker.create_from_options(
            HandLandmarkerOptions(
                base_options=BaseOptions(model_asset_path=MODEL_PATH),
                running_mode=VisionRunningMode.IMAGE,
                num_hands=max_num_hands,
                min_hand_detection_confidence=min_detection_confidence
            )
        )

    def process(self, rgb):
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        raw = self._detector.detect(mp_image)
        class _Result:
            pass
        r = _Result()
        class _FakeLandmark:
            def __init__(self, lm_list):
                self.landmark = lm_list
        r.multi_hand_landmarks = [_FakeLandmark(lm) for lm in raw.hand_landmarks] if raw.hand_landmarks else None
        return r

class _FakeSolutions:
    class hands:
        Hands = _FakeHands
        HAND_CONNECTIONS = None
    class drawing_utils:
        @staticmethod
        def draw_landmarks(frame, hand_lm, connections):
            import cv2
            h, w, _ = frame.shape
            for lm in hand_lm.landmark:
                cx, cy = int(lm.x * w), int(lm.y * h)
                cv2.circle(frame, (cx, cy), 5, (0, 200, 100), -1)

mp.solutions = _FakeSolutions()
# ^^ Copy and pasted solution to my problem to do with outdated software 

stop_event = threading.Event()
enabled = threading.Event()
enabled.set()          # gestures active at startup
show_preview = threading.Event()   # preview off at startup

# ---------------- CONFIG ----------------
DEFAULT_CONFIG = {
    "cooldown": 1.5,        # seconds between actions
    "volume_step": 3,       # number of 2% ticks per volume gesture
    "gestures": {
        "OPEN_HAND": "playpause",
        "THUMBS_UP": "nexttrack",
        "FIST":      "prevtrack",
        "ONE_FINGER":"volumeup",
        "PEACE":     "volumedown",
    },
}

def config_path():
    folder = os.path.join(os.environ["APPDATA"], "GesturePlayer")
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, "config.json")

def save_config(data):
    try:
        with open(config_path(), "w") as f:
            json.dump(data, f, indent=2)
    except OSError:
        pass

def load_config():
    data = {
        "cooldown": DEFAULT_CONFIG["cooldown"],
        "volume_step": DEFAULT_CONFIG["volume_step"],
        "gestures": dict(DEFAULT_CONFIG["gestures"]),
    }
    path = config_path()
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                saved = json.load(f)
            if "cooldown" in saved:
                data["cooldown"] = saved["cooldown"]
            if "volume_step" in saved:
                data["volume_step"] = saved["volume_step"]
            if "gestures" in saved:
                data["gestures"].update(saved["gestures"])
        except (json.JSONDecodeError, OSError):
            pass
    save_config(data)
    return data

CONFIG = load_config()
# ----------------------------------------

# ---------------- LAUNCH ON STARTUP ----------------
# Windows reads this registry key on login and runs whatever commands it lists.
# We add/remove our own entry so the app can start itself when Windows boots.
APP_NAME = "GesturePlayer"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

def startup_target():
    # The command Windows should run at login.
    if getattr(sys, "frozen", False):
        # packaged .exe: just point at the exe itself
        return f'"{sys.executable}"'
    # running as a script: launch with pythonw (no console window) + this file
    script = os.path.abspath(__file__)
    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    return f'"{pyw}" "{script}"'

def is_startup_enabled():
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, APP_NAME)   # raises if our entry is absent
        return True
    except OSError:
        return False

def set_startup(enable):
    if winreg is None:
        return
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enable:
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, startup_target())
            else:
                try:
                    winreg.DeleteValue(key, APP_NAME)
                except FileNotFoundError:
                    pass   # already absent, nothing to remove
    except OSError:
        pass
# ---------------------------------------------------

mp_hands = mp.solutions.hands # Hand tracking model
mp_draw = mp.solutions.drawing_utils # Lines and points along the hands

hands = mp_hands.Hands(max_num_hands = 1, min_detection_confidence = 0.7) # detector itself

cap = cv2.VideoCapture(0) # Connecting OpenCV to the camera with first index 0 meaning connect to first camera on the system - built in webcam

last_action_time = 0 # starting point so there's no weird delay before the first action

def _dist(a, b):
    return math.hypot(a.x - b.x, a.y - b.y)   # straight-line distance between two landmarks

def fingers_up(landmarks):
    ftips = [8, 12, 16, 20] # fingertip indices: index, middle, ring, pinky
    knuckles = [6, 10, 14, 18] # the knuckle below each fingertip
    fingers = []
    for ftip, knuckle in zip(ftips, knuckles):
        fingers.append(landmarks[ftip].y < landmarks[knuckle].y) # tip above knuckle = finger extended

    # Thumb: hand-agnostic check. If the thumb is extended outward, its TIP (4)
    # sits farther from the pinky knuckle (17) than the thumb's own base (2) does.
    # If it's folded across the palm, the tip moves inward, so that distance shrinks.
    # Using distances inside the hand makes this work for either hand and most rotations,
    # unlike the old left/right x-comparison.
    thumb = _dist(landmarks[4], landmarks[17]) > _dist(landmarks[2], landmarks[17])
    return [thumb] + fingers

def detect_gesture(fingers):
    thumb, index, middle, ring, pinky = fingers
    all_up = all([index, middle, ring, pinky])
    all_down = not any([index, middle, ring, pinky])

    if all_up:
        return "OPEN_HAND" # play/pause
    if all_down and thumb:
        return "THUMBS_UP" # next song
    if all_down and not thumb:
        return "FIST" # track before
    if index and not middle and not ring and not pinky:
        return "ONE_FINGER" # volume up
    if index and middle and not ring and not pinky:
        return "PEACE" # volume down
    return None

def run_action(action):
    # Knows HOW to perform each action name. Config decides WHICH gesture maps to which action.
    if action == "playpause":
        pyautogui.press("playpause")
    elif action == "nexttrack":
        pyautogui.press("nexttrack")
    elif action == "prevtrack":
        pyautogui.press("prevtrack")
    elif action == "volumeup":
        for _ in range(CONFIG["volume_step"]):
            pyautogui.press("volumeup")
    elif action == "volumedown":
        for _ in range(CONFIG["volume_step"]):
            pyautogui.press("volumedown")
    else:
        return   # unknown action name, do nothing
    print(action)

def do_action(gesture):
    global last_action_time
    now = time.time()
    if now - last_action_time < CONFIG["cooldown"]:
        return
    last_action_time = now

    action = CONFIG["gestures"].get(gesture)
    if action:
        run_action(action)

def gesture_loop():
    preview_open = False
    while cap.isOpened() and not stop_event.is_set():
        ret, frame = cap.read()
        if not ret:
            break
        frame = cv2.flip(frame, 1)
        if not enabled.is_set():
            if show_preview.is_set():
                cv2.imshow("Gesture Player", frame)
                cv2.waitKey(1)
                preview_open = True
            elif preview_open:
                cv2.destroyAllWindows()
                preview_open = False
            continue
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        result = hands.process(rgb)

        if result.multi_hand_landmarks:
            for hand_lm in result.multi_hand_landmarks:
                mp_draw.draw_landmarks(frame, hand_lm, mp_hands.HAND_CONNECTIONS)
                lm = hand_lm.landmark
                fingers = fingers_up(lm)
                gesture = detect_gesture(fingers)
                if gesture:
                    do_action(gesture)
                cv2.putText(frame, str(gesture), (10, 50),
                            cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 200, 100), 2)

        if show_preview.is_set():
            cv2.imshow("Gesture Player", frame)
            cv2.waitKey(1)
            preview_open = True
        elif preview_open:
            cv2.destroyAllWindows()
            preview_open = False

    cap.release()
    cv2.destroyAllWindows()

def make_icon():
    # Use a bundled icon.png if present, otherwise fall back to a drawn circle.
    try:
        return Image.open(resource_path("icon.png"))
    except Exception:
        img = Image.new("RGB", (64, 64), "black")
        ImageDraw.Draw(img).ellipse((16, 16, 48, 48), fill="white")
        return img

def on_quit(icon, item):
    stop_event.set()
    icon.stop()

def on_toggle_enabled(icon, item):
    if enabled.is_set():
        enabled.clear()
    else:
        enabled.set()

def on_toggle_preview(icon, item):
    if show_preview.is_set():
        show_preview.clear()
    else:
        show_preview.set()

def on_toggle_startup(icon, item):
    set_startup(not is_startup_enabled())   # flip whatever the current state is

def main():
    worker = threading.Thread(target=gesture_loop, daemon=True)
    worker.start()

    menu = pystray.Menu(
        pystray.MenuItem("Enabled", on_toggle_enabled, checked=lambda item: enabled.is_set()),
        pystray.MenuItem("Show preview", on_toggle_preview, checked=lambda item: show_preview.is_set()),
        pystray.MenuItem("Start on login", on_toggle_startup, checked=lambda item: is_startup_enabled()),
        pystray.MenuItem("Quit", on_quit),
    )
    icon = pystray.Icon("gesture_player", make_icon(), "Gesture Player", menu)
    icon.run()

    worker.join(timeout=2)

if __name__ == "__main__":
    multiprocessing.freeze_support()   # required so the PyInstaller .exe doesn't relaunch itself
    main()
# py gesture_player.py