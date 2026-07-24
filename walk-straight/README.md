# Walk Straight

A daily walking-posture tracker. Open `index.html` in any browser — no build
step, no dependencies. Entries are stored in the browser's localStorage.

To use the **camera walking check**, serve the folder over http (browsers
only allow camera access on `http://localhost` or `https`, not on `file://`):

```
cd walk-straight
python3 -m http.server 8000
```

then open <http://localhost:8000>.

## Features

- **Guided camera walking check**: a fully hands-free, spoken session. The
  app checks your whole body is in frame (and says what to fix if not —
  "step back", "tilt the camera down"), then talks you through walking
  toward the camera, turning around, and walking away. It announces when it
  has enough data, reports what it found (hip drop, shoulder tilt, lean,
  head drift) with plain-language advice, and saves the score to today's
  check-in automatically. On-device pose detection (MediaPipe Pose, loaded
  from a CDN on first use); video is processed locally and never uploaded.
- **Human body figure** with both hips marked; the markers change color with
  your hip status (green = good, amber = sore, red = injured).
- **Daily check-in**: rate how straight you walked (1–10), log hip pain
  (0–10), and add notes.
- **Hip injury mode**: mark your hip as injured/broken and the app pauses
  posture goals, shows a get-it-checked warning, and keeps a daily pain log
  you can share with a doctor.
- **14-day history** with a bar chart, color-coded by hip status, plus a
  daily check-in streak counter and context-aware walking tips.
