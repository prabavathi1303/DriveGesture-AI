import cv2
import mediapipe as mp
import math
import ctypes
import time
from collections import deque
import numpy as np

from mediapipe.tasks import python
from mediapipe.tasks.python import vision
from pycaw.pycaw import AudioUtilities

# Optional Windows UI automation for WhatsApp call controls
try:
    from pywinauto import Desktop
    WHATSAPP_AUTOMATION_AVAILABLE = True
except ImportError:
    WHATSAPP_AUTOMATION_AVAILABLE = False


# =========================================================
# WINDOWS VOLUME
# =========================================================

devices = AudioUtilities.GetSpeakers()
volume_control = devices.EndpointVolume
system_volume = volume_control.GetMasterVolumeLevelScalar()


# =========================================================
# WINDOWS MEDIA CONTROLS
# =========================================================

def next_song():

    ctypes.windll.user32.keybd_event(0xB0, 0, 0, 0)
    ctypes.windll.user32.keybd_event(0xB0, 0, 2, 0)


def previous_song():

    ctypes.windll.user32.keybd_event(0xB1, 0, 0, 0)
    ctypes.windll.user32.keybd_event(0xB1, 0, 2, 0)


# =========================================================
# WHATSAPP WINDOWS CONTROL
# =========================================================
# WhatsApp Desktop may NOT expose the incoming-call buttons to
# Windows UI Automation. Therefore we use two methods:
#   1. UI Automation when the button is exposed.
#   2. A Windows API fallback that finds the WhatsApp window and
#      clicks the button using coordinates RELATIVE to that window.
#
# This is NOT a fixed screen coordinate. It works even when the
# WhatsApp window is moved or resized.
# =========================================================

try:
    from pywinauto import Desktop
    WHATSAPP_AUTOMATION_AVAILABLE = True
except ImportError:
    WHATSAPP_AUTOMATION_AVAILABLE = False

import ctypes

user32 = ctypes.windll.user32

WHATSAPP_WINDOW_RE = r"(?i).*WhatsApp.*"


def _get_whatsapp_windows():

    if not WHATSAPP_AUTOMATION_AVAILABLE:
        return []

    try:
        windows = Desktop(backend="uia").windows(
            title_re=WHATSAPP_WINDOW_RE,
            visible_only=True
        )

        result = []

        for window in windows:
            try:
                if window.is_visible():
                    result.append(window)
            except Exception:
                pass

        return result

    except Exception:
        return []


def _button_label(button):

    labels = []

    try:
        value = button.window_text()
        if value:
            labels.append(str(value).strip().lower())
    except Exception:
        pass

    try:
        value = button.element_info.name
        if value:
            labels.append(str(value).strip().lower())
    except Exception:
        pass

    try:
        value = button.element_info.automation_id
        if value:
            labels.append(str(value).strip().lower())
    except Exception:
        pass

    return list(dict.fromkeys(labels))


def _find_whatsapp_button(names):

    wanted = [str(x).lower() for x in names]

    for window in _get_whatsapp_windows():

        try:
            buttons = window.descendants(control_type="Button")
        except Exception:
            continue

        for button in buttons:

            labels = _button_label(button)

            for label in labels:
                for wanted_name in wanted:
                    if wanted_name == label or wanted_name in label:
                        return window, button

    return None, None


def _click_control(window, button):

    try:
        window.set_focus()
    except Exception:
        pass

    time.sleep(0.15)

    try:
        button.click_input()
        return True
    except Exception:
        pass

    try:
        button.click()
        return True
    except Exception:
        return False


def _largest_whatsapp_window():
    """Return the largest visible WhatsApp window."""

    windows = _get_whatsapp_windows()

    if not windows:
        return None

    best = None
    best_area = -1

    for window in windows:

        try:
            rect = window.rectangle()
            width = max(1, rect.width())
            height = max(1, rect.height())
            area = width * height

            if area > best_area:
                best_area = area
                best = window

        except Exception:
            pass

    return best


def _windows_api_click(x, y):
    """Perform a real left mouse click using Windows API."""

    try:
        user32.SetCursorPos(int(x), int(y))
        time.sleep(0.08)

        MOUSEEVENTF_LEFTDOWN = 0x0002
        MOUSEEVENTF_LEFTUP = 0x0004

        user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        time.sleep(0.05)
        user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)

        return True

    except Exception:
        return False


def _click_relative_to_whatsapp(x_ratio, y_ratio):
    """Click a location relative to the actual WhatsApp window."""

    window = _largest_whatsapp_window()

    if window is None:
        return False

    try:
        rect = window.rectangle()

        # Put WhatsApp in the foreground first.
        try:
            window.set_focus()
        except Exception:
            pass

        time.sleep(0.20)

        x = int(rect.left + rect.width() * x_ratio)
        y = int(rect.top + rect.height() * y_ratio)

        return _windows_api_click(x, y)

    except Exception:
        return False


def _click_relative_candidates(candidates):
    """Try several relative positions for different WhatsApp layouts."""

    for x_ratio, y_ratio in candidates:
        if _click_relative_to_whatsapp(x_ratio, y_ratio):
            return True

    return False


def accept_whatsapp_call():

    # Method 1: UI Automation.
    window, button = _find_whatsapp_button([
        "accept",
        "accept call",
        "answer",
        "answer call"
    ])

    if window is not None and button is not None:
        if _click_control(window, button):
            return True

    # Method 2: Windows API fallback.
    # In the WhatsApp layout shown in your screenshot, the green
    # Accept button is approximately at the bottom-center.
    # We try several nearby positions to handle small UI changes.
    return _click_relative_candidates([
        (0.52, 0.925),
        (0.50, 0.915),
        (0.55, 0.925)
    ])


def reject_whatsapp_call():

    # Method 1: UI Automation.
    window, button = _find_whatsapp_button([
        "decline",
        "decline call",
        "reject",
        "reject call",
        "end call",
        "hang up"
    ])

    if window is not None and button is not None:
        if _click_control(window, button):
            return True

    # Method 2: Windows API fallback.
    # Red Reject button is approximately at the bottom-right.
    return _click_relative_candidates([
        (0.90, 0.925),
        (0.89, 0.915),
        (0.92, 0.925)
    ])


def toggle_whatsapp_mute():

    window, button = _find_whatsapp_button([
        "mute",
        "mute microphone",
        "mute mic"
    ])

    if window is not None and button is not None:
        if _click_control(window, button):
            return "MUTED"

    window, button = _find_whatsapp_button([
        "unmute",
        "unmute microphone",
        "unmute mic"
    ])

    if window is not None and button is not None:
        if _click_control(window, button):
            return "UNMUTED"

    # Mute button in the shown layout is approximately center-bottom,
    # above the Accept/Reject row.
    if _click_relative_candidates([
        (0.50, 0.805),
        (0.50, 0.80)
    ]):
        return "MUTE BUTTON CLICKED"

    return None


# =========================================================
# HAND DETECTOR
# =========================================================

hand_model = "models/hand_landmarker.task"

hand_base = python.BaseOptions(
    model_asset_path=hand_model
)

hand_options = vision.HandLandmarkerOptions(
    base_options=hand_base,
    num_hands=1
)

hand_detector = vision.HandLandmarker.create_from_options(
    hand_options
)


# =========================================================
# FACE DETECTOR
# =========================================================

face_model = "models/face_landmarker.task"

face_base = python.BaseOptions(
    model_asset_path=face_model
)

face_options = vision.FaceLandmarkerOptions(
    base_options=face_base,
    num_faces=1,
    output_facial_transformation_matrixes=True
)

face_detector = vision.FaceLandmarker.create_from_options(
    face_options
)


# =========================================================
# CAMERA
# =========================================================

cap = cv2.VideoCapture(0)

if not cap.isOpened():

    print("ERROR: Camera could not be opened.")
    exit()


# =========================================================
# WINDOW
# =========================================================

WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 720

# =========================================================
# MODERN UI THEME
# =========================================================

BG = (12, 16, 22)
PANEL_BG = (22, 28, 36)
PANEL_BORDER = (55, 68, 82)
CARD_BG = (28, 36, 46)
TEXT = (235, 242, 248)
MUTED = (145, 158, 172)
ACCENT = (255, 190, 70)
SUCCESS = (100, 220, 150)
DANGER = (100, 100, 240)
INFO = (220, 180, 80)
ROAD = (58, 68, 80)
ROAD_MAIN = (78, 90, 105)

def rounded_panel(img, x1, y1, x2, y2, fill=PANEL_BG, border=PANEL_BORDER, radius=18, thickness=1):
    cv2.rectangle(img, (x1 + radius, y1), (x2 - radius, y2), fill, -1)
    cv2.rectangle(img, (x1, y1 + radius), (x2, y2 - radius), fill, -1)
    cv2.circle(img, (x1 + radius, y1 + radius), radius, fill, -1)
    cv2.circle(img, (x2 - radius, y1 + radius), radius, fill, -1)
    cv2.circle(img, (x1 + radius, y2 - radius), radius, fill, -1)
    cv2.circle(img, (x2 - radius, y2 - radius), radius, fill, -1)
    cv2.rectangle(img, (x1 + radius, y1), (x2 - radius, y2), border, thickness)
    cv2.rectangle(img, (x1, y1 + radius), (x2, y2 - radius), border, thickness)
    cv2.ellipse(img, (x1 + radius, y1 + radius), (radius, radius), 180, 0, 90, border, thickness)
    cv2.ellipse(img, (x2 - radius, y1 + radius), (radius, radius), 270, 0, 90, border, thickness)
    cv2.ellipse(img, (x1 + radius, y2 - radius), (radius, radius), 90, 0, 90, border, thickness)
    cv2.ellipse(img, (x2 - radius, y2 - radius), (radius, radius), 0, 0, 90, border, thickness)

def status_dot(img, x, y, good):
    cv2.circle(img, (x, y), 7, SUCCESS if good else DANGER, -1)

def section_title(img, title, subtitle, x, y):
    text(img, title, x, y, 0.72, 2)
    text(img, subtitle, x, y + 28, 0.42, 1)


# =========================================================
# MODES
# =========================================================

modes = [
    "MUSIC",
    "PHONE",
    "NAVIGATION"
]

selected_mode = 0

context = "HOME"


# =========================================================
# NAVIGATION
# =========================================================

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


# =========================================================
# MUSIC
# =========================================================

song_name = "Drive Mode"
artist_name = "DriveGesture Player"


# =========================================================
# PHONE
# =========================================================

phone_status = "NO ACTIVE CALL"


# =========================================================
# VEHICLE
# =========================================================

speed = 42


# =========================================================
# GESTURE VARIABLES
# =========================================================

positions = deque(maxlen=12)

previous_y = None

pinch_threshold = 0.05

swipe_distance = 80

last_swipe_time = 0

swipe_cooldown = 1.0

last_pinch_time = 0

pinch_cooldown = 1.0


# =========================================================
# SYSTEM VARIABLES
# =========================================================

gesture = "NO GESTURE"

head_direction = "NO FACE"

yaw_degrees = 0

driver_present = False

safety_status = "UNSAFE - NO DRIVER"

action = "WAITING"


# =========================================================
# TEXT FUNCTION
# =========================================================

def text(
    img,
    message,
    x,
    y,
    size=0.7,
    thickness=2,
    color=TEXT
):

    cv2.putText(
        img,
        message,
        (x, y),
        cv2.FONT_HERSHEY_SIMPLEX,
        size,
        color,
        thickness,
        cv2.LINE_AA
    )


# =========================================================
# PANEL
# =========================================================

def panel(
    img,
    x1,
    y1,
    x2,
    y2
):

    rounded_panel(
        img,
        x1,
        y1,
        x2,
        y2,
        PANEL_BG,
        PANEL_BORDER,
        18,
        1
    )


# =========================================================
# MAP
# =========================================================

def draw_map(
    img,
    x1,
    y1,
    x2,
    y2,
    card,
    zoom
):

    # Background

    cv2.rectangle(
        img,
        (x1, y1),
        (x2, y2),
        (18, 24, 31),
        -1
    )


    # Main horizontal road

    cv2.line(
        img,
        (x1, y1 + 250),
        (x2, y1 + 250),
        ROAD_MAIN,
        45
    )


    # Main vertical road

    cv2.line(
        img,
        (x1 + 250, y1),
        (x1 + 250, y2),
        ROAD_MAIN,
        45
    )


    # Diagonal road

    cv2.line(
        img,
        (x1 + 100, y2 - 50),
        (x2 - 80, y1 + 80),
        ROAD,
        30
    )


    # Small roads

    cv2.line(
        img,
        (x1 + 50, y1 + 100),
        (x2 - 50, y1 + 100),
        ROAD,
        15
    )

    cv2.line(
        img,
        (x1 + 100, y2 - 100),
        (x2 - 50, y2 - 100),
        ROAD,
        15
    )


    # =====================================================
    # ROUTE
    # =====================================================

    if card == 0:

        route_points = np.array([
            [x1 + 80, y2 - 80],
            [x1 + 250, y2 - 80],
            [x1 + 250, y1 + 250],
            [x2 - 100, y1 + 250]
        ], np.int32)


    elif card == 1:

        route_points = np.array([
            [x1 + 80, y2 - 80],
            [x1 + 250, y2 - 80],
            [x1 + 250, y1 + 100],
            [x2 - 100, y1 + 100]
        ], np.int32)


    elif card == 2:

        route_points = np.array([
            [x1 + 80, y2 - 80],
            [x1 + 250, y2 - 80],
            [x1 + 250, y1 + 250],
            [x1 + 450, y1 + 250],
            [x1 + 450, y1 + 100]
        ], np.int32)


    else:

        route_points = np.array([
            [x1 + 80, y2 - 80],
            [x1 + 250, y2 - 80],
            [x1 + 250, y1 + 250],
            [x2 - 120, y1 + 250],
            [x2 - 120, y1 + 100]
        ], np.int32)


    cv2.polylines(
        img,
        [route_points],
        False,
        (255, 255, 255),
        8
    )


    # =====================================================
    # DESTINATION
    # =====================================================

    destination_x = x2 - 120
    destination_y = y1 + 100

    cv2.circle(
        img,
        (destination_x, destination_y),
        16,
        ACCENT,
        -1
    )

    text(
        img,
        "DESTINATION",
        destination_x - 70,
        destination_y - 25,
        0.45,
        1
    )


    # =====================================================
    # CAR
    # =====================================================

    car_x = x1 + 80
    car_y = y2 - 80

    cv2.circle(
        img,
        (car_x, car_y),
        20,
        ACCENT,
        -1
    )

    cv2.arrowedLine(
        img,
        (car_x, car_y),
        (car_x + 45, car_y),
        (255, 255, 255),
        5,
        tipLength=0.35
    )

    text(
        img,
        "YOU",
        car_x - 15,
        car_y + 45,
        0.45,
        1
    )


    # Zoom

    text(
        img,
        f"ZOOM {zoom}%",
        x1 + 20,
        y2 - 20,
        0.5,
        1
    )


# =========================================================
# MAIN LOOP
# =========================================================

while True:

    # =====================================================
    # CAMERA
    # =====================================================

    ret, camera_frame = cap.read()

    if not ret:

        print("ERROR: Could not read camera frame.")
        break


    camera_frame = cv2.flip(
        camera_frame,
        1
    )

    camera_frame = cv2.resize(
        camera_frame,
        (WINDOW_WIDTH, WINDOW_HEIGHT)
    )


    # =====================================================
    # MEDIAPIPE IMAGE
    # =====================================================

    rgb = cv2.cvtColor(
        camera_frame,
        cv2.COLOR_BGR2RGB
    )

    image = mp.Image(
        image_format=mp.ImageFormat.SRGB,
        data=rgb
    )


    # =====================================================
    # RESET
    # =====================================================

    gesture = "NO GESTURE"

    head_direction = "NO FACE"

    yaw_degrees = 0

    driver_present = False


    # =====================================================
    # FACE
    # =====================================================

    face_result = face_detector.detect(image)


    if face_result.face_landmarks:

        driver_present = True

        matrix = face_result.facial_transformation_matrixes[0]

        matrix = np.array(matrix)

        rotation = matrix[:3, :3]

        yaw = np.arctan2(
            rotation[1, 0],
            rotation[0, 0]
        )

        yaw_degrees = np.degrees(yaw)


        if yaw_degrees > 15:

            head_direction = "LOOKING RIGHT"

        elif yaw_degrees < -15:

            head_direction = "LOOKING LEFT"

        else:

            head_direction = "LOOKING CENTER"


    # =====================================================
    # SAFETY
    # =====================================================

    if not driver_present:

        safety_status = "UNSAFE - NO DRIVER"

    elif head_direction == "LOOKING CENTER":

        safety_status = "SAFE"

    else:

        safety_status = "UNSAFE - LOOKING AWAY"


    # =====================================================
    # HAND
    # =====================================================

    hand_result = hand_detector.detect(image)


    if hand_result.hand_landmarks:

        hand = hand_result.hand_landmarks[0]

        thumb = hand[4]

        index = hand[8]

        height, width, _ = camera_frame.shape

        x = int(index.x * width)

        y = int(index.y * height)


        cv2.circle(
            camera_frame,
            (x, y),
            8,
            (255, 255, 255),
            -1
        )


        # =================================================
        # PINCH DISTANCE
        # =================================================

        dx = thumb.x - index.x

        dy = thumb.y - index.y

        distance = math.sqrt(
            dx * dx + dy * dy
        )


        # =================================================
        # PINCH
        # =================================================

        if distance < pinch_threshold:

            current_time = time.time()

            gesture = "PINCH"

            current_y = index.y


            # Prevent repeated mode selection

            if (
                current_time - last_pinch_time
                > pinch_cooldown
            ):

                # =========================================
                # HOME
                # =========================================

                if context == "HOME":

                    if safety_status == "SAFE":

                        context = modes[selected_mode]

                        action = (
                            "ENTER " +
                            context
                        )

                        last_pinch_time = current_time

                    else:

                        action = "IGNORED - UNSAFE"


                # =========================================
                # MUSIC
                # =========================================

                elif context == "MUSIC":

                    if safety_status == "SAFE":

                        action = "VOLUME CONTROL"

                    else:

                        action = "IGNORED - UNSAFE"


                # =========================================
                # NAVIGATION
                # =========================================

                elif context == "NAVIGATION":

                    if safety_status == "SAFE":

                        action = "ZOOM MAP"

                    else:

                        action = "IGNORED - UNSAFE"


                # =========================================
                # PHONE
                # =========================================

                elif context == "PHONE":

                    if safety_status == "SAFE":

                        mute_state = toggle_whatsapp_mute()

                        if mute_state == "MUTED":
                            action = "MUTE CALL"
                            phone_status = "CALL MUTED"
                        elif mute_state == "UNMUTED":
                            action = "UNMUTE CALL"
                            phone_status = "CALL UNMUTED"
                        else:
                            action = "MUTE BUTTON NOT FOUND"

                    else:

                        action = "IGNORED - UNSAFE"


            # =================================================
            # VOLUME / ZOOM CONTINUOUS
            # =================================================

            if context == "MUSIC":

                if safety_status == "SAFE":

                    if previous_y is not None:

                        movement = previous_y - current_y


                        if movement > 0.01:

                            system_volume += 0.02

                            system_volume = min(
                                1.0,
                                system_volume
                            )

                            volume_control.SetMasterVolumeLevelScalar(
                                system_volume,
                                None
                            )


                        elif movement < -0.01:

                            system_volume -= 0.02

                            system_volume = max(
                                0.0,
                                system_volume
                            )

                            volume_control.SetMasterVolumeLevelScalar(
                                system_volume,
                                None
                            )


                    previous_y = current_y

                else:

                    previous_y = None


            elif context == "NAVIGATION":

                if safety_status == "SAFE":

                    if previous_y is not None:

                        movement = previous_y - current_y


                        if movement > 0.01:

                            zoom_level += 5

                            zoom_level = min(
                                200,
                                zoom_level
                            )


                        elif movement < -0.01:

                            zoom_level -= 5

                            zoom_level = max(
                                50,
                                zoom_level
                            )


                    previous_y = current_y

                else:

                    previous_y = None


            else:

                previous_y = None


            positions.clear()


        # =================================================
        # OPEN HAND / SWIPE
        # =================================================

        else:

            previous_y = None

            positions.append(
                (x, y)
            )


            if len(positions) >= 5:

                first_x = positions[0][0]

                last_x = positions[-1][0]

                first_y = positions[0][1]

                last_y = positions[-1][1]


                difference_x = last_x - first_x

                difference_y = abs(
                    last_y - first_y
                )


                current_time = time.time()


                if (
                    current_time - last_swipe_time
                    > swipe_cooldown
                ):

                    if (
                        difference_x > swipe_distance
                        and
                        abs(difference_x)
                        > difference_y * 1.5
                    ):

                        gesture = "SWIPE RIGHT"

                        positions.clear()

                        last_swipe_time = current_time


                    elif (
                        difference_x < -swipe_distance
                        and
                        abs(difference_x)
                        > difference_y * 1.5
                    ):

                        gesture = "SWIPE LEFT"

                        positions.clear()

                        last_swipe_time = current_time


                    else:

                        gesture = "OPEN"

                else:

                    gesture = "OPEN"


    else:

        positions.clear()

        previous_y = None


    # =====================================================
    # GET VOLUME
    # =====================================================

    system_volume = (
        volume_control.GetMasterVolumeLevelScalar()
    )

    volume = int(
        system_volume * 100
    )


    # =====================================================
    # HOME GESTURES
    # =====================================================

    if context == "HOME":

        if gesture == "SWIPE RIGHT":

            if safety_status == "SAFE":

                selected_mode += 1

                if selected_mode >= len(modes):

                    selected_mode = 0

                action = (
                    "SELECT " +
                    modes[selected_mode]
                )

            else:

                action = "IGNORED - UNSAFE"


        elif gesture == "SWIPE LEFT":

            if safety_status == "SAFE":

                selected_mode -= 1

                if selected_mode < 0:

                    selected_mode = len(modes) - 1

                action = (
                    "SELECT " +
                    modes[selected_mode]
                )

            else:

                action = "IGNORED - UNSAFE"


    # =====================================================
    # MUSIC ACTIONS
    # =====================================================

    elif context == "MUSIC":

        if gesture == "SWIPE RIGHT":

            if safety_status == "SAFE":

                action = "NEXT SONG"

                next_song()

            else:

                action = "IGNORED - UNSAFE"


        elif gesture == "SWIPE LEFT":

            if safety_status == "SAFE":

                action = "PREVIOUS SONG"

                previous_song()

            else:

                action = "IGNORED - UNSAFE"


        elif gesture == "PINCH":

            if safety_status == "SAFE":

                action = "VOLUME CONTROL"

            else:

                action = "IGNORED - UNSAFE"


    # =====================================================
    # PHONE ACTIONS
    # =====================================================

    elif context == "PHONE":

        if gesture == "SWIPE RIGHT":

            if safety_status == "SAFE":

                if accept_whatsapp_call():
                    action = "ACCEPT CALL"
                    phone_status = "CALL ACCEPTED"
                else:
                    action = "ACCEPT DETECTED - BUTTON NOT FOUND"
                    phone_status = "CALL WAITING"

            else:

                action = "IGNORED - UNSAFE"


        elif gesture == "SWIPE LEFT":

            if safety_status == "SAFE":

                if reject_whatsapp_call():
                    action = "REJECT CALL"
                    phone_status = "CALL REJECTED"
                else:
                    action = "REJECT DETECTED - BUTTON NOT FOUND"
                    phone_status = "CALL WAITING"

            else:

                action = "IGNORED - UNSAFE"


        elif gesture == "PINCH":

            if safety_status == "SAFE":

                mute_state = toggle_whatsapp_mute()

                if mute_state == "MUTED":
                    action = "MUTE CALL"
                    phone_status = "CALL MUTED"
                elif mute_state == "UNMUTED":
                    action = "UNMUTE CALL"
                    phone_status = "CALL UNMUTED"
                else:
                    action = "MUTE BUTTON NOT FOUND"

            else:

                action = "IGNORED - UNSAFE"


    # =====================================================
    # NAVIGATION ACTIONS
    # =====================================================

    elif context == "NAVIGATION":

        if gesture == "SWIPE RIGHT":

            if safety_status == "SAFE":

                if navigation_card < len(navigation_cards) - 1:

                    navigation_card += 1

                action = "NEXT NAVIGATION CARD"

            else:

                action = "IGNORED - UNSAFE"


        elif gesture == "SWIPE LEFT":

            if safety_status == "SAFE":

                if navigation_card > 0:

                    navigation_card -= 1

                action = "PREVIOUS NAVIGATION CARD"

            else:

                action = "IGNORED - UNSAFE"


        elif gesture == "PINCH":

            if safety_status == "SAFE":

                action = "ZOOM MAP"

            else:

                action = "IGNORED - UNSAFE"


    # =====================================================
    # KEYBOARD BACKUP
    # =====================================================

    key = cv2.waitKey(1) & 0xFF


    if key == ord("h"):

        context = "HOME"

        action = "HOME"


    elif key == ord("m"):

        context = "MUSIC"

        action = "MUSIC MODE"


    elif key == ord("p"):

        context = "PHONE"

        action = "PHONE MODE"


    elif key == ord("n"):

        context = "NAVIGATION"

        action = "NAVIGATION MODE"


    elif key == ord("q"):

        break


    # =====================================================
    # DASHBOARD
    # =====================================================

    dashboard = np.full(
        (
            WINDOW_HEIGHT,
            WINDOW_WIDTH,
            3
        ),
        BG,
        dtype=np.uint8
    )


    # =====================================================
    # TOP BAR
    # =====================================================

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
        2,
        TEXT
    )


    text(
        dashboard,
        "TOUCHLESS VEHICLE HMI",
        310,
        46,
        0.55,
        1
    )


    # Active mode badge
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

    if driver_present:

        status_dot(dashboard, 1040, 40, True)

        text(
            dashboard,
            "DRIVER ACTIVE",
            1050,
            45,
            0.6,
            2
        )

    else:

        status_dot(dashboard, 1068, 40, False)

        text(
            dashboard,
            "NO DRIVER",
            1080,
            45,
            0.6,
            2,
            DANGER
        )


    # =====================================================
    # LEFT CAMERA
    # =====================================================

    panel(
        dashboard,
        25,
        95,
        590,
        565
    )


    section_title(
        dashboard,
        "DRIVER MONITOR",
        "CAMERA + ATTENTION",
        50,
        130
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


    # =====================================================
    # RIGHT PANEL
    # =====================================================

    panel(
        dashboard,
        615,
        95,
        1255,
        565
    )


    # =====================================================
    # HOME SCREEN
    # =====================================================

    if context == "HOME":

        text(
            dashboard,
            "SELECT MODE",
            655,
            155,
            0.8,
            2
        )


        # -------------------------------------------------
        # MODE BOXES
        # -------------------------------------------------

        box_x = [
            655,
            850,
            1045
        ]

        box_names = [
            "MUSIC",
            "PHONE",
            "NAVIGATION"
        ]


        for i in range(3):

            x1 = box_x[i]

            x2 = x1 + 165


            if i == selected_mode:

                cv2.rectangle(
                    dashboard,
                    (x1, 210),
                    (x2, 330),
                    (100, 100, 100),
                    -1
                )

                cv2.rectangle(
                    dashboard,
                    (x1, 210),
                    (x2, 330),
                    (255, 255, 255),
                    3
                )

            else:

                cv2.rectangle(
                    dashboard,
                    (x1, 210),
                    (x2, 330),
                    (55, 55, 55),
                    -1
                )

                cv2.rectangle(
                    dashboard,
                    (x1, 210),
                    (x2, 330),
                    PANEL_BORDER,
                    2
                )


            text(
                dashboard,
                box_names[i],
                x1 + 25,
                275,
                0.65,
                2
            )


            if i == selected_mode:

                text(
                    dashboard,
                    "SELECTED",
                    x1 + 32,
                    305,
                    0.42,
                    1
                )


        # -------------------------------------------------
        # INSTRUCTIONS
        # -------------------------------------------------

        text(
            dashboard,
            "SWIPE RIGHT  →  NEXT MODE",
            700,
            390,
            0.55,
            1
        )


        text(
            dashboard,
            "SWIPE LEFT   ←  PREVIOUS MODE",
            700,
            430,
            0.55,
            1
        )


        text(
            dashboard,
            "PINCH             SELECT",
            700,
            470,
            0.55,
            1
        )


        text(
            dashboard,
            "Selected: " + modes[selected_mode],
            700,
            525,
            0.65,
            2
        )


    # =====================================================
    # MUSIC SCREEN
    # =====================================================

    elif context == "MUSIC":

        text(
            dashboard,
            "MUSIC",
            655,
            155,
            0.8,
            2
        )


        text(
            dashboard,
            "NOW PLAYING",
            655,
            215,
            0.55,
            1
        )


        text(
            dashboard,
            song_name,
            655,
            270,
            1.0,
            2
        )


        text(
            dashboard,
            artist_name,
            655,
            310,
            0.6,
            1
        )


        text(
            dashboard,
            f"VOLUME  {volume}%",
            655,
            375,
            0.7,
            2
        )


        cv2.rectangle(
            dashboard,
            (655, 400),
            (1190, 425),
            (80, 80, 80),
            -1
        )


        volume_width = int(
            535 * volume / 100
        )


        cv2.rectangle(
            dashboard,
            (655, 400),
            (655 + volume_width, 425),
            (255, 255, 255),
            -1
        )


        text(
            dashboard,
            "Swipe ← / →  Change Track",
            655,
            475,
            0.55,
            1
        )


        text(
            dashboard,
            "Pinch ↑ / ↓  Volume",
            655,
            510,
            0.55,
            1
        )


        text(
            dashboard,
            "H = HOME",
            1050,
            510,
            0.45,
            1
        )


    # =====================================================
    # PHONE SCREEN
    # =====================================================

    elif context == "PHONE":

        text(
            dashboard,
            "PHONE",
            655,
            155,
            0.8,
            2
        )


        text(
            dashboard,
            "IN-CAR CALL",
            655,
            230,
            1.0,
            2
        )


        text(
            dashboard,
            phone_status,
            655,
            280,
            0.65,
            2
        )


        text(
            dashboard,
            "Swipe Right  → Accept",
            655,
            365,
            0.55,
            1
        )


        text(
            dashboard,
            "Swipe Left   → Reject",
            655,
            405,
            0.55,
            1
        )


        text(
            dashboard,
            "Pinch → Mute",
            655,
            445,
            0.55,
            1
        )


        text(
            dashboard,
            "H = HOME",
            1050,
            510,
            0.45,
            1
        )


    # =====================================================
    # NAVIGATION SCREEN
    # =====================================================

    elif context == "NAVIGATION":

        text(
            dashboard,
            "NAVIGATION",
            655,
            135,
            0.7,
            2
        )


        # Map

        draw_map(
            dashboard,
            645,
            155,
            925,
            525,
            navigation_card,
            zoom_level
        )


        # Instruction panel

        panel(
            dashboard,
            945,
            155,
            1225,
            525
        )

        cv2.line(
            dashboard,
            (970, 205),
            (1200, 205),
            ACCENT,
            2
        )


        text(
            dashboard,
            "NEXT TURN",
            975,
            190,
            0.5,
            1
        )


        if navigation_card == 0:

            symbol = "→"

        elif navigation_card == 1:

            symbol = "↑"

        elif navigation_card == 2:

            symbol = "←"

        else:

            symbol = "★"


        text(
            dashboard,
            symbol,
            1025,
            275,
            2.0,
            3
        )


        text(
            dashboard,
            navigation_cards[navigation_card],
            975,
            325,
            0.6,
            2
        )


        text(
            dashboard,
            navigation_distance[navigation_card],
            975,
            365,
            0.8,
            2
        )


        text(
            dashboard,
            f"CARD {navigation_card + 1} / 4",
            975,
            415,
            0.5,
            1
        )


        text(
            dashboard,
            "Swipe ← / →",
            975,
            460,
            0.5,
            1
        )


        text(
            dashboard,
            "Pinch = Zoom",
            975,
            490,
            0.5,
            1
        )


    # =====================================================
    # BOTTOM STATUS BAR
    # =====================================================

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


    text(
        dashboard,
        "GESTURE",
        50,
        615,
        0.45,
        1
    )


    text(
        dashboard,
        gesture,
        50,
        655,
        0.6,
        2
    )


    text(
        dashboard,
        "SAFETY",
        350,
        615,
        0.45,
        1
    )


    text(
        dashboard,
        safety_status,
        350,
        655,
        0.55,
        2,
        SUCCESS if safety_status == "SAFE" else DANGER
    )


    text(
        dashboard,
        "ACTION",
        750,
        615,
        0.45,
        1
    )


    text(
        dashboard,
        action,
        750,
        655,
        0.6,
        2
    )


    text(
        dashboard,
        "SPEED",
        1080,
        615,
        0.45,
        1
    )


    text(
        dashboard,
        f"{speed} km/h",
        1080,
        655,
        0.6,
        2
    )


    # =====================================================
    # CONTROLS
    # =====================================================

    text(
        dashboard,
        "H HOME     M MUSIC     P PHONE     N NAVIGATION     Q QUIT",
        350,
        710,
        0.42,
        1
    )


    # =====================================================
    # DISPLAY
    # =====================================================

    cv2.imshow(
        "DriveGesture AI - Vehicle HMI",
        dashboard
    )


# =========================================================
# CLEANUP
# =========================================================

cap.release()

cv2.destroyAllWindows()