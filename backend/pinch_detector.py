import cv2
import mediapipe as mp
import math

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


# Camera
cap = cv2.VideoCapture(0)

while True:

    ret, frame = cap.read()

    if not ret:
        break

    frame = cv2.flip(frame, 1)

    # Convert BGR to RGB
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    # MediaPipe image
    image = mp.Image(
        image_format=mp.ImageFormat.SRGB,
        data=rgb
    )

    # Detect hand
    result = detector.detect(image)

    text = "NO HAND"

    if result.hand_landmarks:

        hand = result.hand_landmarks[0]

        # Thumb tip = 4
        thumb = hand[4]

        # Index finger tip = 8
        index = hand[8]

        # Calculate distance
        dx = thumb.x - index.x
        dy = thumb.y - index.y

        distance = math.sqrt(dx * dx + dy * dy)

        # Pinch decision
        if distance < 0.05:
            text = "PINCH"
        else:
            text = "OPEN"

        # Convert coordinates
        height, width, _ = frame.shape

        tx = int(thumb.x * width)
        ty = int(thumb.y * height)

        ix = int(index.x * width)
        iy = int(index.y * height)

        # Draw line between thumb and index
        cv2.line(
            frame,
            (tx, ty),
            (ix, iy),
            (255, 0, 0),
            2
        )

        # Draw points
        cv2.circle(
            frame,
            (tx, ty),
            8,
            (0, 255, 0),
            -1
        )

        cv2.circle(
            frame,
            (ix, iy),
            8,
            (0, 255, 0),
            -1
        )

        # Show distance
        cv2.putText(
            frame,
            f"Distance: {distance:.3f}",
            (30, 120),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 255, 0),
            2
        )

    # Show PINCH / OPEN
    cv2.putText(
        frame,
        text,
        (30, 70),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.5,
        (0, 255, 0),
        3
    )

    cv2.imshow(
        "DriveGesture AI - Pinch Detection",
        frame
    )

    # Press Q to quit
    if cv2.waitKey(1) & 0xFF == ord("q"):
        break


cap.release()
cv2.destroyAllWindows()