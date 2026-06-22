import cv2
import mediapipe as mp
import pyautogui
import time


class _FakeHands:
    def __init__(self, max_num_hands=1, min_detection_confidence=0.7):
        BaseOptions = mp.tasks.BaseOptions
        HandLandmarker = mp.tasks.vision.HandLandmarker
        HandLandmarkerOptions = mp.tasks.vision.HandLandmarkerOptions
        VisionRunningMode = mp.tasks.vision.RunningMode
        import urllib.request, os
        MODEL_PATH = "hand_landmarker.task"
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
        import mediapipe as mp
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

mp_hands = mp.solutions.hands # Hand tracking model
mp_draw = mp.solutions.drawing_utils # Lines and points along the hands

hands = mp_hands.Hands(max_num_hands = 1, min_detection_confidence = 0.7) # detector itself
# detecting one hand at a time, only reporting a hand if its at least 70% confident it actually found one in the frame - stops confusion with random background object

cap = cv2.VideoCapture(0) # Connecting OpenCV to the camera with first index 0 meaning connect to first camera on the system - built in webcam

last_action_time = 0 # Treat this as a starting point - you're basically resetting the elapsed time to 0 so that the machine thinks that no action has really happened. This is so that there is no weird delay between actions. 
COOLDOWN = 1.5 # How many actions must pass before another action can be taken - all CAPS enforces the rule that this should not be changed mid program. 

def fingers_up(landmarks):
    ftips = [8, 12, 16, 20] # indexing for each point
    knuckles = [6, 10, 14, 18] # indexing for each point
    fingers = [] #True/False to be appended in here
    for ftip, knuckle in zip(ftips, knuckles): # zip function puts eg. (8, 6) together
        fingers.append(landmarks[ftip].y < landmarks[knuckle].y) # append True/False whether knuckles are more or less than fingertips - extension of finger
    thumb = landmarks[4].x < landmarks[3].x # append True/False for extension of thumb
    return [thumb] + fingers # Hence return true or false for thumb and finger 

def detect_gesture(fingers):
    thumb, index, middle, ring, pinky = fingers
    all_up = all([index, middle, ring, pinky]) # returns True only if every item here is True
    all_down = not any([index, middle, ring, pinky]) # returns True if at least one is True so not means none are True

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

def do_action(gesture):
    global last_action_time # global links it to the main/outer variable so that when you update inside the function, it updates the original value itself. 
    now = time.time()
    if now - last_action_time < COOLDOWN:
        return
    last_action_time = now

    if gesture == "OPEN_HAND":
        pyautogui.press("space")
        print("Play/Pause")
    elif gesture == "THUMBS_UP":
        pyautogui.hotkey("ctrl", "right")
        print("Next track")
    elif gesture == "FIST":
        pyautogui.hotkey("ctrl", "left")
        print("Previous track")
    elif gesture == "ONE_FINGER":
        pyautogui.hotkey("ctrl", "up")
        print("Volume up")
    elif gesture == "PEACE":
        pyautogui.hotkey("ctrl", "down")
        print("Volume down")

while cap.isOpened(): # loop that runs as long as the camera is running 
    ret, frame = cap.read() # Frame is the actual image as a grid of pixels. Ret (Return status) is a True/False value meaning "Did that work?"
    if not ret: # If Return status fails eg. camera disconnection, something went wrong - this results in a break of the loop rather than a crash in the program. 
        break

    frame = cv2.flip(frame, 1) # inverts the selfie camera to negate the pre-installed inverse feature already
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB) # Pixels are ordered weirdly as OpenCV reads colour in BGR whereas MediaPipe reads in RGB - this is basically a conversion to reorder them appropriately

    result = hands.process(rgb) # Pixels in frame are processed and handed to MediaPipe - result returns everything that MediaPipe found 

    if result.multi_hand_landmarks: # do anything if MediaPipe found a hand in frame
        for hand_lm in result.multi_hand_landmarks: # Loop through each detected hand 
            mp_draw.draw_landmarks(frame, hand_lm, mp_hands.HAND_CONNECTIONS) # Draws landmarks eg. pinpoints and lines for points on hand
            lm = hand_lm.landmark # Simplifies landmark for each looped hand
            fingers = fingers_up(lm) # call function with landmark as parameter
            gesture = detect_gesture(fingers) # 
            if gesture:
                do_action(gesture)
            cv2.putText(frame, str(gesture), (10, 50),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 200, 100), 2)
    
    cv2.imshow("Gesture Player", frame)
    if cv2.waitKey(1) & 0xFF == ord("q"):
        break



cap.release() # closes connection to the webcam so it's freed up for other programs
cv2.destroyAllWindows() # closes the camera window


# py gesture_player.py


