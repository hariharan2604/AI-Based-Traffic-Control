import json
import time
from collections import deque
from config.settings import (
    ACO_DEFAULT_DURATION,
    ACO_MAX_DURATION,
    BASE_YELLOW_DURATION,
    EMERGENCY_GREEN_BOOST,
    MIN_GREEN_DURATION,
)
from core.mqtt_client import (
    manual_override,
    manual_override_lock,
    vehicle_density_data,
    vehicle_data_lock,
    emergency_events,
)

# Store signal states, timers, and density history
signal_states = {}
signal_timers = {}
density_history = {}
active_signal = None

def initialize_signals(mqtt_client):
    """Initialize traffic signals: One pair starts GREEN, the other RED."""
    global signal_states, active_signal
    
    signal_pairs = [("4001", "4003"), ("4002", "4004")]
    signal_states = {signal: "red" for pair in signal_pairs for signal in pair}
    
    active_signal = signal_pairs[0]  # First pair starts GREEN
    
    for signal in active_signal:
        update_signal(mqtt_client, signal, "green", ACO_DEFAULT_DURATION)
    for signal in signal_pairs[1]:
        update_signal(mqtt_client, signal, "red", ACO_DEFAULT_DURATION)
    
    print(f"🚦 Initialization complete. {active_signal} starts as GREEN.")

def weighted_moving_average(signal, new_density):
    """Smooths density fluctuations using a weighted moving average."""
    if signal not in density_history:
        density_history[signal] = deque(maxlen=3)
    density_history[signal].append(new_density)
    weights = [0.2, 0.3, 0.5]
    return sum(w * d for w, d in zip(weights, density_history[signal]))

def aco_optimize_signal(density_data):
    """ACO-based optimization to calculate Green time for each signal pair."""
    signal_pairs = [("4001", "4003"), ("4002", "4004")]
    pair_durations = {}
    total_density = sum(sum(d.values()) for d in density_data.values())

    for pair in signal_pairs:
        pair_density = sum(sum(density_data.get(signal, {}).values()) for signal in pair)
        smoothed_density = sum(weighted_moving_average(signal, sum(density_data.get(signal, {}).values())) for signal in pair)
        
        if any(signal in emergency_events for signal in pair):
            green_duration = min(ACO_MAX_DURATION, ACO_DEFAULT_DURATION + EMERGENCY_GREEN_BOOST)
        else:
            green_duration = max(MIN_GREEN_DURATION, int(
                ACO_DEFAULT_DURATION + ((pair_density / total_density) * (ACO_MAX_DURATION - ACO_DEFAULT_DURATION))
            )) if total_density > 0 else ACO_DEFAULT_DURATION
        
        pair_durations[pair] = green_duration
    
    return pair_durations

def update_signal(mqtt_client, signal, state, duration):
    """Publish signal state to MQTT and update tracking."""
    signal_states[signal] = state
    signal_timers[signal] = time.time()
    payload = {"state": state, "duration": duration, "emergency": signal in emergency_events}
    mqtt_client.publish(f"signal/status/{signal}", json.dumps(payload))
    print(f"🚦 {signal}: {state.upper()} for {duration}s (Emergency: {signal in emergency_events})")

def cycle_signals(mqtt_client, ws_servers):
    """Manages traffic signals with alternate intersections in green."""
    global active_signal
    signal_pairs = [("4001", "4003"), ("4002", "4004")]
    pair_index = 0
    initialized = False
    
    while True:
        while not all(ws.client_count > 0 for ws in ws_servers):
            print("⏸️ Waiting for WebSocket clients...")
            time.sleep(2)
            initialized = False
        
        if not initialized:
            print("🔄 Reinitializing signals...")
            initialize_signals(mqtt_client)
            initialized = True  
        
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
        
        next_pair_durations = aco_optimize_signal(density_data)
        
        while True:
            if not all(ws.client_count > 0 for ws in ws_servers):
                print("⏸️ WebSocket client disconnected. Pausing signals.")
                initialized = False  
                break
            
            current_pair = signal_pairs[pair_index]
            next_pair = signal_pairs[(pair_index + 1) % 2]
            
            for signal in current_pair:
                update_signal(mqtt_client, signal, "yellow", BASE_YELLOW_DURATION)
            time.sleep(BASE_YELLOW_DURATION)
            
            for signal in current_pair:
                update_signal(mqtt_client, signal, "red", next_pair_durations.get(next_pair, ACO_DEFAULT_DURATION)+BASE_YELLOW_DURATION)
            
            active_signal = next_pair
            green_duration = next_pair_durations.get(next_pair, ACO_DEFAULT_DURATION)
            
            for signal in next_pair:
                update_signal(mqtt_client, signal, "green", green_duration)
            
            time.sleep(green_duration)
            pair_index = (pair_index + 1) % 2
