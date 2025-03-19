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
    emergency_events,
)

# Store signal information
density_history = {}
signal_states = {}
signal_timers = {}  # Last state change times
signal_first_cycle = {}  # Track first full cycle completion

def weighted_moving_average(intersection, new_density):
    """Compute a weighted moving average for smoother signal updates."""
    if intersection not in density_history:
        density_history[intersection] = deque(maxlen=3)
    
    density_history[intersection].append(new_density)
    
    weights = [0.2, 0.3, 0.5]  # Recent densities have higher weight
    
    return sum(w * d for w, d in zip(weights, density_history[intersection]))

def aco_optimize_signal(density_data):
    """ACO-based signal optimization ensuring fairness and emergency prioritization."""
    signal_durations = {}
    emergency_mode = {}

    total_density = sum(sum(density.values()) for density in density_data.values())

    for intersection, density in density_data.items():
        smoothed_density = weighted_moving_average(intersection, sum(density.values()))

        # Prioritize emergency vehicles
        if intersection in emergency_events:
            emergency_mode[intersection] = True
            green_duration = min(ACO_MAX_DURATION, ACO_DEFAULT_DURATION + EMERGENCY_GREEN_BOOST)
        else:
            emergency_mode[intersection] = False
            green_duration = (
                int(ACO_DEFAULT_DURATION + ((smoothed_density / total_density) * (ACO_MAX_DURATION - ACO_DEFAULT_DURATION)))
                if total_density > 0 else ACO_DEFAULT_DURATION
            )

        signal_durations[intersection] = green_duration

    return signal_durations, emergency_mode

def update_signal_state(mqtt_client, intersection, state, duration):
    """Send signal updates via MQTT only if the state has changed."""
    if signal_states.get(intersection) == state:
        return  # Prevent redundant updates

    signal_status = {
        "state": state,
        "duration": duration,
        "manual_override": intersection in manual_override,
        "emergency_mode": intersection in emergency_events,
    }

    mqtt_client.publish(f"signal/status/{intersection}", json.dumps(signal_status))
    
    signal_states[intersection] = state
    signal_timers[intersection] = time.time()  # Track last state change time
    
    print(f"🚦 Intersection {intersection}: {state.upper()} for {duration}s (Manual: {signal_status['manual_override']}, Emergency: {signal_status['emergency_mode']})")

def validate_signal_distribution():
    """Ensure signals are not all in the same state to prevent traffic jams."""
    state_counts = {"green": 0, "yellow": 0, "red": 0}

    for state in signal_states.values():
        state_counts[state] += 1

    # Prevent all signals from being the same state (e.g., all green)
    if state_counts["green"] == 4 or state_counts["red"] == 4:
        print("⚠️ Detected all signals in the same state. Forcing staggered cycle.")
        return False

    return True

def manage_traffic_signals(mqtt_client):
    """Handles signal updates while ensuring proper cycling and fairness."""

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

        # Track updated intersections to ensure staggered updates
        updated_intersections = set()

        for intersection, green_duration in signal_durations.items():
            last_update_time = signal_timers.get(intersection, 0)
            elapsed_time = time.time() - last_update_time

            if intersection not in signal_first_cycle:
                signal_first_cycle[intersection] = False

            if not signal_first_cycle[intersection]:
                # Enforce full cycle before allowing optimizations
                current_state = signal_states.get(intersection, "red")

                if current_state == "red":
                    update_signal_state(mqtt_client, intersection, "green", green_duration)
                elif current_state == "green":
                    update_signal_state(mqtt_client, intersection, "yellow", BASE_YELLOW_DURATION)
                elif current_state == "yellow":
                    update_signal_state(mqtt_client, intersection, "red", BASE_RED_DURATION)
                    signal_first_cycle[intersection] = True  # Mark cycle completion
                
                continue  # Skip further updates until first cycle completes

            if emergency_mode.get(intersection, False):
                print(f"🚨 EMERGENCY MODE ACTIVE at {intersection}! Extending Green time.")
                update_signal_state(mqtt_client, intersection, "green", green_duration)
                update_signal_state(mqtt_client, intersection, "yellow", BASE_YELLOW_DURATION)
                update_signal_state(mqtt_client, intersection, "red", BASE_RED_DURATION)
                continue

            current_state = signal_states.get(intersection, "red")

            if current_state == "red" and "green" not in updated_intersections:
                update_signal_state(mqtt_client, intersection, "green", green_duration)
                updated_intersections.add("green")
            elif current_state == "green" and "yellow" not in updated_intersections:
                update_signal_state(mqtt_client, intersection, "yellow", BASE_YELLOW_DURATION)
                updated_intersections.add("yellow")
            elif current_state == "yellow" and "red" not in updated_intersections:
                update_signal_state(mqtt_client, intersection, "red", BASE_RED_DURATION)
                updated_intersections.add("red")

        # If all signals ended up in the same state, force a staggered cycle
        if not validate_signal_distribution():
            stagger_signals(mqtt_client)

        time.sleep(0.5)  # Small delay before checking again

def stagger_signals(mqtt_client):
    """Force staggered updates if all signals are in the same state."""
    intersections = list(signal_states.keys())

    for i, intersection in enumerate(intersections):
        state_order = ["green", "yellow", "red"]
        new_state = state_order[i % len(state_order)]  # Distribute states
        duration = (
            ACO_DEFAULT_DURATION if new_state == "green"
            else BASE_YELLOW_DURATION if new_state == "yellow"
            else BASE_RED_DURATION
        )
        update_signal_state(mqtt_client, intersection, new_state, duration)

    print("🔄 Staggered signal update applied to prevent deadlock.")
