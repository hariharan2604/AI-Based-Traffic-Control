import json
import time
import threading
from collections import deque
from config.settings import (
    ACO_DEFAULT_DURATION,
    ACO_MAX_DURATION,
    MIN_UPDATE_THRESHOLD,
    BASE_YELLOW_DURATION,
    BASE_RED_DURATION,
    EMERGENCY_THRESHOLD,
    EMERGENCY_GREEN_BOOST,
)
from core.mqtt_client import (
    manual_override,
    manual_override_lock,
    vehicle_density_data,
    vehicle_data_lock,
)

density_history = {}
signal_states = {}
signal_timers = {}  # Stores last switch times for non-blocking updates

def weighted_moving_average(intersection, new_density):
    """Computes a weighted moving average for smoother ACO updates."""
    if intersection not in density_history:
        density_history[intersection] = deque(maxlen=3)
    
    density_history[intersection].append(new_density)
    weights = [0.2, 0.3, 0.5]
    return sum(w * d for w, d in zip(weights, density_history[intersection]))

def aco_optimize_signal(density_data):
    """ACO optimization with Emergency Mode."""
    signal_durations = {}
    emergency_mode = {}

    total_density = sum(sum(density.values()) for density in density_data.values())

    for intersection, density in density_data.items():
        smoothed_density = weighted_moving_average(intersection, sum(density.values()))

        if smoothed_density >= EMERGENCY_THRESHOLD:
            emergency_mode[intersection] = True
            green_duration = min(ACO_MAX_DURATION, ACO_DEFAULT_DURATION + EMERGENCY_GREEN_BOOST)
        else:
            emergency_mode[intersection] = False
            green_duration = int(
                ACO_DEFAULT_DURATION + ((smoothed_density / total_density) * (ACO_MAX_DURATION - ACO_DEFAULT_DURATION))
            ) if total_density > 0 else ACO_DEFAULT_DURATION

        signal_durations[intersection] = green_duration

    return signal_durations, emergency_mode

def update_signal_state(mqtt_client, intersection, state, duration):
    """Sends signal updates via MQTT only if the state changes."""
    if signal_states.get(intersection) == state:
        return  # Prevent redundant updates

    signal_status = {
        "state": state,
        "duration": duration,
        "manual_override": intersection in manual_override
    }
    mqtt_client.publish(f"signal/status/{intersection}", json.dumps(signal_status))
    signal_states[intersection] = state
    signal_timers[intersection] = time.time()  # Track last state change time
    print(f"🚦 Intersection {intersection}: {state.upper()} for {duration}s (Manual: {signal_status['manual_override']})")

def manage_traffic_signals(mqtt_client):
    """Handles signal updates while ensuring proper Manual Override & Emergency Mode enforcement."""
    while True:
        with manual_override_lock:
            is_manual_active = bool(manual_override)

        with vehicle_data_lock:
            density_data = vehicle_density_data.copy()

        if not density_data and not is_manual_active:
            print("⚠️ No vehicle density data available. Using default durations.")
            time.sleep(5)
            continue
        
        if is_manual_active:
            signal_durations = manual_override.copy()
            emergency_mode = {k: False for k in manual_override}
            print("🚦 Manual override active. ACO paused.")
        else:
            signal_durations, emergency_mode = aco_optimize_signal(density_data)

        for intersection, green_duration in signal_durations.items():
            if emergency_mode.get(intersection, False):
                print(f"🚨 EMERGENCY MODE ACTIVE at {intersection}! Extending Green time.")

            # Check if enough time has passed since last state change
            last_update = signal_timers.get(intersection, 0)
            elapsed_time = time.time() - last_update

            if elapsed_time < green_duration + BASE_YELLOW_DURATION + BASE_RED_DURATION:
                continue  # Skip updating this signal if it's still running

            # Enforce Manual Override properly
            if intersection in manual_override:
                update_signal_state(mqtt_client, intersection, "green", signal_durations[intersection])
                update_signal_state(mqtt_client, intersection, "yellow", BASE_YELLOW_DURATION)
                update_signal_state(mqtt_client, intersection, "red", BASE_RED_DURATION)
                continue

            # Ensure proper traffic light cycle (Red → Green → Yellow → Red)
            current_state = signal_states.get(intersection, "red")

            if current_state == "red":
                update_signal_state(mqtt_client, intersection, "green", green_duration)
            elif current_state == "green":
                update_signal_state(mqtt_client, intersection, "yellow", BASE_YELLOW_DURATION)
            elif current_state == "yellow":
                update_signal_state(mqtt_client, intersection, "red", BASE_RED_DURATION)

        time.sleep(0.5)  # Small delay before checking again
