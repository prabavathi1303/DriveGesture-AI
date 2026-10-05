import cv2
import mediapipe as mp
import numpy as np

from mediapipe.tasks import python
from mediapipe.tasks.python import vision

model_path = "models/face_landmarker.task"

base_options = python.BaseOptions(
    model_asset_path=model_path
)

options = vision.FaceLandmarkerOptions(
    base_options=base_options,
    num_faces=1,
    output_facial_transformation_matrixes=True
)

detector = vision.FaceLandmarker.create_from_options(options)

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

    direction = "NO FACE"

    if result.face_landmarks:

        matrix = result.facial_transformation_matrixes[0]

        # Convert to NumPy matrix
        matrix = np.array(matrix)

        # Get rotation values
        rotation = matrix[:3, :3]

        yaw = np.arctan2(
            rotation[1, 0],
            rotation[0, 0]
        )

        yaw_degrees = np.degrees(yaw)

        if yaw_degrees > 15:
            direction = "LOOKING RIGHT"

        elif yaw_degrees < -15:
            direction = "LOOKING LEFT"

        else:
            direction = "LOOKING CENTER"

        cv2.putText(
            frame,
            direction,
            (30, 60),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (0, 255, 0),
            2
        )

        cv2.putText(
            frame,
            f"Yaw: {yaw_degrees:.1f}",
            (30, 100),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 255, 0),
            2
        )

    else:

        cv2.putText(
            frame,
            "NO FACE",
            (30, 60),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (0, 0, 255),
            2
        )

    cv2.imshow(
        "DriveGesture AI - Head Pose",
        frame
    )

    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()