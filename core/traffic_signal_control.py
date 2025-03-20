# import json
# import time
# from collections import deque
# from config.settings import (
#     ACO_DEFAULT_DURATION,
#     ACO_MAX_DURATION,
#     BASE_YELLOW_DURATION,
#     EMERGENCY_GREEN_BOOST,
#     MIN_GREEN_DURATION,
# )
# from core.mqtt_client import (
#     manual_override,
#     manual_override_lock,
#     vehicle_density_data,
#     vehicle_data_lock,
#     emergency_events,
# )

# signal_states = {}
# signal_timers = {}
# density_history = {}
# active_signal = None

# def initialize_signals(mqtt_client):
#     global signal_states, active_signal
    
#     signal_pairs = [("4001", "4003"), ("4002", "4004")]
#     signal_states = {signal: "red" for pair in signal_pairs for signal in pair}
#     active_signal = signal_pairs[0]  # First pair starts GREEN
    
#     for signal in active_signal:
#         update_signal(mqtt_client, signal, "green", ACO_DEFAULT_DURATION)
#     for signal in signal_pairs[1]:
#         update_signal(mqtt_client, signal, "red", ACO_DEFAULT_DURATION)
    
#     print(f"🚦 Initialization complete. {active_signal} starts as GREEN.")



# def check_emergency_interrupt():
#     """Ensures emergency events are not missed due to rapid clearing."""
#     global emergency_events

#     if not emergency_events:
#         return None  # No emergency detected

#     for pair in [("4001", "4003"), ("4002", "4004")]:
#         if any(signal in emergency_events for signal in pair):
#             print(f"⚠️ Emergency event detected in {pair}. Holding for 10s")
#             time.sleep(10)  # Hold the emergency state to ensure detection
#             return pair

#     return None

# def handle_emergency(mqtt_client, emergency_pair):
#     """Handles emergency events by switching signals immediately."""
#     global active_signal
#     print(f"🚨 Emergency detected in {emergency_pair}! Interrupting normal cycle.")
    
#     print(f"🟡 Turning {active_signal} yellow for {BASE_YELLOW_DURATION}s")
#     for signal in active_signal:
#         update_signal(mqtt_client, signal, "yellow", BASE_YELLOW_DURATION)

#     time.sleep(BASE_YELLOW_DURATION)

#     print(f"🔴 Turning {active_signal} red")
#     for signal in active_signal:
#         update_signal(mqtt_client, signal, "red", ACO_MAX_DURATION + EMERGENCY_GREEN_BOOST + BASE_YELLOW_DURATION)

#     print(f"🟢 Turning {emergency_pair} green for {ACO_MAX_DURATION + EMERGENCY_GREEN_BOOST}s")
#     for signal in emergency_pair:
#         update_signal(mqtt_client, signal, "green", ACO_MAX_DURATION + EMERGENCY_GREEN_BOOST)

#     active_signal = emergency_pair  
#     time.sleep(ACO_MAX_DURATION + EMERGENCY_GREEN_BOOST)
    
# def cycle_signals(mqtt_client, ws_servers):
#     """Manages traffic signals, ensuring immediate response to emergencies and synchronized red duration."""
#     global active_signal
#     signal_pairs = [("4001", "4003"), ("4002", "4004")]
#     pair_index = 0
#     initialized = False

#     while True:
#         # Wait for all WebSocket clients to be connected
#         while not all(ws.client_count > 0 for ws in ws_servers):
#             print("⏸️ Waiting for WebSocket clients...")
#             time.sleep(2)
#             initialized = False
        
#         if not initialized:
#             print("🔄 Reinitializing signals...")
#             initialize_signals(mqtt_client)
#             initialized = True  

#         with manual_override_lock:
#             is_manual_active = bool(manual_override)

#         with vehicle_data_lock:
#             density_data = vehicle_density_data.copy()

#         print(f"📢 Current Emergency Events: {emergency_events}")
        
#         if is_manual_active:
#             print("🔧 Manual Override Active. Skipping ACO.")
#             time.sleep(2)
#             continue

#         if not density_data:
#             print("⚠️ No density data available. Using default cycle.")
#             time.sleep(2)
#             continue

#         # Check for emergency events before starting a new cycle
#         emergency_pair = check_emergency_interrupt()
#         if emergency_pair:
#             print(f"🚨 Emergency Detected for: {emergency_pair}")
#             handle_emergency(mqtt_client, emergency_pair)
#             continue  # Restart the loop after handling emergency

#         # Normal ACO-based cycling if no emergency
#         next_pair_durations = aco_optimize_signal(density_data)
#         current_pair = signal_pairs[pair_index]
#         next_pair = signal_pairs[(pair_index + 1) % 2]

#         # Transition current pair to yellow
#         print(f"🟡 Transitioning {current_pair} to yellow for {BASE_YELLOW_DURATION}s")
#         for signal in current_pair:
#             update_signal(mqtt_client, signal, "yellow", BASE_YELLOW_DURATION)
        
#         time.sleep(BASE_YELLOW_DURATION)  # Wait for yellow time

#         # Check again for emergency before setting new green
#         emergency_pair = check_emergency_interrupt()
#         if emergency_pair:
#             print(f"🚨 Emergency detected in {emergency_pair}! Switching immediately.")
#             handle_emergency(mqtt_client, emergency_pair)
#             continue  # Restart loop

#         # Get optimized green duration
#         green_duration = next_pair_durations.get(next_pair, ACO_DEFAULT_DURATION)

#         # Set next pair to green
#         print(f"🟢 Setting {next_pair} to green for {green_duration}s")
#         for signal in next_pair:
#             update_signal(mqtt_client, signal, "green", green_duration)

#         # Ensure the current pair is set to red for the exact green + yellow duration of the next pair
#         red_duration = green_duration + BASE_YELLOW_DURATION
#         print(f"🔴 Setting {current_pair} to red for {red_duration}s")
#         for signal in current_pair:
#             update_signal(mqtt_client, signal, "red", red_duration)

#         active_signal = next_pair  # Update active signal
#         time.sleep(green_duration)  # Wait for green duration
#         pair_index = (pair_index + 1) % 2  # Move to next pair


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
    active_signal = signal_pairs[0]  # First pair starts GREEN
    
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

    # Convert keys to strings to prevent lookup issues
    density_data = {str(k): v for k, v in density_data.items()}

    print(f"📊 Density Data Received: {json.dumps(density_data, indent=2)}")

    total_density = sum(sum(vehicle_counts.values()) for vehicle_counts in density_data.values())
    print(f"🔢 Total Density: {total_density}")

    # Set a minimum share (so no pair gets too little time)
    MIN_RATIO = 0.35  # 35% minimum allocation
    MAX_RATIO = 0.65  # 65% maximum allocation

    for pair in signal_pairs:
        pair_density = sum(sum(density_data.get(str(signal), {}).values()) for signal in pair)
        print(f"✅ Pair {pair} - Calculated Density: {pair_density}")

        if any(signal in emergency_events for signal in pair):
            green_duration = ACO_MAX_DURATION + EMERGENCY_GREEN_BOOST
            print(f"🚨 Emergency detected for {pair}. Green duration: {green_duration}s")
        else:
            # Calculate normalized density ratio
            density_ratio = (pair_density / (total_density + 1e-6)) if total_density > 0 else 0.5
            density_ratio = max(MIN_RATIO, min(MAX_RATIO, density_ratio))  # Ensure fairness

            # Apply the ratio to scale between default and max duration
            green_duration = int(ACO_DEFAULT_DURATION + density_ratio * (ACO_MAX_DURATION - ACO_DEFAULT_DURATION))

        pair_durations[pair] = green_duration
        print(f"🟢 ACO Optimized Duration for {pair}: {green_duration}s")

    return pair_durations


def update_signal(mqtt_client, signal, state, duration):
    signal_states[signal] = state
    signal_timers[signal] = time.time()
    payload = {"state": state, "duration": duration, "emergency": signal in emergency_events}
    mqtt_client.publish(f"signal/status/{signal}", json.dumps(payload))
    print(f"🚦 Updating {signal} to {state.upper()} for {duration}s (Emergency: {signal in emergency_events})")
def check_emergency_interrupt():
    """Ensures emergency events are not missed due to rapid clearing."""
    global emergency_events

    if not emergency_events:
        return None  # No emergency detected

    # Convert emergency event signals to strings (to avoid mismatches)
    emergency_set = {str(signal) for signal in emergency_events}

    for pair in [("4001", "4003"), ("4002", "4004")]:
        if any(signal in emergency_set for signal in pair):
            print(f"⚠️ Emergency event detected in {pair}. Immediate action required.")
            return pair

    return None


def handle_emergency(mqtt_client, emergency_pair):
    """Handles emergency events by switching signals immediately."""
    global active_signal
    print(f"🚨 Emergency detected in {emergency_pair}! Interrupting normal cycle.")
    
    print(f"🟡 Turning {active_signal} yellow for {BASE_YELLOW_DURATION}s")
    for signal in active_signal:
        update_signal(mqtt_client, signal, "yellow", BASE_YELLOW_DURATION)

    time.sleep(BASE_YELLOW_DURATION)

    print(f"🔴 Turning {active_signal} red")
    for signal in active_signal:
        update_signal(mqtt_client, signal, "red", ACO_MAX_DURATION + EMERGENCY_GREEN_BOOST + BASE_YELLOW_DURATION)

    print(f"🟢 Turning {emergency_pair} green for {ACO_MAX_DURATION + EMERGENCY_GREEN_BOOST}s")
    for signal in emergency_pair:
        update_signal(mqtt_client, signal, "green", ACO_MAX_DURATION + EMERGENCY_GREEN_BOOST)

    active_signal = emergency_pair  
    time.sleep(ACO_MAX_DURATION + EMERGENCY_GREEN_BOOST)
    
def cycle_signals(mqtt_client, ws_servers):
    """Manages traffic signals, ensuring immediate response to emergencies and synchronized red duration."""
    global active_signal
    signal_pairs = [("4001", "4003"), ("4002", "4004")]
    pair_index = 0
    initialized = False

    while True:
        # Wait for all WebSocket clients to be connected
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

        print(f"📢 Current Emergency Events: {emergency_events}")
        
        # Check for emergency immediately
        emergency_pair = check_emergency_interrupt()
        print(f"📢 Current Emergency pair: {emergency_pair}")
        if emergency_pair:
            handle_emergency(mqtt_client, emergency_pair)
            continue  # Restart the loop after handling emergency
        
        if is_manual_active:
            print("🔧 Manual Override Active. Skipping ACO.")
            time.sleep(2)
            continue

        if not density_data:
            print("⚠️ No density data available. Using default cycle.")
            time.sleep(2)
            continue

        # Normal ACO-based cycling if no emergency
        next_pair_durations = aco_optimize_signal(density_data)
        current_pair = signal_pairs[pair_index]
        next_pair = signal_pairs[(pair_index + 1) % 2]

        # Check again for emergency before setting yellow
        emergency_pair = check_emergency_interrupt()
        if emergency_pair:
            handle_emergency(mqtt_client, emergency_pair)
            continue  # Restart loop

        # Transition current pair to yellow
        print(f"🟡 Transitioning {current_pair} to yellow for {BASE_YELLOW_DURATION}s")
        for signal in current_pair:
            update_signal(mqtt_client, signal, "yellow", BASE_YELLOW_DURATION)
        
        time.sleep(BASE_YELLOW_DURATION)  # Wait for yellow time

        # Check again for emergency before setting green
        emergency_pair = check_emergency_interrupt()
        if emergency_pair:
            handle_emergency(mqtt_client, emergency_pair)
            continue  # Restart loop

        # Get optimized green duration
        green_duration = next_pair_durations.get(next_pair, ACO_DEFAULT_DURATION)

        # Set next pair to green
        print(f"🟢 Setting {next_pair} to green for {green_duration}s")
        for signal in next_pair:
            update_signal(mqtt_client, signal, "green", green_duration)

        # Ensure the current pair is set to red for the exact green + yellow duration of the next pair
        red_duration = green_duration + BASE_YELLOW_DURATION
        print(f"🔴 Setting {current_pair} to red for {red_duration}s")
        for signal in current_pair:
            update_signal(mqtt_client, signal, "red", red_duration)

        active_signal = next_pair  # Update active signal
        time.sleep(green_duration)  # Wait for green duration
        pair_index = (pair_index + 1) % 2  # Move to next pair
