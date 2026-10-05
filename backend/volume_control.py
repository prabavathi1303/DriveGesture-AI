import cv2
import mediapipe as mp
import math

from mediapipe.tasks import python
from mediapipe.tasks.python import vision


# -----------------------------
# MediaPipe Hand Landmarker
# -----------------------------

model_path = "models/hand_landmarker.task"

base_options = python.BaseOptions(
    model_asset_path=model_path
)

options = vision.HandLandmarkerOptions(
    base_options=base_options,
    num_hands=1
)

detector = vision.HandLandmarker.create_from_options(options)


# -----------------------------
# Camera
# -----------------------------

cap = cv2.VideoCapture(0)


# Volume starts at 50
volume = 50

# Previous hand Y position
previous_y = None

# Pinch threshold
pinch_threshold = 0.05


while True:

    ret, frame = cap.read()

    if not ret:
        break

    frame = cv2.flip(frame, 1)

    rgb = cv2.cvtColor(
        frame,
        cv2.COLOR_BGR2RGB
    )

    image = mp.Image(
        image_format=mp.ImageFormat.SRGB,
        data=rgb
    )

    result = detector.detect(image)

    status = "NO HAND"

    if result.hand_landmarks:

        hand = result.hand_landmarks[0]

        # Thumb tip
        thumb = hand[4]

        # Index finger tip
        index = hand[8]

        # Calculate distance
        dx = thumb.x - index.x
        dy = thumb.y - index.y

        distance = math.sqrt(
            dx * dx + dy * dy
        )

        # Check pinch
        if distance < pinch_threshold:

            status = "PINCH - CONTROL VOLUME"

            # Use index finger Y position
            current_y = index.y

            if previous_y is not None:

                movement = previous_y - current_y

                # Move UP
                if movement > 0.01:

                    volume += 2

                # Move DOWN
                elif movement < -0.01:

                    volume -= 2

            previous_y = current_y

        else:

            status = "OPEN"

            previous_y = None


    # Keep volume between 0 and 100
    volume = max(0, min(100, volume))


    # -----------------------------
    # Display
    # -----------------------------

    cv2.putText(
        frame,
        status,
        (30, 60),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (0, 255, 0),
        2
    )

    cv2.putText(
        frame,
        f"Volume: {volume}%",
        (30, 110),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.2,
        (0, 255, 0),
        3
    )


    # Volume bar

    bar_x = 30
    bar_y = 150
    bar_width = 300
    bar_height = 30

    cv2.rectangle(
        frame,
        (bar_x, bar_y),
        (bar_x + bar_width, bar_y + bar_height),
        (255, 255, 255),
        2
    )

    filled_width = int(
        bar_width * volume / 100
    )

    cv2.rectangle(
        frame,
        (bar_x, bar_y),
        (bar_x + filled_width, bar_y + bar_height),
        (0, 255, 0),
        -1
    )


    cv2.imshow(
        "DriveGesture AI - Volume Control",
        frame
    )


    # Q = quit

    if cv2.waitKey(1) & 0xFF == ord("q"):
        break


cap.release()
cv2.destroyAllWindows()