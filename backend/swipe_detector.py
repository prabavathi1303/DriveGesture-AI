import cv2
import mediapipe as mp
from collections import deque

from mediapipe.tasks import python
from mediapipe.tasks.python import vision


# Model
model_path = "models/hand_landmarker.task"

base_options = python.BaseOptions(
    model_asset_path=model_path
)

options = vision.HandLandmarkerOptions(
    base_options=base_options,
    num_hands=1
)

detector = vision.HandLandmarker.create_from_options(options)


# Store previous hand positions
positions = deque(maxlen=10)

cap = cv2.VideoCapture(0)

while True:

    ret, frame = cap.read()

    if not ret:
        break

    frame = cv2.flip(frame, 1)

    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    image = mp.Image(
        image_format=mp.ImageFormat.SRGB,
        data=rgb
    )

    result = detector.detect(image)

    gesture = "NO GESTURE"

    if result.hand_landmarks:

        hand = result.hand_landmarks[0]

        # Use index finger tip
        index = hand[8]

        height, width, _ = frame.shape

        x = int(index.x * width)
        y = int(index.y * height)

        # Save current position
        positions.append((x, y))

        cv2.circle(
            frame,
            (x, y),
            8,
            (0, 255, 0),
            -1
        )

        # Need enough positions
        if len(positions) == 10:

            first_x = positions[0][0]
            last_x = positions[-1][0]

            difference = last_x - first_x

            # Swipe right
            if difference > 150:

                gesture = "SWIPE RIGHT"
                positions.clear()

            # Swipe left
            elif difference < -150:

                gesture = "SWIPE LEFT"
                positions.clear()


    cv2.putText(
        frame,
        gesture,
        (30, 70),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.2,
        (0, 255, 0),
        3
    )

    cv2.imshow(
        "DriveGesture AI - Swipe Detection",
        frame
    )

    if cv2.waitKey(1) & 0xFF == ord("q"):
        break


cap.release()
cv2.destroyAllWindows()