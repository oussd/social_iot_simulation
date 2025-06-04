# src/simulations/scenario_generator.py

import random
import re 
from typing import List, Dict, Any, Optional, Callable # Added Callable
from dataclasses import dataclass, field 
import datetime # Unused, can be removed if not needed elsewhere
import json # For the helper save_scenario and if __name__ == '__main__'

# --- Dataclass for Jobs ---
@dataclass
class ScenarioJob:
    id: str
    job_type: str 
    timestamp: int 
    target_device_name: str 
    target_zone: Optional[str] = None
    
    priority: int = 2
    work_units_required: float = 1.0 
    deadline_time: int = 0 
    creation_time: int = 0 
    
    status: str = "PENDING"
    assigned_to_device_id: Optional[str] = None 
    work_units_done: float = 0.0
    completion_time: int = -1
    iot_app_reward: float = 10.0 # Changed from base_reward to match usage
    penalty_for_failure: int = 5
    parameters: Dict[str, Any] = field(default_factory=dict)
    sub_task_results: List[Dict] = field(default_factory=list)

    def __post_init__(self):
        if not self.creation_time:
            self.creation_time = self.timestamp
        # Deadline calculation was moved to job creation in generator functions
        # as it needs access to JOB_PROPERTIES and random.

# --- Default Configuration (Restored from original) ---
DEFAULT_NUM_ZONES = 4 
DEFAULT_DEVICES_PER_ZONE = {
    "TempSensor": 3,   
    "HVAC": 3,         
    "AccessPoint": 2,  
    "WindowSensor": 2, 
    "ZoneServer": 4    
}
DEFAULT_NUM_CENTRAL_SERVERS = 1 
DEFAULT_DURATION_MINUTES = 24 * 60 # 1440 minutes (original value)

FIXED_RANDOM_SEED = 42

DEFAULT_TARGET_TEMP_RANGE = (20.0, 25.0) # Original value
TEMP_CHANGE_PER_HVAC_CYCLE = 0.5 
TEMP_DROP_WINDOW_OPEN = 3.0 
INITIAL_ZONE_TEMP_RANGE = (18.0, 28.0) 

JOB_PROPERTIES = { # Restored JOB_PROPERTIES
    "SENSE_TEMPERATURE": {"work_units_base": (5, 15), "reward_base": 2.0, "penalty": 2, "deadline_offset_range": (5,10), "processing_time_estimate": 1}, 
    "CARD_SWIPE": {"work_units_base": (3,8), "reward_base": 1.0, "penalty": 1, "deadline_offset_range": (1,3), "processing_time_estimate": 1},
    "WINDOW_STATUS_CHANGE": {"work_units_base": (5,10), "reward_base": 0.5, "penalty": 0, "deadline_offset_range": (2,5), "processing_time_estimate": 1}, 
    "ADJUST_HVAC": {"work_units_base": (20,40), "reward_base": 10.0, "penalty": 5, "deadline_offset_range": (5,15), "processing_time_estimate": 3}, 
    "SERVER_COMM_TASK": {"work_units_base": (50,100), "reward_base": 15.0, "penalty": 3, "deadline_offset_range": (20,40), "processing_time_estimate": 10}, 
    "ZONE_SERVER_TASK": {"work_units_base": (30,60), "reward_base": 7.0, "penalty": 3, "deadline_offset_range": (15,30), "processing_time_estimate": 5}, 
    "PERIODIC_HEALTH_CHECK": {"work_units_base": (2,2), "reward_base": 0.1, "penalty": 0, "deadline_offset_range": (5,5), "processing_time_estimate": 1}
}

def _get_job_deadline(timestamp: int, job_type: str) -> int:
    props = JOB_PROPERTIES.get(job_type, {"deadline_offset_range": (5,10)}) # Default if not found
    return timestamp + random.randint(*props.get("deadline_offset_range", (5,10)))

def _get_random_work_units(job_type:str) -> int:
    props = JOB_PROPERTIES.get(job_type, {"work_units_base": (5,10)})
    return random.randint(*props.get("work_units_base",(5,10)))


def get_device_names(num_zones: int, 
                     devices_per_zone_config: Dict[str, int], 
                     num_central_servers: int) -> Dict[str, Any]:
    """Generates a structured map of device names for the simulation. (Original structure)"""
    device_map: Dict[str, Any] = {
        "zones": {}, 
        "central": {"CentralServer": []}, 
        "config_details": {
            "devices_per_zone_config": devices_per_zone_config.copy(), 
            "num_zones": num_zones,
            "num_central_servers": num_central_servers
        }
    }
    device_list_for_instantiation: List[Dict[str, Any]] = [] 

    for i in range(1, num_zones + 1):
        zone_name = f"Zone{i}"
        device_map["zones"][zone_name] = {}
        for device_type, count in devices_per_zone_config.items():
            device_map["zones"][zone_name][device_type] = []
            for j in range(1, count + 1):
                device_name = f"{zone_name}_{device_type}{j}"
                device_map["zones"][zone_name][device_type].append(device_name)
                device_list_for_instantiation.append({"name": device_name, "type": device_type, "zone_id_num": i})

    for k in range(1, num_central_servers + 1):
        server_name = f"CentralServer{k}"
        device_map["central"]["CentralServer"].append(server_name)
        device_list_for_instantiation.append({"name": server_name, "type": "CentralServer", "zone_id_num": None})
    
    device_map["config_details"]["device_list_for_instantiation_flat"] = device_list_for_instantiation
    return device_map


def generate_simple_control_scenario( 
    duration_minutes: int = DEFAULT_DURATION_MINUTES,
    num_zones: int = DEFAULT_NUM_ZONES,
    devices_per_zone_config: Optional[Dict[str, int]] = None, 
    num_central_servers: int = DEFAULT_NUM_CENTRAL_SERVERS
) -> List[Dict[str,Any]]: 
    
    if devices_per_zone_config is None:
        devices_per_zone_config = DEFAULT_DEVICES_PER_ZONE

    random.seed(FIXED_RANDOM_SEED)
    jobs_list: List[Dict[str, Any]] = []
    job_id_counter = 0

    # This variable holds the dictionary structure returned by get_device_names
    device_name_map_data = get_device_names(num_zones, devices_per_zone_config, num_central_servers)
    
    # This is the flat list of device configurations needed for iterating all devices
    actual_device_configs_list = device_name_map_data["config_details"]["device_list_for_instantiation_flat"]
    
    all_device_names_flat = [d_cfg['name'] for d_cfg in actual_device_configs_list]
    
    temp_sensors = [d['name'] for d in actual_device_configs_list if d['type'] == "TempSensor"]
    hvacs = [d['name'] for d in actual_device_configs_list if d['type'] == "HVAC"]
    access_points = [d['name'] for d in actual_device_configs_list if d['type'] == "AccessPoint"]
    window_sensors = [d['name'] for d in actual_device_configs_list if d['type'] == "WindowSensor"]
    zone_servers = [d['name'] for d in actual_device_configs_list if d['type'] == "ZoneServer"]
    central_servers = [d['name'] for d in actual_device_configs_list if d['type'] == "CentralServer"]
    
    zone_states: Dict[str, Dict[str, Any]] = {}
    for i in range(1, num_zones + 1):
        zone_name = f"Zone{i}"
        zone_hvacs_for_state = device_name_map_data["zones"].get(zone_name, {}).get("HVAC", [])
        zone_states[zone_name] = {
            "current_temperature": round(random.uniform(*INITIAL_ZONE_TEMP_RANGE), 1),
            "current_occupancy": 0,
            "hvac_status": {hvac_name: "OFF" for hvac_name in zone_hvacs_for_state} 
        }

    for minute in range(duration_minutes):
        hour_of_day = (minute // 60) % 24

        for z_idx in range(1, num_zones + 1):
            zone_name = f"Zone{z_idx}"
            current_temp = zone_states[zone_name]["current_temperature"]
            hvacs_in_zone = device_name_map_data["zones"].get(zone_name,{}).get("HVAC", []) 
            
            is_any_hvac_active = False
            for hvac_name in hvacs_in_zone:
                if zone_states[zone_name]["hvac_status"].get(hvac_name) == "HEATING":
                    current_temp += TEMP_CHANGE_PER_HVAC_CYCLE / 10 
                    is_any_hvac_active = True
                    if current_temp >= DEFAULT_TARGET_TEMP_RANGE[1]: 
                        zone_states[zone_name]["hvac_status"][hvac_name] = "OFF"
                elif zone_states[zone_name]["hvac_status"].get(hvac_name) == "COOLING":
                    current_temp -= TEMP_CHANGE_PER_HVAC_CYCLE / 10
                    is_any_hvac_active = True
                    if current_temp <= DEFAULT_TARGET_TEMP_RANGE[0]: 
                        zone_states[zone_name]["hvac_status"][hvac_name] = "OFF"
            
            if not is_any_hvac_active: 
                 if current_temp > 15: current_temp -= 0.01 
                 elif current_temp < 15: current_temp += 0.01
            zone_states[zone_name]["current_temperature"] = round(current_temp, 2)

        if minute % 10 == 0: 
            for zone_idx_loop in range(1, num_zones + 1):
                zone_name_loop = f"Zone{zone_idx_loop}"
                temp_sensors_in_zone = device_name_map_data["zones"].get(zone_name_loop, {}).get("TempSensor", [])
                hvacs_in_zone_list = device_name_map_data["zones"].get(zone_name_loop, {}).get("HVAC", [])
                current_zone_temp_reading = zone_states[zone_name_loop]["current_temperature"]
                
                for i, ts_name in enumerate(temp_sensors_in_zone):
                    job_id_counter += 1; props_sense = JOB_PROPERTIES["SENSE_TEMPERATURE"]
                    jobs_list.append({"id":f"job_{job_id_counter}", "job_type":"SENSE_TEMPERATURE", "timestamp":minute, "target_device_name":ts_name, "target_zone":zone_name_loop, "work_units_required":_get_random_work_units("SENSE_TEMPERATURE"), "iot_app_reward":props_sense["reward_base"], "penalty_for_failure":props_sense["penalty"], "parameters":{"sensed_temperature": round(current_zone_temp_reading,1), "sensor_index": i+1}, "deadline_time": _get_job_deadline(minute, "SENSE_TEMPERATURE")})
                    
                    if i < len(hvacs_in_zone_list): 
                        hvac_name = hvacs_in_zone_list[i]; hvac_action_params = {}; trigger_hvac = False
                        if current_zone_temp_reading < DEFAULT_TARGET_TEMP_RANGE[0] and zone_states[zone_name_loop]["hvac_status"].get(hvac_name) != "HEATING":
                            hvac_action_params = {"target_mode": "HEAT", "current_temp_reading": round(current_zone_temp_reading,1), "set_point": DEFAULT_TARGET_TEMP_RANGE[0]}; zone_states[zone_name_loop]["hvac_status"][hvac_name] = "HEATING"; trigger_hvac = True
                        elif current_zone_temp_reading > DEFAULT_TARGET_TEMP_RANGE[1] and zone_states[zone_name_loop]["hvac_status"].get(hvac_name) != "COOLING":
                            hvac_action_params = {"target_mode": "COOL", "current_temp_reading": round(current_zone_temp_reading,1), "set_point": DEFAULT_TARGET_TEMP_RANGE[1]}; zone_states[zone_name_loop]["hvac_status"][hvac_name] = "COOLING"; trigger_hvac = True
                        elif DEFAULT_TARGET_TEMP_RANGE[0] <= current_zone_temp_reading <= DEFAULT_TARGET_TEMP_RANGE[1] and zone_states[zone_name_loop]["hvac_status"].get(hvac_name) != "OFF":
                            hvac_action_params = {"target_mode": "OFF", "current_temp_reading": round(current_zone_temp_reading,1)}; zone_states[zone_name_loop]["hvac_status"][hvac_name] = "OFF"; trigger_hvac = True
                        
                        if trigger_hvac:
                            job_id_counter += 1; props_hvac = JOB_PROPERTIES["ADJUST_HVAC"]
                            jobs_list.append({"id":f"job_{job_id_counter}", "job_type":"ADJUST_HVAC", "timestamp":minute + 1, "target_device_name":hvac_name, "target_zone":zone_name_loop, "work_units_required":_get_random_work_units("ADJUST_HVAC"), "iot_app_reward":props_hvac["reward_base"], "penalty_for_failure":props_hvac["penalty"], "parameters":{**hvac_action_params, "triggered_by_sensor": ts_name, "zone_id": zone_name_loop}, "deadline_time": _get_job_deadline(minute+1, "ADJUST_HVAC")})
        
        swipe_probability = 0.0; direction = None
        if 7 <= hour_of_day < 9: swipe_probability = 0.4; direction = "IN"
        elif 12 <= hour_of_day < 14: swipe_probability = 0.2; direction = random.choice(["IN", "OUT"])
        elif 17 <= hour_of_day < 19: swipe_probability = 0.35; direction = "OUT"
        elif 9 <= hour_of_day < 17 : swipe_probability = 0.08; 
        
        if random.random() < swipe_probability:
            if not direction: direction = random.choice(["IN","OUT"]) 
            target_zone_name_swipe = random.choice(list(device_name_map_data["zones"].keys()))
            access_points_in_zone = device_name_map_data["zones"].get(target_zone_name_swipe, {}).get("AccessPoint", [])
            if access_points_in_zone:
                ap_name = random.choice(access_points_in_zone); job_id_counter += 1; props_swipe = JOB_PROPERTIES["CARD_SWIPE"]
                jobs_list.append({"id":f"job_{job_id_counter}", "job_type":"CARD_SWIPE", "timestamp":minute, "target_device_name":ap_name, "target_zone":target_zone_name_swipe, "parameters":{"direction": direction, "user_id": f"user_{random.randint(1, 500)}", "zone_id":target_zone_name_swipe}, "work_units_required":_get_random_work_units("CARD_SWIPE"), "iot_app_reward":props_swipe["reward_base"], "penalty_for_failure":props_swipe["penalty"], "deadline_time": _get_job_deadline(minute, "CARD_SWIPE")})
                if direction == "IN": zone_states[target_zone_name_swipe]["current_occupancy"] += 1
                elif direction == "OUT" and zone_states[target_zone_name_swipe]["current_occupancy"] > 0: zone_states[target_zone_name_swipe]["current_occupancy"] -= 1

        if 8 <= hour_of_day < 17 and random.random() < 0.0025: 
            target_zone_name_window = random.choice(list(device_name_map_data["zones"].keys())); 
            window_sensors_in_zone = device_name_map_data["zones"].get(target_zone_name_window, {}).get("WindowSensor", [])
            hvacs_in_zone_window = device_name_map_data["zones"].get(target_zone_name_window, {}).get("HVAC", [])
            if window_sensors_in_zone:
                window_sensor_name = random.choice(window_sensors_in_zone); job_id_counter += 1; props_window = JOB_PROPERTIES["WINDOW_STATUS_CHANGE"]
                jobs_list.append({"id":f"job_{job_id_counter}", "job_type":"WINDOW_STATUS_CHANGE", "timestamp":minute, "target_device_name":window_sensor_name, "target_zone":target_zone_name_window, "parameters":{"status": "OPENED", "window_id": window_sensor_name.split("_")[-1], "zone_id":target_zone_name_window}, "work_units_required":_get_random_work_units("WINDOW_STATUS_CHANGE"), "iot_app_reward":props_window["reward_base"], "penalty_for_failure":props_window["penalty"], "deadline_time":_get_job_deadline(minute, "WINDOW_STATUS_CHANGE")})
                zone_states[target_zone_name_window]["current_temperature"] = round(zone_states[target_zone_name_window]["current_temperature"] - TEMP_DROP_WINDOW_OPEN, 1)
                current_zone_temp_after_window = zone_states[target_zone_name_window]["current_temperature"]
                if hvacs_in_zone_window:
                    hvac_to_react = hvacs_in_zone_window[0] ; hvac_action_params_window = {}; trigger_hvac_window_reaction = False
                    if current_zone_temp_after_window < DEFAULT_TARGET_TEMP_RANGE[0] and zone_states[target_zone_name_window]["hvac_status"].get(hvac_to_react) != "HEATING":
                        hvac_action_params_window = {"target_mode": "HEAT", "current_temp_reading": round(current_zone_temp_after_window,1), "set_point": DEFAULT_TARGET_TEMP_RANGE[0]}; zone_states[target_zone_name_window]["hvac_status"][hvac_to_react] = "HEATING"; trigger_hvac_window_reaction = True
                    if trigger_hvac_window_reaction:
                        job_id_counter += 1; props_hvac_react_window = JOB_PROPERTIES["ADJUST_HVAC"]
                        jobs_list.append({"id":f"job_{job_id_counter}", "job_type":"ADJUST_HVAC", "timestamp":minute + 1, "target_device_name":hvac_to_react, "target_zone":target_zone_name_window, "parameters":{**hvac_action_params_window, "reason": "window_opened_event", "zone_id": target_zone_name_window}, "work_units_required":_get_random_work_units("ADJUST_HVAC"), "iot_app_reward":props_hvac_react_window["reward_base"], "penalty_for_failure":props_hvac_react_window["penalty"], "deadline_time":_get_job_deadline(minute+1, "ADJUST_HVAC")})
        
        if minute % 45 == 0: 
            for zone_idx_server in range(1, num_zones + 1):
                zone_name_server = f"Zone{zone_idx_server}"
                zone_servers_in_zone = device_name_map_data["zones"].get(zone_name_server, {}).get("ZoneServer", [])
                if zone_servers_in_zone:
                    server_name = random.choice(zone_servers_in_zone); current_occupancy = zone_states[zone_name_server]["current_occupancy"]; 
                    props_zserver = JOB_PROPERTIES["ZONE_SERVER_TASK"]
                    base_work_units_z = props_zserver["work_units_base"] 
                    dynamic_work_units = round(random.randint(*base_work_units_z) + min(5.0, current_occupancy * 0.1), 2) 
                    job_id_counter += 1
                    jobs_list.append({"id":f"job_{job_id_counter}", "job_type":"ZONE_SERVER_TASK", "timestamp":minute, "target_device_name":server_name, "target_zone":zone_name_server, "parameters":{"task_subtype": random.choice(["ZONE_DATA_CACHE", "LOCAL_AUTH_SYNC"]), "current_occupancy_for_load": current_occupancy, "zone_id": zone_name_server}, "work_units_required":dynamic_work_units, "iot_app_reward":props_zserver["reward_base"], "penalty_for_failure":props_zserver["penalty"], "deadline_time":_get_job_deadline(minute, "ZONE_SERVER_TASK")})

        if minute % 90 == 0 and device_name_map_data["central"].get("CentralServer"): 
            central_servers_list = device_name_map_data["central"]["CentralServer"]
            if central_servers_list: 
                server_name = random.choice(central_servers_list); job_id_counter += 1; props_cserver = JOB_PROPERTIES["SERVER_COMM_TASK"]
                jobs_list.append({"id":f"job_{job_id_counter}", "job_type":"SERVER_COMM_TASK", "timestamp":minute, "target_device_name":server_name, "parameters":{"task_subtype": random.choice(["GLOBAL_DATA_AGGREGATION", "INTER_ZONE_SYNC", "MAIN_BACKUP"])}, "work_units_required":_get_random_work_units("SERVER_COMM_TASK"), "iot_app_reward":props_cserver["reward_base"], "penalty_for_failure":props_cserver["penalty"], "deadline_time":_get_job_deadline(minute, "SERVER_COMM_TASK")})
        
        if minute > 0 and minute % 180 == 0: 
            # Use the 'all_device_names_flat' list which was correctly derived earlier
            for dev_name in all_device_names_flat:
                job_id_counter +=1; props_health = JOB_PROPERTIES["PERIODIC_HEALTH_CHECK"]
                jobs_list.append({"id":f"job_{job_id_counter}", "job_type":"PERIODIC_HEALTH_CHECK", "timestamp":minute, "target_device_name":dev_name, "work_units_required":_get_random_work_units("PERIODIC_HEALTH_CHECK"), "iot_app_reward":props_health["reward_base"], "penalty_for_failure":props_health["penalty"], "parameters":{}, "deadline_time":_get_job_deadline(minute, "PERIODIC_HEALTH_CHECK")})

    jobs_list.sort(key=lambda j: j["timestamp"])
    # As per main.py's expectation for control_case if it only unpacks one value:
    return jobs_list 
    # If main.py for control_case needs the device_configs_map, it should call get_device_names itself.
    # Or this function's signature and main.py's call should be:
    # return jobs_list, device_name_map_data # To match high_load_scenario structure


def generate_high_load_scenario(
    duration_minutes: int = DEFAULT_DURATION_MINUTES,
    num_zones: int = DEFAULT_NUM_ZONES,
    devices_per_zone_config: Optional[Dict[str, int]] = None,
    num_central_servers: int = DEFAULT_NUM_CENTRAL_SERVERS
) -> Dict[str, Any]:
    if devices_per_zone_config is None:
        devices_per_zone_config = DEFAULT_DEVICES_PER_ZONE 

    random.seed(FIXED_RANDOM_SEED + 1) 
    
    device_name_map_data = get_device_names(num_zones, devices_per_zone_config, num_central_servers)
    actual_device_configs_list = device_name_map_data["config_details"]["device_list_for_instantiation_flat"]
    all_device_names_flat = [d_cfg['name'] for d_cfg in actual_device_configs_list]
    
    jobs_list: List[Dict[str, Any]] = []
    job_id_counter = 0
    
    zone_states: Dict[str, Dict[str, Any]] = {}
    for i in range(1, num_zones + 1):
        zone_name = f"Zone{i}"
        zone_hvacs = device_name_map_data["zones"].get(zone_name, {}).get("HVAC", [])
        zone_states[zone_name] = {
            "current_temperature": round(random.uniform(*INITIAL_ZONE_TEMP_RANGE), 1),
            "current_occupancy": 0,
            "hvac_status": {hvac_name: "OFF" for hvac_name in zone_hvacs}
        }

    zone_ids_for_high_load = list(range(1, (num_zones // 2) + 1))
    high_load_hvacs = [f"Zone{z}_HVAC1" for z in zone_ids_for_high_load if f"Zone{z}_HVAC1" in device_name_map_data["zones"].get(f"Zone{z}", {}).get("HVAC",[])]
    high_load_zone_servers = [f"Zone{z}_ZoneServer1" for z in zone_ids_for_high_load if f"Zone{z}_ZoneServer1" in device_name_map_data["zones"].get(f"Zone{z}", {}).get("ZoneServer",[])]
    
    HIGH_LOAD_MULTIPLIER = 2.5 
    HIGH_LOAD_JOB_FREQUENCY_DIVISOR = 2 

    initial_relationships: List[Dict[str, Any]] = []
    for z_id in range(1, num_zones + 1):
        zone_hvac_list = device_name_map_data["zones"].get(f"Zone{z_id}", {}).get("HVAC", [])
        if len(zone_hvac_list) > 1:
            for i in range(len(zone_hvac_list)):
                primary_hvac = zone_hvac_list[i]
                backup_hvac = zone_hvac_list[(i + 1) % len(zone_hvac_list)] 
                initial_relationships.append({"device1_name": primary_hvac, "device2_name": backup_hvac, "type": "back-me", "policy_id": "hvac_backup_policy_v1"})
    
    for z_id in range(1, num_zones + 1):
        zone_server_list = device_name_map_data["zones"].get(f"Zone{z_id}", {}).get("ZoneServer", [])
        for i in range(len(zone_server_list)):
            for j in range(i + 1, len(zone_server_list)):
                server1 = zone_server_list[i]
                server2 = zone_server_list[j]
                initial_relationships.append({"device1_name": server1, "device2_name": server2, "type": "work-with-me", "policy_id": "server_collaboration_policy_v1"})
                initial_relationships.append({"device1_name": server2, "device2_name": server1, "type": "work-with-me", "policy_id": "server_collaboration_policy_v1"}) 

    for minute in range(duration_minutes):
        hour_of_day = (minute // 60) % 24

        for z_idx in range(1, num_zones + 1):
            zone_name = f"Zone{z_idx}"
            current_temp = zone_states[zone_name]["current_temperature"]
            hvacs_in_zone_list = device_name_map_data["zones"].get(zone_name,{}).get("HVAC", [])
            is_any_hvac_active = False
            for hvac_name in hvacs_in_zone_list:
                if zone_states[zone_name]["hvac_status"].get(hvac_name) == "HEATING":
                    current_temp += TEMP_CHANGE_PER_HVAC_CYCLE / 10; is_any_hvac_active = True
                    if current_temp >= DEFAULT_TARGET_TEMP_RANGE[1]: zone_states[zone_name]["hvac_status"][hvac_name] = "OFF"
                elif zone_states[zone_name]["hvac_status"].get(hvac_name) == "COOLING":
                    current_temp -= TEMP_CHANGE_PER_HVAC_CYCLE / 10; is_any_hvac_active = True
                    if current_temp <= DEFAULT_TARGET_TEMP_RANGE[0]: zone_states[zone_name]["hvac_status"][hvac_name] = "OFF"
            if not is_any_hvac_active:
                 if current_temp > 15: current_temp -= 0.01 
                 elif current_temp < 15: current_temp += 0.01
            zone_states[zone_name]["current_temperature"] = round(current_temp, 2)

        if minute % 10 == 0: 
            for zone_idx_loop in range(1, num_zones + 1):
                zone_name_loop = f"Zone{zone_idx_loop}"
                temp_sensors_in_zone = device_name_map_data["zones"].get(zone_name_loop, {}).get("TempSensor", [])
                hvacs_in_zone_list = device_name_map_data["zones"].get(zone_name_loop, {}).get("HVAC", [])
                current_zone_temp_reading = zone_states[zone_name_loop]["current_temperature"]
                
                for i, ts_name in enumerate(temp_sensors_in_zone):
                    job_id_counter += 1; props_sense = JOB_PROPERTIES["SENSE_TEMPERATURE"]
                    jobs_list.append({"id":f"hl_job_{job_id_counter}", "job_type":"SENSE_TEMPERATURE", "timestamp":minute, "target_device_name":ts_name, "target_zone":zone_name_loop, "work_units_required":_get_random_work_units("SENSE_TEMPERATURE") * 1.2, "iot_app_reward":props_sense["reward_base"] * 1.1, "penalty_for_failure":props_sense["penalty"], "parameters":{"sensed_temperature": round(current_zone_temp_reading,1), "sensor_index": i+1}, "deadline_time":_get_job_deadline(minute, "SENSE_TEMPERATURE")})
                    
                    if i < len(hvacs_in_zone_list): 
                        hvac_name = hvacs_in_zone_list[i]; hvac_action_params = {}; trigger_hvac = False
                        if current_zone_temp_reading < DEFAULT_TARGET_TEMP_RANGE[0] and zone_states[zone_name_loop]["hvac_status"].get(hvac_name) != "HEATING":
                            hvac_action_params = {"target_mode": "HEAT", "current_temp_reading": round(current_zone_temp_reading,1), "set_point": DEFAULT_TARGET_TEMP_RANGE[0]}; zone_states[zone_name_loop]["hvac_status"][hvac_name] = "HEATING"; trigger_hvac = True
                        elif current_zone_temp_reading > DEFAULT_TARGET_TEMP_RANGE[1] and zone_states[zone_name_loop]["hvac_status"].get(hvac_name) != "COOLING":
                            hvac_action_params = {"target_mode": "COOL", "current_temp_reading": round(current_zone_temp_reading,1), "set_point": DEFAULT_TARGET_TEMP_RANGE[1]}; zone_states[zone_name_loop]["hvac_status"][hvac_name] = "COOLING"; trigger_hvac = True
                        elif DEFAULT_TARGET_TEMP_RANGE[0] <= current_zone_temp_reading <= DEFAULT_TARGET_TEMP_RANGE[1] and zone_states[zone_name_loop]["hvac_status"].get(hvac_name) != "OFF":
                             hvac_action_params = {"target_mode": "OFF", "current_temp_reading": round(current_zone_temp_reading,1)}; zone_states[zone_name_loop]["hvac_status"][hvac_name] = "OFF"; trigger_hvac = True
                        
                        if trigger_hvac:
                            job_id_counter += 1; props_hvac = JOB_PROPERTIES["ADJUST_HVAC"]
                            current_hvac_work_units = _get_random_work_units("ADJUST_HVAC")
                            current_job_deadline = _get_job_deadline(minute+1, "ADJUST_HVAC")
                            current_reward = props_hvac["reward_base"]
                            task_details_hvac = {**hvac_action_params, "triggered_by_sensor": ts_name, "zone_id": zone_name_loop, "iot_app_reward": current_reward}

                            if hvac_name in high_load_hvacs:
                                if minute % 70 == (10 + zone_idx_loop * 5): 
                                    current_hvac_work_units = random.randint(140, 180) 
                                    current_job_deadline = minute + 1 + random.randint(3, 7)   
                                    task_details_hvac["iot_app_reward"] = 25.0
                                    task_details_hvac["criticality"] = "high"
                                else: 
                                    current_hvac_work_units = int(current_hvac_work_units * HIGH_LOAD_MULTIPLIER)
                                    task_details_hvac["iot_app_reward"] = 18.0
                            
                            jobs_list.append({"id":f"hl_job_{job_id_counter}", "job_type":"ADJUST_HVAC", "timestamp":minute + 1, "target_device_name":hvac_name, "target_zone":zone_name_loop, "work_units_required":int(current_hvac_work_units), "iot_app_reward":task_details_hvac["iot_app_reward"], "penalty_for_failure":props_hvac["penalty"], "parameters":task_details_hvac, "deadline_time":current_job_deadline})

        swipe_probability_hl = 0.0
        if 7 <= hour_of_day < 10: swipe_probability_hl = 0.6
        elif 12 <= hour_of_day < 14: swipe_probability_hl = 0.25
        elif 16 <= hour_of_day < 19: swipe_probability_hl = 0.5 
        elif 9 <= hour_of_day < 17 : swipe_probability_hl = 0.15
        
        if random.random() < swipe_probability_hl:
            if not direction: direction = random.choice(["IN","OUT"]) 
            target_zone_name_swipe = random.choice(list(device_name_map_data["zones"].keys()))
            access_points_in_zone = device_name_map_data["zones"].get(target_zone_name_swipe, {}).get("AccessPoint", [])
            if access_points_in_zone:
                ap_name = random.choice(access_points_in_zone); job_id_counter += 1; props_swipe = JOB_PROPERTIES["CARD_SWIPE"]
                jobs_list.append({"id":f"hl_job_{job_id_counter}", "job_type":"CARD_SWIPE", "timestamp":minute, "target_device_name":ap_name, "target_zone":target_zone_name_swipe, "parameters":{"direction": direction, "user_id": f"user_{random.randint(1, 500)}", "zone_id":target_zone_name_swipe}, "work_units_required":_get_random_work_units("CARD_SWIPE"), "iot_app_reward":props_swipe["reward_base"], "penalty_for_failure":props_swipe["penalty"], "deadline_time":_get_job_deadline(minute, "CARD_SWIPE")})
                if direction == "IN": zone_states[target_zone_name_swipe]["current_occupancy"] += 1
                elif direction == "OUT" and zone_states[target_zone_name_swipe]["current_occupancy"] > 0: zone_states[target_zone_name_swipe]["current_occupancy"] -= 1

        if 8 <= hour_of_day < 17 and random.random() < 0.0035: 
            target_zone_name_window = random.choice(list(device_name_map_data["zones"].keys())); 
            window_sensors_in_zone = device_name_map_data["zones"].get(target_zone_name_window, {}).get("WindowSensor", [])
            if window_sensors_in_zone:
                window_sensor_name = random.choice(window_sensors_in_zone); job_id_counter += 1; props_window = JOB_PROPERTIES["WINDOW_STATUS_CHANGE"]
                jobs_list.append({"id":f"hl_job_{job_id_counter}", "job_type":"WINDOW_STATUS_CHANGE", "timestamp":minute, "target_device_name":window_sensor_name, "target_zone":target_zone_name_window, "parameters":{"status": "OPENED", "window_id": window_sensor_name.split("_")[-1], "zone_id":target_zone_name_window}, "work_units_required":_get_random_work_units("WINDOW_STATUS_CHANGE"), "iot_app_reward":props_window["reward_base"], "penalty_for_failure":props_window["penalty"], "deadline_time":_get_job_deadline(minute, "WINDOW_STATUS_CHANGE")})
                zone_states[target_zone_name_window]["current_temperature"] = round(zone_states[target_zone_name_window]["current_temperature"] - TEMP_DROP_WINDOW_OPEN, 1)
        
        if minute > 0 and minute % (45 // HIGH_LOAD_JOB_FREQUENCY_DIVISOR) == 0:
            for z_idx_server in range(1, num_zones + 1):
                zone_name_server = f"Zone{z_idx_server}"
                zone_servers_in_zone_list = device_name_map_data["zones"].get(zone_name_server, {}).get("ZoneServer", [])
                if zone_servers_in_zone_list:
                    server_name = random.choice(zone_servers_in_zone_list); current_occupancy = zone_states[zone_name_server]["current_occupancy"]; 
                    props_zserver = JOB_PROPERTIES["ZONE_SERVER_TASK"]
                    
                    work_units_val = random.randint(*props_zserver["work_units_base"]) + int(current_occupancy * 2.5) 
                    job_deadline_val = _get_job_deadline(minute, "ZONE_SERVER_TASK")
                    reward_val = props_zserver["reward_base"] * 1.2 
                    task_subtype_val = random.choice(["ZONE_DATA_PROCESSING", "LOCAL_REQUEST_QUEUE"])
                    task_details_server = {"task_subtype": task_subtype_val, "current_occupancy_for_load": current_occupancy, "zone_id": zone_name_server, "iot_app_reward": reward_val}

                    if server_name in high_load_zone_servers:
                        if minute % 65 == (15 + z_idx_server * 5): 
                            work_units_val = random.randint(320, 400) 
                            task_subtype_val = random.choice(["CRITICAL_DATA_BURST_PROCESS", "URGENT_LARGE_QUEUE_FLUSH"])
                            job_deadline_val = minute + random.randint(8, 15) 
                            task_details_server["iot_app_reward"] = 30.0
                            task_details_server["criticality"] = "high"
                            task_details_server["task_subtype"] = task_subtype_val
                        else: 
                             work_units_val = int(work_units_val * HIGH_LOAD_MULTIPLIER)
                             task_details_server["iot_app_reward"] = 22.0
                    
                    job_id_counter += 1
                    jobs_list.append({"id":f"hl_job_{job_id_counter}", "job_type":"ZONE_SERVER_TASK", "timestamp":minute, "target_device_name":server_name, "target_zone":zone_name_server, "parameters":task_details_server, "work_units_required":int(work_units_val), "iot_app_reward":task_details_server["iot_app_reward"], "penalty_for_failure":props_zserver["penalty"], "deadline_time": job_deadline_val})
        
        if minute > 0 and minute % 90 == 0 and device_name_map_data["central"].get("CentralServer"): 
            central_servers_list = device_name_map_data["central"]["CentralServer"]
            if central_servers_list: 
                server_name = random.choice(central_servers_list); job_id_counter += 1; props_cserver = JOB_PROPERTIES["SERVER_COMM_TASK"]
                work_units_cserver = _get_random_work_units("SERVER_COMM_TASK") * 1.5 
                jobs_list.append({"id":f"hl_job_{job_id_counter}", "job_type":"SERVER_COMM_TASK", "timestamp":minute, "target_device_name":server_name, "parameters":{"task_subtype": random.choice(["GLOBAL_DATA_AGGREGATION_HIGH", "INTER_ZONE_SYNC_URGENT", "CRITICAL_MAIN_BACKUP"])}, "work_units_required":int(work_units_cserver), "iot_app_reward":props_cserver["reward_base"]*1.5, "penalty_for_failure":props_cserver["penalty"], "deadline_time":_get_job_deadline(minute, "SERVER_COMM_TASK")})
        
        if minute > 0 and minute % 180 == 0: 
            for dev_name in all_device_names_flat: # Use the correctly derived flat list
                job_id_counter +=1; props_health = JOB_PROPERTIES["PERIODIC_HEALTH_CHECK"]
                jobs_list.append({"id":f"hl_job_{job_id_counter}", "job_type":"PERIODIC_HEALTH_CHECK", "timestamp":minute, "target_device_name":dev_name, "work_units_required":_get_random_work_units("PERIODIC_HEALTH_CHECK"), "iot_app_reward":props_health["reward_base"], "penalty_for_failure":props_health["penalty"], "parameters":{}, "deadline_time":_get_job_deadline(minute, "PERIODIC_HEALTH_CHECK")})

    jobs_list.sort(key=lambda j: j["timestamp"])
    
    return {
        "scenario_name": f"High Load Scenario ({num_zones}z, {duration_minutes}m)",
        "duration_minutes": duration_minutes,
        "device_configs_for_instantiation": device_name_map_data, 
        "jobs": jobs_list, 
        "initial_relationships": initial_relationships
    }


# Helper function to save scenario to a file (optional)
def save_scenario(scenario_data: Dict[str, Any], filename: str):
    """Saves the generated scenario data to a JSON file."""
    output_dir = "scripts" 
    import os
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, filename)
    with open(filepath, 'w') as f:
        json.dump(scenario_data, f, indent=2)
    print(f"Saved scenario to {filepath}")


if __name__ == '__main__':
    devices_per_zone_example = { "TempSensor": 2, "HVAC": 1, "ZoneServer": 2, "AccessPoint":1, "WindowSensor":1}
    
    high_load_data = generate_high_load_scenario(
        duration_minutes=60, 
        num_zones=2, 
        devices_per_zone_config=devices_per_zone_example,
        num_central_servers=1
    )
    save_scenario(high_load_data, "high_load_scenario_example.json")
    print(f"Generated and saved high_load_scenario_example.json with {len(high_load_data['jobs'])} jobs.")

    # For control scenario, main.py expects generate_simple_control_scenario to return only jobs list.
    # main.py then calls get_device_names separately.
    control_jobs_list = generate_simple_control_scenario(
        duration_minutes=60, 
        num_zones=2,
        devices_per_zone_config=devices_per_zone_example,
        num_central_servers=1
    )
    # To save it in a similar structure as high_load for example purposes:
    control_device_name_map = get_device_names(2, devices_per_zone_example, 1)
    control_scenario_data_example = {
        "scenario_name": "Control Scenario Example (2 zones, 60 min)",
        "duration_minutes": 60,
        "device_configs_for_instantiation": control_device_name_map,
        "jobs": control_jobs_list,
        "initial_relationships": [] 
    }
    save_scenario(control_scenario_data_example, "control_scenario_example.json")
    print(f"Generated and saved control_scenario_example.json with {len(control_scenario_data_example['jobs'])} jobs.")
