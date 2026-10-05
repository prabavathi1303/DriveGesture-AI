import cv2
import mediapipe as mp
import math
import ctypes
import time
from collections import deque
from pathlib import Path
import numpy as np

from mediapipe.tasks import python
from mediapipe.tasks.python import vision
from pycaw.pycaw import AudioUtilities

# ============================================================
# OPTIONAL WINDOWS MOUSE CONTROL
# ============================================================
try:
    import pyautogui
    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False

# Make mouse/screenshot coordinates match the real Windows screen
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass

# ============================================================
# PATHS
# ============================================================
BASE_DIR = Path(__file__).resolve().parent.parent
HAND_MODEL = BASE_DIR / "models" / "hand_landmarker.task"
FACE_MODEL = BASE_DIR / "models" / "face_landmarker.task"

# ============================================================
# AUDIO
# ============================================================
devices = AudioUtilities.GetSpeakers()
volume_control = devices.EndpointVolume
system_volume = volume_control.GetMasterVolumeLevelScalar()

def next_song():
    ctypes.windll.user32.keybd_event(0xB0, 0, 0, 0)
    ctypes.windll.user32.keybd_event(0xB0, 0, 2, 0)

def previous_song():
    ctypes.windll.user32.keybd_event(0xB1, 0, 0, 0)
    ctypes.windll.user32.keybd_event(0xB1, 0, 2, 0)

# ============================================================
# WHATSAPP SCREEN BUTTON CONTROL
# ============================================================
# This version does NOT depend on WhatsApp UI Automation.
# It looks at the actual screen and finds the large green/red
# incoming-call button shown in the user's WhatsApp window.
# ============================================================

def _find_call_button(button="accept"):
    if not PYAUTOGUI_AVAILABLE:
        return None

    try:
        screenshot = pyautogui.screenshot()
    except Exception:
        return None

    image = np.array(screenshot)
    hsv = cv2.cvtColor(image, cv2.COLOR_RGB2HSV)
    screen_h, screen_w = image.shape[:2]

    if button == "accept":
        # WhatsApp green Accept
        lower = np.array([35, 70, 70], dtype=np.uint8)
        upper = np.array([95, 255, 255], dtype=np.uint8)
    else:
        # WhatsApp red Reject/Hang-up
        lower1 = np.array([0, 80, 70], dtype=np.uint8)
        upper1 = np.array([12, 255, 255], dtype=np.uint8)
        lower2 = np.array([165, 80, 70], dtype=np.uint8)
        upper2 = np.array([179, 255, 255], dtype=np.uint8)

    if button == "accept":
        mask = cv2.inRange(hsv, lower, upper)
    else:
        mask1 = cv2.inRange(hsv, lower1, upper1)
        mask2 = cv2.inRange(hsv, lower2, upper2)
        mask = cv2.bitwise_or(mask1, mask2)

    kernel = np.ones((7, 7), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(
        mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )

    candidates = []

    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        area = w * h

        # Call controls are near the bottom of the screen.
        if y < int(screen_h * 0.62):
            continue

        # Wide horizontal button for Accept.
        # Round red Reject is smaller, so use separate rules.
        if button == "accept":
            if area > 5000 and w > 180 and h > 30 and w > h * 2.5:
                candidates.append((x, y, w, h, area))
        else:
            if area > 1500 and w > 35 and h > 25 and w / max(h, 1) < 4.5:
                candidates.append((x, y, w, h, area))

    if not candidates:
        return None

    # Prefer the lowest/largest candidate.
    candidates.sort(
        key=lambda item: (item[1] + item[3], item[4]),
        reverse=True
    )

    x, y, w, h, area = candidates[0]

    return {
        "x": x,
        "y": y,
        "w": w,
        "h": h,
        "cx": x + w // 2,
        "cy": y + h // 2,
        "area": area
    }

def _click_screen_point(x, y):
    if not PYAUTOGUI_AVAILABLE:
        return False

    try:
        pyautogui.moveTo(int(x), int(y), duration=0.20)
        time.sleep(0.15)
        pyautogui.click()
        return True
    except Exception:
        return False

def accept_whatsapp_call():
    found = _find_call_button("accept")

    if found is None:
        print("WhatsApp ACCEPT button not found.")
        return False

    print(
        "WhatsApp GREEN Accept detected at "
        f"({found['cx']}, {found['cy']}), "
        f"area={found['area']}"
    )

    ok = _click_screen_point(found["cx"], found["cy"])

    if ok:
        print("Clicked WhatsApp ACCEPT button.")

    return ok

def reject_whatsapp_call():
    found = _find_call_button("reject")

    if found is None:
        print("WhatsApp REJECT button not found.")
        return False

    print(
        "WhatsApp RED Reject detected at "
        f"({found['cx']}, {found['cy']}), "
        f"area={found['area']}"
    )

    ok = _click_screen_point(found["cx"], found["cy"])

    if ok:
        print("Clicked WhatsApp REJECT button.")

    return ok

def toggle_whatsapp_mute():
    # Try UI Automation only for mute if available.
    # The incoming-call accept/reject feature does not depend on it.
    try:
        from pywinauto import Desktop

        windows = Desktop(backend="uia").windows(
            title_re=r"(?i).*WhatsApp.*",
            visible_only=True
        )

        for window in windows:
            try:
                buttons = window.descendants(control_type="Button")
                for b in buttons:
                    names = []
                    try:
                        names.append(str(b.window_text()).lower())
                    except Exception:
                        pass
                    try:
                        names.append(str(b.element_info.name).lower())
                    except Exception:
                        pass

                    joined = " ".join(names)

                    if "mute" in joined and "unmute" not in joined:
                        b.click_input()
                        return "MUTED"

                    if "unmute" in joined:
                        b.click_input()
                        return "UNMUTED"
            except Exception:
                pass
    except Exception:
        pass

    return None

# ============================================================
# MEDIAPIPE MODELS
# ============================================================
hand_base = python.BaseOptions(
    model_asset_path=str(HAND_MODEL)
)

hand_options = vision.HandLandmarkerOptions(
    base_options=hand_base,
    num_hands=1
)

hand_detector = vision.HandLandmarker.create_from_options(
    hand_options
)

face_base = python.BaseOptions(
    model_asset_path=str(FACE_MODEL)
)

face_options = vision.FaceLandmarkerOptions(
    base_options=face_base,
    num_faces=1,
    output_facial_transformation_matrixes=True
)

face_detector = vision.FaceLandmarker.create_from_options(
    face_options
)

# ============================================================
# CAMERA
# ============================================================
cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)

if not cap.isOpened():
    print("ERROR: Could not open camera.")
    raise SystemExit

print("Camera opened successfully.")

WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 720

# ============================================================
# STATE
# ============================================================
modes = ["MUSIC", "PHONE", "NAVIGATION"]
selected_mode = 0
context = "PHONE"   # Start directly in PHONE for testing.

navigation_cards = [
    "TURN RIGHT",
    "GO STRAIGHT",
    "TURN LEFT",
    "DESTINATION"
]

navigation_distance = [
    "500 m",
    "1.2 km",
    "300 m",
    "100 m"
]

navigation_card = 0
zoom_level = 100

song_name = "Drive Mode"
artist_name = "DriveGesture Player"

phone_status = "CALL WAITING"

speed = 42

gesture = "NO GESTURE"
head_direction = "NO FACE"
yaw_degrees = 0
driver_present = False
safety_status = "UNSAFE - NO DRIVER"
action = "WAITING"

# ============================================================
# ROBUST SWIPE DETECTION
# ============================================================
swipe_points = deque(maxlen=20)
last_swipe_time = 0
swipe_cooldown = 1.0

# Minimum movement in pixels.
SWIPE_DISTANCE = 90

# We only use recent points, so a normal hand movement is not
# accidentally kept for too long.
SWIPE_WINDOW_SECONDS = 0.65

# ============================================================
# PINCH
# ============================================================
pinch_threshold = 0.055
previous_y = None
last_pinch_time = 0
pinch_cooldown = 1.0

# ============================================================
# UI
# ============================================================
BG = (12, 16, 22)
PANEL_BG = (22, 28, 36)
PANEL_BORDER = (55, 68, 82)
CARD_BG = (28, 36, 46)
TEXT = (235, 242, 248)
MUTED = (145, 158, 172)
ACCENT = (70, 190, 255)
SUCCESS = (100, 220, 150)
DANGER = (100, 100, 240)
ROAD = (58, 68, 80)
ROAD_MAIN = (78, 90, 105)

def text(img, message, x, y, size=0.7, thickness=2, color=TEXT):
    cv2.putText(
        img,
        str(message),
        (int(x), int(y)),
        cv2.FONT_HERSHEY_SIMPLEX,
        size,
        color,
        thickness,
        cv2.LINE_AA
    )

def rounded_panel(img, x1, y1, x2, y2):
    cv2.rectangle(img, (x1, y1), (x2, y2), PANEL_BG, -1)
    cv2.rectangle(img, (x1, y1), (x2, y2), PANEL_BORDER, 1)

def draw_phone_panel(dashboard):
    text(dashboard, "PHONE", 655, 155, 0.8, 2)
    text(dashboard, "IN-CAR CALL", 655, 230, 1.0, 2)
    text(dashboard, phone_status, 655, 280, 0.65, 2)

    text(dashboard, "Swipe Right  → Accept", 655, 365, 0.55, 1)
    text(dashboard, "Swipe Left   → Reject", 655, 405, 0.55, 1)
    text(dashboard, "Pinch → Mute", 655, 445, 0.55, 1)

def draw_music_panel(dashboard, volume):
    text(dashboard, "MUSIC", 655, 155, 0.8, 2)
    text(dashboard, "NOW PLAYING", 655, 215, 0.55, 1)
    text(dashboard, song_name, 655, 270, 1.0, 2)
    text(dashboard, artist_name, 655, 310, 0.6, 1)
    text(dashboard, f"VOLUME  {volume}%", 655, 375, 0.7, 2)

    cv2.rectangle(
        dashboard, (655, 400), (1190, 425), (80, 80, 80), -1
    )

    filled = int(535 * volume / 100)
    cv2.rectangle(
        dashboard, (655, 400), (655 + filled, 425),
        ACCENT, -1
    )

    text(dashboard, "Swipe ← / →  Change Track", 655, 475, 0.55, 1)
    text(dashboard, "Pinch ↑ / ↓  Volume", 655, 510, 0.55, 1)

def draw_home_panel(dashboard):
    text(dashboard, "SELECT MODE", 655, 155, 0.8, 2)

    names = ["MUSIC", "PHONE", "NAVIGATION"]
    xs = [655, 850, 1045]

    for i in range(3):
        x = xs[i]
        selected = i == selected_mode

        cv2.rectangle(
            dashboard,
            (x, 210), (x + 165, 330),
            CARD_BG if not selected else (55, 65, 78),
            -1
        )

        cv2.rectangle(
            dashboard,
            (x, 210), (x + 165, 330),
            ACCENT if selected else PANEL_BORDER,
            3 if selected else 1
        )

        text(dashboard, names[i], x + 20, 275, 0.60, 2)

        if selected:
            text(dashboard, "SELECTED", x + 30, 305, 0.42, 1)

    text(dashboard, "SWIPE RIGHT  →  NEXT MODE", 700, 390, 0.55, 1)
    text(dashboard, "SWIPE LEFT   ←  PREVIOUS MODE", 700, 430, 0.55, 1)
    text(dashboard, "PINCH             SELECT", 700, 470, 0.55, 1)

def draw_navigation_panel(dashboard):
    text(dashboard, "NAVIGATION", 655, 155, 0.8, 2)

    x1, y1, x2, y2 = 655, 185, 930, 515

    cv2.rectangle(
        dashboard, (x1, y1), (x2, y2),
        (18, 24, 31), -1
    )

    cv2.line(
        dashboard, (x1 + 40, y2 - 50),
        (x2 - 40, y1 + 80), ROAD_MAIN, 30
    )

    cv2.line(
        dashboard, (x1 + 100, y1 + 180),
        (x2 - 30, y1 + 180), ROAD_MAIN, 30
    )

    cv2.circle(
        dashboard, (x2 - 55, y1 + 80),
        14, ACCENT, -1
    )

    text(
        dashboard,
        navigation_cards[navigation_card],
        965, 250, 0.7, 2
    )

    text(
        dashboard,
        navigation_distance[navigation_card],
        965, 300, 0.8, 2
    )

    text(
        dashboard,
        f"CARD {navigation_card + 1} / 4",
        965, 350, 0.5, 1
    )

    text(dashboard, "Swipe ← / →", 965, 410, 0.5, 1)
    text(dashboard, "Pinch = Zoom", 965, 445, 0.5, 1)

# ============================================================
# ACTION HANDLERS
# ============================================================
def handle_gesture(g):
    global context
    global selected_mode
    global action
    global phone_status
    global navigation_card
    global zoom_level
    global song_name

    if g not in ("SWIPE RIGHT", "SWIPE LEFT", "PINCH"):
        return

    if safety_status != "SAFE":
        action = "IGNORED - UNSAFE"
        return

    # ---------------- PHONE ----------------
    if context == "PHONE":

        if g == "SWIPE RIGHT":
            action = "ACCEPT DETECTED..."
            print("SWIPE RIGHT -> trying WhatsApp ACCEPT")

            if accept_whatsapp_call():
                action = "ACCEPT CALL"
                phone_status = "CALL ACCEPTED"
            else:
                action = "ACCEPT - BUTTON NOT FOUND"
                phone_status = "CALL WAITING"

        elif g == "SWIPE LEFT":
            action = "REJECT DETECTED..."
            print("SWIPE LEFT -> trying WhatsApp REJECT")

            if reject_whatsapp_call():
                action = "REJECT CALL"
                phone_status = "CALL REJECTED"
            else:
                action = "REJECT - BUTTON NOT FOUND"
                phone_status = "CALL WAITING"

        elif g == "PINCH":
            state = toggle_whatsapp_mute()

            if state == "MUTED":
                action = "MUTE CALL"
                phone_status = "CALL MUTED"
            elif state == "UNMUTED":
                action = "UNMUTE CALL"
                phone_status = "CALL UNMUTED"
            else:
                action = "MUTE BUTTON NOT FOUND"

        return

    # ---------------- HOME ----------------
    if context == "HOME":

        if g == "SWIPE RIGHT":
            selected_mode = (selected_mode + 1) % len(modes)
            action = "SELECT " + modes[selected_mode]

        elif g == "SWIPE LEFT":
            selected_mode = (selected_mode - 1) % len(modes)
            action = "SELECT " + modes[selected_mode]

        elif g == "PINCH":
            context = modes[selected_mode]
            action = "ENTER " + context

        return

    # ---------------- MUSIC ----------------
    if context == "MUSIC":

        if g == "SWIPE RIGHT":
            action = "NEXT SONG"
            song_name = "Next Track"
            next_song()

        elif g == "SWIPE LEFT":
            action = "PREVIOUS SONG"
            song_name = "Previous Track"
            previous_song()

        return

    # ---------------- NAVIGATION ----------------
    if context == "NAVIGATION":

        if g == "SWIPE RIGHT":
            navigation_card = min(
                navigation_card + 1,
                len(navigation_cards) - 1
            )
            action = "NEXT NAVIGATION CARD"

        elif g == "SWIPE LEFT":
            navigation_card = max(
                navigation_card - 1,
                0
            )
            action = "PREVIOUS NAVIGATION CARD"

        elif g == "PINCH":
            zoom_level = min(200, zoom_level + 5)
            action = "ZOOM MAP"

# ============================================================
# MAIN LOOP
# ============================================================
while True:

    ret, camera_frame = cap.read()

    if not ret:
        print("ERROR: Could not read camera frame.")
        break

    camera_frame = cv2.flip(camera_frame, 1)

    # Keep camera processing resolution reasonable.
    camera_frame = cv2.resize(
        camera_frame,
        (WINDOW_WIDTH, WINDOW_HEIGHT)
    )

    rgb = cv2.cvtColor(
        camera_frame,
        cv2.COLOR_BGR2RGB
    )

    image = mp.Image(
        image_format=mp.ImageFormat.SRGB,
        data=rgb
    )

    gesture = "OPEN"

    # ========================================================
    # FACE
    # ========================================================
    face_result = face_detector.detect(image)

    driver_present = bool(face_result.face_landmarks)

    if driver_present and face_result.facial_transformation_matrixes:
        matrix = np.array(
            face_result.facial_transformation_matrixes[0]
        )

        rotation = matrix[:3, :3]

        yaw = np.arctan2(
            rotation[1, 0],
            rotation[0, 0]
        )

        yaw_degrees = float(np.degrees(yaw))

        if yaw_degrees > 15:
            head_direction = "LOOKING RIGHT"
        elif yaw_degrees < -15:
            head_direction = "LOOKING LEFT"
        else:
            head_direction = "LOOKING CENTER"

    else:
        head_direction = "NO FACE"
        yaw_degrees = 0

    if not driver_present:
        safety_status = "UNSAFE - NO DRIVER"
    elif head_direction == "LOOKING CENTER":
        safety_status = "SAFE"
    else:
        safety_status = "UNSAFE - LOOKING AWAY"

    # ========================================================
    # HAND
    # ========================================================
    hand_result = hand_detector.detect(image)

    if hand_result.hand_landmarks:

        hand = hand_result.hand_landmarks[0]

        thumb = hand[4]
        index = hand[8]

        h, w, _ = camera_frame.shape

        x = int(index.x * w)
        y = int(index.y * h)

        # Draw fingertip
        cv2.circle(
            camera_frame,
            (x, y),
            9,
            (255, 255, 255),
            -1
        )

        # Thumb-index distance
        dx = thumb.x - index.x
        dy = thumb.y - index.y

        pinch_distance = math.sqrt(
            dx * dx + dy * dy
        )

        current_time = time.time()

        # ====================================================
        # PINCH
        # ====================================================
        if pinch_distance < pinch_threshold:

            gesture = "PINCH"
            swipe_points.clear()

            if (
                current_time - last_pinch_time
                > pinch_cooldown
            ):
                handle_gesture("PINCH")
                last_pinch_time = current_time

            previous_y = index.y

        # ====================================================
        # OPEN HAND / SWIPE
        # ====================================================
        else:

            current_y = index.y
            previous_y = None

            # Store normalized x with timestamp.
            swipe_points.append(
                (current_time, x, y)
            )

            # Remove points older than the swipe window.
            while (
                swipe_points
                and current_time - swipe_points[0][0]
                > SWIPE_WINDOW_SECONDS
            ):
                swipe_points.popleft()

            detected_swipe = None

            if len(swipe_points) >= 5:

                first_time, first_x, first_y = swipe_points[0]
                last_time, last_x, last_y = swipe_points[-1]

                dx_pixels = last_x - first_x
                dy_pixels = abs(last_y - first_y)

                elapsed = last_time - first_time

                if elapsed >= 0.08:

                    # Horizontal movement must dominate.
                    horizontal = (
                        abs(dx_pixels)
                        > max(
                            SWIPE_DISTANCE,
                            dy_pixels * 1.25
                        )
                    )

                    if horizontal:

                        if dx_pixels > 0:
                            detected_swipe = "SWIPE RIGHT"
                        else:
                            detected_swipe = "SWIPE LEFT"

            if detected_swipe is not None:

                if (
                    current_time - last_swipe_time
                    > swipe_cooldown
                ):

                    gesture = detected_swipe

                    print(
                        f"{detected_swipe} detected"
                    )

                    handle_gesture(detected_swipe)

                    last_swipe_time = current_time

                    swipe_points.clear()

            # If no swipe yet, show OPEN.
            elif gesture != "PINCH":
                gesture = "OPEN"

    else:
        swipe_points.clear()
        previous_y = None
        gesture = "NO HAND"

    # ========================================================
    # VOLUME
    # ========================================================
    system_volume = volume_control.GetMasterVolumeLevelScalar()
    volume = int(system_volume * 100)

    # ========================================================
    # KEYBOARD CONTROLS
    # ========================================================
    key = cv2.waitKey(1) & 0xFF

    if key == ord("q"):
        break

    elif key == ord("h"):
        context = "HOME"
        action = "HOME"
        swipe_points.clear()

    elif key == ord("m"):
        context = "MUSIC"
        action = "MUSIC MODE"
        swipe_points.clear()

    elif key == ord("p"):
        context = "PHONE"
        action = "PHONE MODE"
        phone_status = "CALL WAITING"
        swipe_points.clear()

    elif key == ord("n"):
        context = "NAVIGATION"
        action = "NAVIGATION MODE"
        swipe_points.clear()

    # ========================================================
    # DASHBOARD
    # ========================================================
    dashboard = np.full(
        (WINDOW_HEIGHT, WINDOW_WIDTH, 3),
        BG,
        dtype=np.uint8
    )

    # Top bar
    cv2.rectangle(
        dashboard,
        (0, 0),
        (WINDOW_WIDTH, 75),
        (17, 22, 29),
        -1
    )

    cv2.line(
        dashboard,
        (25, 74),
        (1255, 74),
        ACCENT,
        2
    )

    text(
        dashboard,
        "DRIVEGESTURE AI",
        30,
        48,
        1.0,
        2
    )

    text(
        dashboard,
        "TOUCHLESS VEHICLE HMI",
        310,
        46,
        0.55,
        1
    )

    cv2.rectangle(
        dashboard,
        (760, 18),
        (980, 58),
        CARD_BG,
        -1
    )

    text(
        dashboard,
        "MODE  " + context,
        780,
        45,
        0.52,
        2,
        ACCENT
    )

    dot_color = SUCCESS if driver_present else DANGER

    cv2.circle(
        dashboard,
        (1040, 40),
        7,
        dot_color,
        -1
    )

    text(
        dashboard,
        "DRIVER ACTIVE" if driver_present else "NO DRIVER",
        1052,
        45,
        0.6,
        2,
        TEXT if driver_present else DANGER
    )

    # Left camera panel
    rounded_panel(
        dashboard,
        25, 95, 590, 565
    )

    text(
        dashboard,
        "DRIVER MONITOR",
        50,
        130,
        0.72,
        2
    )

    text(
        dashboard,
        "CAMERA + ATTENTION",
        50,
        155,
        0.42,
        1
    )

    small_camera = cv2.resize(
        camera_frame,
        (530, 350)
    )

    dashboard[
        160:510,
        45:575
    ] = small_camera

    cv2.rectangle(
        dashboard,
        (45, 160),
        (575, 510),
        ACCENT,
        2
    )

    # Right panel
    rounded_panel(
        dashboard,
        615, 95, 1255, 565
    )

    if context == "HOME":
        draw_home_panel(dashboard)

    elif context == "MUSIC":
        draw_music_panel(dashboard, volume)

    elif context == "PHONE":
        draw_phone_panel(dashboard)

    elif context == "NAVIGATION":
        draw_navigation_panel(dashboard)

    # Bottom status
    cv2.rectangle(
        dashboard,
        (25, 585),
        (1255, 690),
        (17, 22, 29),
        -1
    )

    cv2.line(
        dashboard,
        (25, 585),
        (1255, 585),
        PANEL_BORDER,
        1
    )

    text(dashboard, "GESTURE", 50, 615, 0.45, 1)
    text(dashboard, gesture, 50, 655, 0.6, 2)

    text(dashboard, "SAFETY", 350, 615, 0.45, 1)
    text(
        dashboard,
        safety_status,
        350,
        655,
        0.55,
        2,
        SUCCESS if safety_status == "SAFE" else DANGER
    )

    text(dashboard, "ACTION", 750, 615, 0.45, 1)
    text(dashboard, action, 750, 655, 0.55, 2)

    text(dashboard, "SPEED", 1080, 615, 0.45, 1)
    text(dashboard, f"{speed} km/h", 1080, 655, 0.6, 2)

    text(
        dashboard,
        "H HOME    M MUSIC    P PHONE    N NAVIGATION    Q QUIT",
        350,
        710,
        0.42,
        1
    )

    cv2.imshow(
        "DriveGesture AI - Vehicle HMI",
        dashboard
    )

# ============================================================
# CLEANUP
# ============================================================
cap.release()
cv2.destroyAllWindows()

try:
    hand_detector.close()
except Exception:
    pass

try:
    face_detector.close()
except Exception:
    pass

print("DriveGesture AI stopped.")
