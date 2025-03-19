import json
import time
import threading
from collections import deque
from config.settings import (
    ACO_DEFAULT_DURATION,
    ACO_MAX_DURATION,
    BASE_YELLOW_DURATION,
    BASE_RED_DURATION,
    EMERGENCY_GREEN_BOOST,
)
from core.mqtt_client import (
    manual_override,
    manual_override_lock,
    vehicle_density_data,
    vehicle_data_lock,
    emergency_events,
)

# Store signal states, timers, and historical density
signal_states = {}  # Tracks Green, Yellow, or Red state
signal_timers = {}  # Tracks last state change time
density_history = {}  # For smoothing traffic density
signal_queue = []  # Queue to rotate active signals

def initialize_signals(mqtt_client):
    """Start all signals at RED, queue them in order, and publish initial states."""
    global signal_states, signal_queue
    signal_states = {f"{i+4001}": "red" for i in range(4)}
    signal_queue = list(signal_states.keys())  # Maintain order

    # Publish initial signal states
    for signal in signal_states:
        update_signal(mqtt_client, signal, "red", BASE_RED_DURATION)  # Ensure red state is published

    print("🚦 All signals initialized to RED and published.")


def weighted_moving_average(signal, new_density):
    """Computes a weighted moving average to smooth density fluctuations."""
    if signal not in density_history:
        density_history[signal] = deque(maxlen=3)  # Store last 3 densities

    density_history[signal].append(new_density)

    weights = [0.2, 0.3, 0.5]  # Higher weight for recent data

    return sum(w * d for w, d in zip(weights, density_history[signal]))

def aco_optimize_signal(density_data):
    """ACO-based optimization to dynamically adjust Green time."""
    signal_durations = {}
    emergency_mode = {}

    total_density = sum(sum(d.values()) for d in density_data.values())  # Sum of all intersections

    for signal, density in density_data.items():
        smoothed_density = weighted_moving_average(signal, sum(density.values()))

        # Emergency vehicle priority
        if signal in emergency_events:
            emergency_mode[signal] = True
            green_duration = min(ACO_MAX_DURATION, ACO_DEFAULT_DURATION + EMERGENCY_GREEN_BOOST)
        else:
            emergency_mode[signal] = False
            green_duration = int(
                ACO_DEFAULT_DURATION + ((smoothed_density / total_density) * (ACO_MAX_DURATION - ACO_DEFAULT_DURATION))
            ) if total_density > 0 else ACO_DEFAULT_DURATION

        signal_durations[signal] = green_duration

    return signal_durations, emergency_mode

def update_signal(mqtt_client, signal, state, duration):
    """Publish signal state to MQTT and update tracking."""
    signal_states[signal] = state
    signal_timers[signal] = time.time()

    payload = {"state": state, "duration": duration, "emergency": signal in emergency_events}
    mqtt_client.publish(f"signal/status/{signal}", json.dumps(payload))

    print(f"🚦 {signal}: {state.upper()} for {duration}s (Emergency: {signal in emergency_events})")

def cycle_signals(mqtt_client, ws_servers):
    """Manages traffic signal sequencing with ACO optimization, waiting for WebSocket clients."""
    initialize_signals(mqtt_client=mqtt_client)
    global signal_queue

    while True:
        # Ensure all WebSocket clients are connected before starting
        while not all(ws.client_count > 0 for ws in ws_servers):
            print("⏸️ Waiting for all WebSocket clients to connect...")
            time.sleep(2)

        with manual_override_lock:
            is_manual_active = bool(manual_override)

        with vehicle_data_lock:
            density_data = vehicle_density_data.copy()

        if is_manual_active:
            print("🔧 Manual Override Active. Skipping ACO.")
            time.sleep(2)
            continue

        if not density_data:
            print("⚠️ No density data available. Using default cycle.")
            time.sleep(2)
            continue

        # Calculate optimized signal durations
        signal_durations, emergency_mode = aco_optimize_signal(density_data)

        # Ensure at least one GREEN signal (prevents deadlocks)
        active_green = [s for s, state in signal_states.items() if state == "green"]
        if not active_green:
            print("⚠️ No active GREEN signal. Assigning one to prevent deadlock.")
            first_signal = signal_queue.pop(0)
            signal_queue.append(first_signal)
            update_signal(mqtt_client, first_signal, "green", ACO_DEFAULT_DURATION)

        # Process signals in order
        for signal in signal_queue:
            # If WebSocket clients disconnect, pause signal cycling
            if not all(ws.client_count > 0 for ws in ws_servers):
                print("⏸️ WebSocket client disconnected. Pausing traffic signal updates.")
                break

            current_state = signal_states.get(signal, "red")
            green_duration = signal_durations.get(signal, ACO_DEFAULT_DURATION)

            if current_state == "green":
                update_signal(mqtt_client, signal, "yellow", BASE_YELLOW_DURATION)
            elif current_state == "yellow":
                update_signal(mqtt_client, signal, "red", BASE_RED_DURATION)
            elif current_state == "red":
                # Ensure only one GREEN at a time
                active_green = [s for s, state in signal_states.items() if state == "green"]
                if not active_green:
                    update_signal(mqtt_client, signal, "green", green_duration)

            time.sleep(0.5)  # Small delay to manage signal changes

