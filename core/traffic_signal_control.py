import json
import time
import logging
import sys

from collections import deque
from config.settings import (
    ACO_DEFAULT_DURATION,
    ACO_MAX_DURATION,
    BASE_YELLOW_DURATION,
    EMERGENCY_GREEN_BOOST,
)
from core.mqtt_client import (
    manual_override,
    manual_override_lock,
    vehicle_density_data,
    vehicle_data_lock,
    emergency_events,
)

logging.getLogger(__name__).addHandler(logging.StreamHandler(sys.stdout))
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(message)s",
)
signal_states = {}
signal_timers = {}
density_history = {}
active_signal = None

def initialize_signals(mqtt_client):
    global signal_states, active_signal
    
    signal_pairs = [("4001", "4003"), ("4002", "4004")]
    signal_states = {signal: "red" for pair in signal_pairs for signal in pair}
    active_signal = signal_pairs[0]
    
    for signal in active_signal:
        update_signal(mqtt_client, signal, "green", ACO_DEFAULT_DURATION)
    for signal in signal_pairs[1]:
        update_signal(mqtt_client, signal, "red", ACO_DEFAULT_DURATION)
    
    logging.info(f"🚦 Initialization complete. {active_signal} starts as GREEN.")
    # emergency_events.add(4004)

def weighted_moving_average(signal, new_density):
    if signal not in density_history:
        density_history[signal] = deque(maxlen=3)
    density_history[signal].append(new_density)
    weights = [0.2, 0.3, 0.5]
    return sum(w * d for w, d in zip(weights, density_history[signal]))

def aco_optimize_signal(density_data):
    signal_pairs = [("4001", "4003"), ("4002", "4004")]
    pair_durations = {}
    
    density_data = {str(k): v for k, v in density_data.items()}
    logging.info(f"📊 Density Data Received: {json.dumps(density_data, indent=2)}")
    
    total_density = sum(sum(vehicle_counts.values()) for vehicle_counts in density_data.values())
    logging.info(f"🔢 Total Density: {total_density}")
    
    MIN_RATIO = 0.35
    MAX_RATIO = 0.65
    
    for pair in signal_pairs:
        pair_density = sum(
            (
                sum(density_data.get(str(signal), {}).values())
                if str(signal) in density_data
                else 0
            )
            for signal in pair
        )
        logging.info(f"✅ Pair {pair} - Calculated Density: {pair_density}")
        
        if any(signal in emergency_events for signal in pair):
            green_duration = ACO_MAX_DURATION + EMERGENCY_GREEN_BOOST
            logging.info(f"🚨 Emergency detected for {pair}. Green duration: {green_duration}s")
        else:
            density_ratio = (pair_density / (total_density + 1e-6)) if total_density > 0 else 0.5
            density_ratio = max(MIN_RATIO, min(MAX_RATIO, density_ratio))
            green_duration = int(ACO_DEFAULT_DURATION + density_ratio * (ACO_MAX_DURATION - ACO_DEFAULT_DURATION))
        
        pair_durations[pair] = green_duration
        logging.info(f"🟢 ACO Optimized Duration for {pair}: {green_duration}s")
    
    return pair_durations

def update_signal(mqtt_client, signal, state, duration):
    signal_states[signal] = state
    signal_timers[signal] = time.time()
    payload = {
        "state": state,
        "duration": duration,
        "emergency": str(signal) in emergency_events,
    }
    mqtt_client.publish(f"signal/status/{signal}", json.dumps(payload))
    logging.info(f"🚦 Updating {signal} to {state.upper()} for {duration}s (Emergency: {signal in emergency_events})")

def check_emergency_interrupt():
    if not emergency_events:
        return None
    
    emergency_set = {str(signal) for signal in emergency_events}
    for pair in [("4001", "4003"), ("4002", "4004")]:
        if any(signal in emergency_set for signal in pair):
            logging.info(f"⚠️ Emergency event detected in {pair}. Immediate action required.")
            return pair
    return None

def handle_emergency(mqtt_client, emergency_pair):
    global active_signal
    logging.info(f"🚨 Emergency detected in {emergency_pair}! Interrupting normal cycle.")
    
    green_duration = ACO_MAX_DURATION + EMERGENCY_GREEN_BOOST
    yellow_duration = BASE_YELLOW_DURATION
    red_duration = green_duration + yellow_duration  # Red duration includes next yellow phase

    # Transition current active signals to yellow
    for signal in active_signal:
        update_signal(mqtt_client, signal, "yellow", yellow_duration)

    time.sleep(yellow_duration)  # Ensure current signals complete their yellow phase

    # Now, transition the current active signals to red
    for signal in active_signal:
        update_signal(mqtt_client, signal, "red", red_duration)

    # After ensuring no overlap, turn the next pair green
    for signal in emergency_pair:
        update_signal(mqtt_client, signal, "green", green_duration)

    active_signal = emergency_pair
    time.sleep(red_duration)

def cycle_signals(mqtt_client, ws_servers):
    global active_signal
    signal_pairs = [("4001", "4003"), ("4002", "4004")]
    pair_index = 0
    initialized = False
    
    while True:
        if not initialized:
            initialize_signals(mqtt_client)
            initialized = True
        
        emergency_pair = check_emergency_interrupt()
        if emergency_pair:
            handle_emergency(mqtt_client, emergency_pair)
            continue
        
        with manual_override_lock:
            if manual_override:
                logging.info("🔧 Manual Override Active. Skipping ACO.")
                time.sleep(2)
                continue
        
        with vehicle_data_lock:
            density_data = vehicle_density_data.copy()
        
        next_pair_durations = aco_optimize_signal(density_data)
        current_pair = signal_pairs[pair_index]
        next_pair = signal_pairs[(pair_index + 1) % 2]
        
        green_duration = next_pair_durations.get(next_pair, ACO_DEFAULT_DURATION)
        red_duration = green_duration + BASE_YELLOW_DURATION
        
        for signal in current_pair:
            update_signal(mqtt_client, signal, "yellow", BASE_YELLOW_DURATION)
        time.sleep(BASE_YELLOW_DURATION)
        
        for signal in current_pair:
            update_signal(mqtt_client, signal, "red", red_duration)
        
        for signal in next_pair:
            update_signal(mqtt_client, signal, "green", green_duration)
        
        active_signal = next_pair
        time.sleep(red_duration)
        pair_index = (pair_index + 1) % 2
