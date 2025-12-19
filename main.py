# Author: Ariana – motors + distance + PIR safety logic + donation counter
# + Solenoid lock + conveyor belt + Servo lock indicator (Sol)
# + NeoPixel status LEDs (Sol)

import RPi.GPIO as GPIO
import time
from time import sleep

PROGRAM_START = time.time()
PIR_STARTUP_IGNORE = 30.0  # seconds to ignore PIR after startup
# <<< NEW LED CODE >>>
from rpi_ws281x import PixelStrip, Color, ws

# >>> NEW: web log server imports <<<
from webserver2 import start_web_server, log_and_print
start_web_server()

GPIO.setmode(GPIO.BOARD)
GPIO.setwarnings(False)

# >>> NEW: start Flask server in background <<<
start_web_server()

# -----------------------------
# DONATION COUNTER
# -----------------------------
donation_count = 0   # increments each time doors safely open & close

# -----------------------------
# Ultrasonic Sensors (BOARD Mode)
# Sensor 1:
#   Trig = Pin 40 (GPIO 21)
#   Echo = Pin 38 (GPIO 20)
# Sensor 2:
#   Trig = Pin 31 (GPIO 6)
#   Echo = Pin 29 (GPIO 5)
# -----------------------------
TRIG1 = 40
ECHO1 = 38

TRIG2 = 31
ECHO2 = 29

GPIO.setup(TRIG1, GPIO.OUT)
GPIO.setup(ECHO1, GPIO.IN)

GPIO.setup(TRIG2, GPIO.OUT)
GPIO.setup(ECHO2, GPIO.IN)

# Make sure triggers start LOW
GPIO.output(TRIG1, False)
GPIO.output(TRIG2, False)

# -----------------------------
# PIR SENSOR (motion inside box)
# -----------------------------
PIR_PIN = 37                 # <--- change if your PIR is on a different pin
GPIO.setup(PIR_PIN, GPIO.IN) # PIR modules usually drive HIGH/LOW themselves


# -----------------------------
# Motor Driver 1 pins
# -----------------------------
M1_IN1 = 12
M1_IN2 = 11
M1_IN3 = 13
M1_IN4 = 15
motor1_pins = [M1_IN1, M1_IN2, M1_IN3, M1_IN4]

# -----------------------------
# Motor Driver 2 pins
# -----------------------------
M2_IN1 = 16
M2_IN2 = 18
M2_IN3 = 22
M2_IN4 = 7
motor2_pins = [M2_IN1, M2_IN2, M2_IN3, M2_IN4]

# -----------------------------
# BUTTON
# -----------------------------
BUTTON_PIN = 36
GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

# -----------------------------
# CONVEYOR BELT RELAY
# -----------------------------
BELT_PIN = 24          # BOARD pin 24 -> relay input
GPIO.setup(BELT_PIN, GPIO.OUT)
GPIO.output(BELT_PIN, GPIO.LOW)   # belt OFF at start

BELT_RUN_TIME = 5.0    # seconds belt should run

# -----------------------------
# SERVO (lock position indicator)
# -----------------------------
SERVO_PIN = 33          # BOARD pin 33
GPIO.setup(SERVO_PIN, GPIO.OUT)

# 50Hz PWM for standard servo
servo_pwm = GPIO.PWM(SERVO_PIN, 50)
servo_pwm.start(0)

def set_servo_angle(angle):
    """
    0°  = servo DOWN  -> door locked
    180° = servo UP   -> door unlocked
    """
    duty = 2 + (angle / 18.0)    # 0°->~2%, 180°->~12%
    servo_pwm.ChangeDutyCycle(duty)
    sleep(0.3)
    # Optional: stop sending pulses to reduce jitter
    servo_pwm.ChangeDutyCycle(0)

# -----------------------------
# SOLENOID LOCK (via H-bridge)
# -----------------------------
# Using the pins that were BCM 9 and 11 in your old code,
# which correspond to BOARD 21 and 23:
LOCK_RIGHT1 = 21   # was BCM9 in previous code
LOCK_RIGHT2 = 23   # was BCM11
LOCK_LEFT3 = 8
LOCK_LEFT4 = 10

GPIO.setup(LOCK_RIGHT1, GPIO.OUT)
GPIO.setup(LOCK_RIGHT2, GPIO.OUT)
GPIO.setup(LOCK_LEFT3, GPIO.OUT)
GPIO.setup(LOCK_LEFT4, GPIO.OUT)

LOCK_RELEASE_TIME = 0.5  # small delay after unlocking before moving doors

def lock_engage():
    """
    Lock ON (door locked).
    Solenoid OFF: IN1=LOW, IN2=LOW
    + Servo DOWN (0°)
    """
    GPIO.output(LOCK_RIGHT1, GPIO.LOW)
    GPIO.output(LOCK_RIGHT2, GPIO.LOW)
    GPIO.output(LOCK_LEFT3, GPIO.LOW)
    GPIO.output(LOCK_LEFT4, GPIO.LOW)

    set_servo_angle(0)  # servo down = locked
    log_and_print("Lock engaged (door locked). Servo down.")

def lock_release():
    """
    Lock OFF (door unlocked).
    Solenoid ON: IN1=HIGH, IN2=LOW
    + Servo UP (180°)
    """
    GPIO.output(LOCK_RIGHT1, GPIO.HIGH)
    GPIO.output(LOCK_RIGHT2, GPIO.LOW)
    GPIO.output(LOCK_LEFT3, GPIO.HIGH)
    GPIO.output(LOCK_LEFT4, GPIO.LOW)

    set_servo_angle(180)  # servo up = unlocked
    log_and_print("Lock released (door unlocked). Servo up.")

# Start with lock ON (engaged)
lock_engage()

# -----------------------------
# STEPPER SEQUENCE (full step)
# -----------------------------
sequence = [
    [1,0,1,0],
    [0,1,1,0],
    [0,1,0,1],
    [1,0,0,1]
]

# -----------------------------
# MOTOR CONFIG – easy to tune
# -----------------------------

# MOTOR 1 CONFIG
M1_FORWARD_PINS   = motor1_pins[::-1]   # Motor 1 forward (flipped)
M1_BACKWARD_PINS  = motor1_pins        # Motor 1 backward

M1_FORWARD_STEPS  = 7                  # Motor 1 forward steps
M1_BACKWARD_STEPS = 9                  # Motor 1 backward steps

# MOTOR 2 CONFIG
M2_FORWARD_PINS   = motor2_pins        # Motor 2 forward (normal)
M2_BACKWARD_PINS  = motor2_pins[::-1]  # Motor 2 backward

M2_FORWARD_STEPS  = 8                  # Motor 2 forward steps
M2_BACKWARD_STEPS = 9                  # Motor 2 backward steps

# -----------------------------
# SAFETY / DETECTION CONFIG – easy to tune
# -----------------------------
S1_DETECT_CM      = 20.0   # Sensor 1: object if < this distance
S2_DETECT_CM      = 10.0   # Sensor 2: object if < this distance

PIR_OBSERVE_TIME  = 5.0    # seconds to watch PIR for motion
PIR_POLL_INTERVAL = 0.1    # how often to sample PIR during check (seconds)
PIR_MIN_MOTION_TIME = 5.0

DOOR_OPEN_DELAY   = 2.0    # time doors stay open before closing (seconds)
STEP_DELAY        = 0.08   # delay between step phases (motor speed)

# -----------------------------
# SETUP ALL MOTOR PINS
# -----------------------------
for pin in motor1_pins + motor2_pins:
    GPIO.setup(pin, GPIO.OUT)
    GPIO.output(pin, 0)

# -----------------------------
# <<< LED CODE: NeoPixel STATUS LED >>>
# -----------------------------
LED_COUNT      = 2           # we only use LED 0 as status, LED 1 stays off
LED_PIN        = 19          # BCM 19 (physical pin 35) for NeoPixel data
LED_FREQ_HZ    = 800000
LED_DMA        = 10
LED_BRIGHTNESS = 128         # 0–255
LED_INVERT     = False
LED_CHANNEL    = 1
LED_STRIP_TYPE = ws.SK6812_STRIP_GRBW  # Adafruit RGBW NeoPixels

strip = PixelStrip(
    LED_COUNT,
    LED_PIN,
    LED_FREQ_HZ,
    LED_DMA,
    LED_INVERT,
    LED_BRIGHTNESS,
    LED_CHANNEL,
    LED_STRIP_TYPE
)
strip.begin()

def led_all_off():
    for i in range(LED_COUNT):
        strip.setPixelColor(i, Color(0, 0, 0, 0))
    strip.show()

def led_idle():
    """
    Idle: system ready / waiting for next donation
    -> LED 0 GREEN solid
       LED 1 WHITE solid
    """
    # LED 0: green
    strip.setPixelColor(0, Color(255, 0, 0))      # R,G,B,(W)
    # LED 1: white using W channel
    strip.setPixelColor(1, Color(0, 0, 0, 255))   # pure white
    strip.show()

def led_safe():
    """
    Safe: donation allowed / doors will open
    -> LED 0 RED solid
       LED 1 OFF
    """
    strip.setPixelColor(0, Color(0, 255, 0))      # red
    strip.setPixelColor(1, Color(0, 0, 0, 0))     # off
    strip.show()

def led_not_safe_flash(duration=3.0, period=0.4):
    """
    Not safe: PIR saw motion, user should check box and try again.
    -> LED 0 FLASHING RED, LED 1 OFF, then back to idle (green+white)
    """
    # make sure LED 1 is off during flashing
    strip.setPixelColor(1, Color(0, 0, 0, 0))
    strip.show()

    end_time = time.time() + duration
    while time.time() < end_time:
        # ON (red)
        strip.setPixelColor(0, Color(0, 255, 0))
        strip.show()
        time.sleep(period / 2)

        # OFF
        strip.setPixelColor(0, Color(0, 0, 0, 0))
        strip.show()
        time.sleep(period / 2)

    # After flashing, go back to idle state (green + white)
    led_idle()

# Start: idle (green)
led_idle()

# -----------------------------
# measure_distance
# -----------------------------
def measure_distance(trigger_pin, echo_pin):
    """Measure distance from one HC-SR04 sensor."""
    # Send 10 µs trigger pulse
    GPIO.output(trigger_pin, True)
    time.sleep(0.00001)
    GPIO.output(trigger_pin, False)

    start_time = time.time()
    stop_time = time.time()

    # Wait for echo to go HIGH
    while GPIO.input(echo_pin) == 0:
        start_time = time.time()

    # Wait for echo to go LOW
    while GPIO.input(echo_pin) == 1:
        stop_time = time.time()

    # Time difference
    time_elapsed = stop_time - start_time

    # Distance in cm
    distance_cm = round((time_elapsed * 34300) / 2, 2)

    return distance_cm

# -----------------------------
# PIR CHECK FUNCTION
# -----------------------------
def pir_clear_for_window():
    """
    Check PIR for a fixed time window.

    We ONLY declare "Person detected" if the PIR input stays HIGH
    continuously for at least PIR_MIN_MOTION_TIME seconds.

    - Short spikes (e.g., < PIR_MIN_MOTION_TIME) are ignored.
    - If no sustained motion is found during PIR_OBSERVE_TIME,
      we treat it as safe (return True).
    """
    log_and_print(
        f"Checking for sustained motion for up to {PIR_OBSERVE_TIME} seconds "
        f"(needs {PIR_MIN_MOTION_TIME} seconds continuous HIGH to count)."
    )

    start = time.time()
    motion_start = None  # when we first saw HIGH

    while time.time() - start < PIR_OBSERVE_TIME:
        pir_value = GPIO.input(PIR_PIN)

        if pir_value == GPIO.HIGH:
            if motion_start is None:
                # First time we see HIGH – start timing it
                motion_start = time.time()
                log_and_print("PIR went HIGH, starting motion timer...")
            else:
                # We've been HIGH for a while, check duration
                if time.time() - motion_start >= PIR_MIN_MOTION_TIME:
                    log_and_print(
                        f"Person detected (PIR HIGH for >= {PIR_MIN_MOTION_TIME} seconds). "
                        "Doors will NOT open."
                    )
                    return False
        else:
            # Went LOW again before reaching threshold -> treat as noise
            if motion_start is not None:
                log_and_print("PIR went LOW again before threshold; ignoring spike.")
            motion_start = None

        time.sleep(PIR_POLL_INTERVAL)

    # If we finish the whole window without sustained HIGH, it's safe
    log_and_print("No sustained motion detected. Safely opening doors.")
    return True

# -----------------------------
# MOTOR MOVE FUNCTIONS
# -----------------------------
def move_both_forward(delay=STEP_DELAY):
    """Move BOTH motors forward at the same time."""
    total_steps = max(M1_FORWARD_STEPS, M2_FORWARD_STEPS)

    for step in range(total_steps):
        for phase in sequence:
            # Motor 1
            if step < M1_FORWARD_STEPS:
                for pin, val in zip(M1_FORWARD_PINS, phase):
                    GPIO.output(pin, val)
            else:
                for pin in motor1_pins:
                    GPIO.output(pin, 0)

            # Motor 2
            if step < M2_FORWARD_STEPS:
                for pin, val in zip(M2_FORWARD_PINS, phase):
                    GPIO.output(pin, val)
            else:
                for pin in motor2_pins:
                    GPIO.output(pin, 0)

            sleep(delay)

    for pin in motor1_pins + motor2_pins:
        GPIO.output(pin, 0)

def move_both_backward(delay=STEP_DELAY):
    """Move BOTH motors backward at the same time."""
    total_steps = max(M1_BACKWARD_STEPS, M2_BACKWARD_STEPS)

    for step in range(total_steps):
        for phase in sequence:
            # Motor 1
            if step < M1_BACKWARD_STEPS:
                for pin, val in zip(M1_BACKWARD_PINS, phase):
                    GPIO.output(pin, val)
            else:
                for pin in motor1_pins:
                    GPIO.output(pin, 0)

            # Motor 2
            if step < M2_BACKWARD_STEPS:
                for pin, val in zip(M2_BACKWARD_PINS, phase):
                    GPIO.output(pin, val)
            else:
                for pin in motor2_pins:
                    GPIO.output(pin, 0)

            sleep(delay)

    for pin in motor1_pins + motor2_pins:
        GPIO.output(pin, 0)

log_and_print("System ready. Waiting for button press...")
log_and_print(f"Current donation count: {donation_count}")

try:
    while True:
        # Wait for button press
        if GPIO.input(BUTTON_PIN) == GPIO.HIGH:
            log_and_print("Button pressed! Measuring distance once...")

            # Keep LED green while we evaluate (idle = not yet safe)
            # no leds_all_off() here

            # One measurement from each sensor
            d1 = measure_distance(TRIG1, ECHO1)
            sleep(0.05)  # small delay between sensors
            d2 = measure_distance(TRIG2, ECHO2)

            log_and_print(f"Sensor 1: {d1} cm   |   Sensor 2: {d2} cm")

            # Check thresholds for object presence
            if (d1 < S1_DETECT_CM) or (d2 < S2_DETECT_CM):
                log_and_print("Object detected by distance sensors.")

                # ---- PIR SAFETY CHECK ----
                safe_to_open = pir_clear_for_window()

                if safe_to_open:
                    # LEDs: SAFE to donate (solid red)
                    led_safe()

                    # 1) Unlock first
                    log_and_print("Releasing lock before opening doors...")
                    lock_release()  # this also moves servo UP
                    sleep(LOCK_RELEASE_TIME)

                    # 2) Open doors
                    log_and_print("Motors FORWARD (opening doors)...")
                    move_both_forward(delay=STEP_DELAY)

                    # 3) Start belt as soon as doors are open
                    log_and_print("Doors open. Starting conveyor belt...")
                    GPIO.output(BELT_PIN, GPIO.HIGH)
                    belt_start = time.time()

                    # 4) Keep doors open for DOOR_OPEN_DELAY seconds
                    log_and_print(f"Keeping doors open for {DOOR_OPEN_DELAY} seconds...")
                    sleep(DOOR_OPEN_DELAY)

                    # 5) Close doors
                    log_and_print("Motors BACKWARD (closing doors)...")
                    move_both_backward(delay=STEP_DELAY)

                    # 6) Ensure belt runs for BELT_RUN_TIME total
                    elapsed = time.time() - belt_start
                    remaining = max(0.0, BELT_RUN_TIME - elapsed)
                    if remaining > 0:
                        sleep(remaining)

                    GPIO.output(BELT_PIN, GPIO.LOW)
                    log_and_print("Conveyor belt stopped.")

                    # 7) Re-engage lock AFTER motion
                    lock_engage()   # this also moves servo DOWN

                    # ✅ Count donation here
                    donation_count += 1
                    log_and_print(f"Donation counted! Total donations: {donation_count}\n")

                    # Back to idle: green
                    led_idle()

                else:
                    # Motion detected -> do NOT open doors or run belt
                    log_and_print("Doors remain closed for safety. Conveyor stays off. Lock stays engaged.")
                    log_and_print(f"Total donations so far: {donation_count}\n")

                    # LEDs: NOT safe to donate (flashing red, then back to green)
                    led_not_safe_flash()

            else:
                log_and_print("No object detected. Motors, conveyor, and lock state unchanged.")
                log_and_print(f"Total donations so far: {donation_count}\n")

                # No object -> idle (green)
                led_idle()

            # Wait for button release so it doesn't retrigger
            while GPIO.input(BUTTON_PIN) == GPIO.HIGH:
                sleep(0.05)

        sleep(0.05)

except KeyboardInterrupt:
    log_and_print("\nStopped by user")

finally:
    # Make sure everything is in a safe state
    GPIO.output(BELT_PIN, GPIO.LOW)
    lock_engage()        # lock + servo down on exit
    servo_pwm.stop()     # stop servo PWM

    # Turn LEDs off on exit
    led_all_off()

    GPIO.cleanup()
    log_and_print("GPIO cleaned up.")
