import json
import time
from collections import deque
from config.settings import ACO_DEFAULT_DURATION, ACO_MAX_DURATION, MIN_UPDATE_THRESHOLD
from core.mqtt_client import manual_override, manual_override_lock, vehicle_density_data, vehicle_data_lock

# Stores past densities to smooth transitions
density_history = {}

def weighted_moving_average(intersection, new_density):
    """Computes a weighted moving average for smoother ACO updates."""
    if intersection not in density_history:
        density_history[intersection] = deque(maxlen=3)  # Store last 3 updates
    
    density_history[intersection].append(new_density)
    weights = [0.2, 0.3, 0.5]  # More weight to recent densities
    return sum(w * d for w, d in zip(weights, density_history[intersection]))

def aco_optimize_signal(density_data):
    """ACO optimization with smoother transitions."""
    signal_durations = {}
    total_density = sum(sum(density.values()) for density in density_data.values())

    for intersection, density in density_data.items():
        smoothed_density = weighted_moving_average(intersection, sum(density.values()))

        if total_density == 0:
            optimized_duration = ACO_DEFAULT_DURATION
        else:
            proportion = smoothed_density / total_density
            optimized_duration = int(
                ACO_DEFAULT_DURATION + (proportion * (ACO_MAX_DURATION - ACO_DEFAULT_DURATION))
            )

        signal_durations[intersection] = optimized_duration

    return signal_durations

def manage_traffic_signals(mqtt_client):
    """Handles signal updates dynamically based on traffic changes."""
    last_signal_durations = {}

    while True:
        with manual_override_lock:
            if manual_override:  # If manual override is active, use it
                signal_durations = manual_override.copy()
                print("🚦 Manual override active. ACO paused.")
            else:
                with vehicle_data_lock:
                    density_data = vehicle_density_data.copy()
                
                if not density_data:
                    print("⚠️ No vehicle density data available. Using default durations.")
                    time.sleep(5)
                    continue
                
                signal_durations = aco_optimize_signal(density_data)

        # Select intersection with the highest duration for GREEN signal
        green_intersection = max(signal_durations, key=signal_durations.get, default=None)

        # Only update signals if there's a significant change
        for intersection, duration in signal_durations.items():
            if (intersection not in last_signal_durations or 
                abs(last_signal_durations[intersection] - duration) >= MIN_UPDATE_THRESHOLD):
                
                # Send MQTT update with signal status
                signal_status = {
                    "duration": duration,
                    "state": "green" if intersection == green_intersection else "red"
                }
                
                mqtt_client.publish(f"signal/status/{intersection}", json.dumps(signal_status))
                last_signal_durations[intersection] = duration
                print(f"✅ Signal {intersection}: {signal_status['state'].upper()} for {duration}s")

        time.sleep(1)  # Check every second

