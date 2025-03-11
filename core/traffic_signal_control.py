import json
import time
from config.settings import ACO_DEFAULT_DURATION, ACO_MAX_DURATION
from core.mqtt_handler import manual_override

def aco_optimize_signal(density_data):
    """Uses ACO to determine optimal traffic signal durations."""
    signal_durations = {}

    total_density = sum(sum(density.values()) for density in density_data.values())
    for intersection, density in density_data.items():
        if total_density == 0:
            signal_durations[intersection] = ACO_DEFAULT_DURATION
        else:
            proportion = sum(density.values()) / total_density
            signal_durations[intersection] = int(ACO_DEFAULT_DURATION + (proportion * (ACO_MAX_DURATION - ACO_DEFAULT_DURATION)))

    return signal_durations

def manage_traffic_signals(mqtt_client):
    """Optimizes and publishes signal durations via MQTT."""
    density_data = {}

    while True:
        for port in [4001, 4002, 4003, 4004]:
            # Fetch real-time vehicle density data from MQTT (to be implemented)
            density_data[port] = {}

        # Optimize signal duration using ACO
        signal_durations = aco_optimize_signal(density_data)

        # Apply manual overrides if present
        for intersection in signal_durations:
            if intersection in manual_override:
                signal_durations[intersection] = manual_override[intersection]

        # Publish optimized signal durations
        for intersection, duration in signal_durations.items():
            mqtt_client.publish(f"signal/duration/{intersection}", json.dumps({"duration": duration}))

        time.sleep(5)  # Optimize every 5 seconds
