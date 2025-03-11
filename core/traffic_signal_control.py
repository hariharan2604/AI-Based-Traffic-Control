import json
import time
import threading
from config.settings import ACO_DEFAULT_DURATION, ACO_MAX_DURATION
from core.mqtt_client import manual_override, manual_override_lock, vehicle_density_data, vehicle_data_lock

def aco_optimize_signal(density_data):
    """Uses ACO to determine optimal traffic signal durations."""
    signal_durations = {}
    total_density = sum(sum(density.values()) for density in density_data.values())

    for intersection, density in density_data.items():
        if total_density == 0:
            signal_durations[intersection] = ACO_DEFAULT_DURATION
        else:
            proportion = sum(density.values()) / total_density
            signal_durations[intersection] = int(
                ACO_DEFAULT_DURATION + (proportion * (ACO_MAX_DURATION - ACO_DEFAULT_DURATION))
            )

    return signal_durations

def manage_traffic_signals(mqtt_client):
    """Handles signal durations, using manual override if present, otherwise using ACO."""
    while True:
        with manual_override_lock:
            if manual_override:  # If any manual override exists, ACO stops working
                signal_durations = manual_override.copy()
                print("Manual override active. ACO paused.")
            else:
                with vehicle_data_lock:
                    density_data = vehicle_density_data.copy()
                
                if not density_data:
                    print("No vehicle density data available. Using default durations.")
                    time.sleep(5)
                    continue
                
                print(f"Current Density Data: {density_data}")  # Debugging
                signal_durations = aco_optimize_signal(density_data)

        # Publish the updated durations
        for intersection, duration in signal_durations.items():
            mqtt_client.publish(f"signal/duration/{intersection}", json.dumps({"duration": duration}))
            print(f"Updated duration for {intersection}: {duration}s")  # Debugging

        time.sleep(5)
