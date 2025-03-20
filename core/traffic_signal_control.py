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
    
    print(f"🚦 Initialization complete. {active_signal} starts as GREEN.")

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

    print(f"📊 Density Data Received: {json.dumps(density_data, indent=2)}")

    total_density = sum(sum(vehicle_counts.values()) for vehicle_counts in density_data.values())
    print(f"🔢 Total Density: {total_density}")

    MIN_RATIO = 0.35  
    MAX_RATIO = 0.65  

    for pair in signal_pairs:
        pair_density = sum(sum(density_data.get(str(signal), {}).values()) if str(signal) in density_data else 0 for signal in pair)
        print(f"✅ Pair {pair} - Calculated Density: {pair_density}")

        if any(signal in emergency_events for signal in pair):
            green_duration = ACO_MAX_DURATION + EMERGENCY_GREEN_BOOST
            print(f"🚨 Emergency detected for {pair}. Green duration: {green_duration}s")
        else:
            density_ratio = (pair_density / (total_density + 1e-6)) if total_density > 0 else 0.5
            density_ratio = max(MIN_RATIO, min(MAX_RATIO, density_ratio))

            green_duration = int(ACO_DEFAULT_DURATION + density_ratio * (ACO_MAX_DURATION - ACO_DEFAULT_DURATION))

        pair_durations[pair] = green_duration
        print(f"🟢 ACO Optimized Duration for {pair}: {green_duration}s")

    return pair_durations

def update_signal(mqtt_client, signal, state, duration):
    signal_states[signal] = state
    signal_timers[signal] = time.time()
    payload = {"state": state, "duration": duration, "emergency": str(signal) in emergency_events}
    mqtt_client.publish(f"signal/status/{signal}", json.dumps(payload))
    print(f"🚦 Updating {signal} to {state.upper()} for {duration}s (Emergency: {signal in emergency_events})")

def check_emergency_interrupt():
    global emergency_events

    if not emergency_events:
        return None  

    emergency_set = {str(signal) for signal in emergency_events}

    for pair in [("4001", "4003"), ("4002", "4004")]:
        if any(signal in emergency_set for signal in pair):
            print(f"⚠️ Emergency event detected in {pair}. Immediate action required.")
            return pair

    return None

def handle_emergency(mqtt_client, emergency_pair):
    global active_signal
    print(f"🚨 Emergency detected in {emergency_pair}! Interrupting normal cycle.")
    
    print(f"🟡 Turning {active_signal} yellow for {BASE_YELLOW_DURATION}s")
    for signal in active_signal:
        update_signal(mqtt_client, signal, "yellow", BASE_YELLOW_DURATION)
    
    time.sleep(BASE_YELLOW_DURATION)
    
    red_duration = ACO_MAX_DURATION + EMERGENCY_GREEN_BOOST + BASE_YELLOW_DURATION
    print(f"🔴 Turning {active_signal} red for {red_duration}s")
    for signal in active_signal:
        update_signal(mqtt_client, signal, "red", red_duration)
    
    green_duration = ACO_MAX_DURATION + EMERGENCY_GREEN_BOOST
    print(f"🟢 Turning {emergency_pair} green for {green_duration}s")
    for signal in emergency_pair:
        update_signal(mqtt_client, signal, "green", green_duration)
    
    active_signal = emergency_pair  
    time.sleep(green_duration)  
    
    for _ in range(int(ACO_MAX_DURATION / 2)):  
        time.sleep(2)
        new_emergency = check_emergency_interrupt()
        if new_emergency and new_emergency != emergency_pair:
            print(f"🚨 New emergency detected: {new_emergency}! Switching immediately.")
            handle_emergency(mqtt_client, new_emergency)
            return

def cycle_signals(mqtt_client, ws_servers):
    global active_signal
    signal_pairs = [("4001", "4003"), ("4002", "4004")]
    pair_index = 0
    initialized = False
    timeout = 60  

    start_time = time.time()

    while True:
        while not all(ws.client_count > 0 for ws in ws_servers):
            print("⏸️ Waiting for WebSocket clients...")
            time.sleep(2)

            if time.time() - start_time > timeout:
                print("⚠️ Timeout waiting for WebSocket clients. Proceeding with default settings.")
                break

            initialized = False
        
        if not initialized:
            print("🔄 Reinitializing signals...")
            initialize_signals(mqtt_client)
            initialized = True  

        with manual_override_lock:
            is_manual_active = bool(manual_override)

        with vehicle_data_lock:
            density_data = vehicle_density_data.copy()

        print(f"📢 Current Emergency Events: {emergency_events}")
        
        emergency_pair = check_emergency_interrupt()
        print(f"📢 Current Emergency pair: {emergency_pair}")
        if emergency_pair:
            handle_emergency(mqtt_client, emergency_pair)
            continue  

        if is_manual_active:
            print("🔧 Manual Override Active. Skipping ACO.")
            time.sleep(2)
            continue

        if not density_data:
            print("⚠️ No density data available. Using default cycle.")
            time.sleep(2)
            continue

        next_pair_durations = aco_optimize_signal(density_data)
        current_pair = signal_pairs[pair_index]
        next_pair = signal_pairs[(pair_index + 1) % 2]

        emergency_pair = check_emergency_interrupt()
        if emergency_pair:
            handle_emergency(mqtt_client, emergency_pair)
            continue  

        print(f"🟡 Transitioning {current_pair} to yellow for {BASE_YELLOW_DURATION}s")
        for signal in current_pair:
            update_signal(mqtt_client, signal, "yellow", BASE_YELLOW_DURATION)
        
        time.sleep(BASE_YELLOW_DURATION)

        emergency_pair = check_emergency_interrupt()
        if emergency_pair:
            handle_emergency(mqtt_client, emergency_pair)
            continue  

        green_duration = next_pair_durations.get(next_pair, ACO_DEFAULT_DURATION)

        print(f"🟢 Setting {next_pair} to green for {green_duration}s")
        for signal in next_pair:
            update_signal(mqtt_client, signal, "green", green_duration)

        red_duration = green_duration + BASE_YELLOW_DURATION
        print(f"🔴 Setting {current_pair} to red for {red_duration}s")
        for signal in current_pair:
            update_signal(mqtt_client, signal, "red", red_duration)

        active_signal = next_pair  
        time.sleep(green_duration)  
        pair_index = (pair_index + 1) % 2  
