# src/simulations/scenario_generator.py

import random
import re 
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field 
import datetime 

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
    base_reward: int = 10
    penalty_for_failure: int = 5
    parameters: Dict[str, Any] = field(default_factory=dict)
    sub_task_results: List[Dict] = field(default_factory=list)

    def __post_init__(self):
        if not self.creation_time:
            self.creation_time = self.timestamp
        if not self.deadline_time: 
            job_props = JOB_PROPERTIES.get(self.job_type, {})
            base_processing_time = job_props.get("processing_time", 5)
            # Ensure estimated_duration is at least 1 to avoid deadline_time <= timestamp
            estimated_duration = max(1, base_processing_time + random.randint(1, int(base_processing_time * 0.5) + 1))
            self.deadline_time = self.timestamp + estimated_duration


# --- Default Configuration ---
DEFAULT_NUM_ZONES = 4 
DEFAULT_DEVICES_PER_ZONE = {
    "TempSensor": 3,   
    "HVAC": 3,         
    "AccessPoint": 2,  
    "WindowSensor": 2, 
    "ZoneServer": 4    
}
DEFAULT_NUM_CENTRAL_SERVERS = 1 
DEFAULT_DURATION_MINUTES = 24 * 60 

FIXED_RANDOM_SEED = 42

DEFAULT_TARGET_TEMP_RANGE = (20.0, 25.0) 
TEMP_CHANGE_PER_HVAC_CYCLE = 0.5 
TEMP_DROP_WINDOW_OPEN = 3.0 
INITIAL_ZONE_TEMP_RANGE = (18.0, 28.0) 

def get_device_names(num_zones: int, devices_per_zone_config: Dict[str, int], num_central_servers: int) -> Dict[str, Any]:
    device_map: Dict[str, Any] = {
        "zones": {}, 
        "central": {"CentralServer": []}, 
        "config_details": {
            "devices_per_zone_config": devices_per_zone_config.copy(), 
            "num_zones": num_zones,
            "num_central_servers": num_central_servers
        }
    }
    for i in range(num_zones):
        zone_name = f"Zone{i+1}"
        device_map["zones"][zone_name] = {}
        for device_type, count in devices_per_zone_config.items():
            device_map["zones"][zone_name][device_type] = [
                f"{zone_name}_{device_type}{j+1}" for j in range(count)
            ]
    for i in range(num_central_servers):
        device_map["central"]["CentralServer"].append(f"CentralServer{i+1}")
    return device_map

JOB_PROPERTIES = {
    "SENSE_TEMPERATURE": {"work_units": 0.5, "reward": 5, "penalty": 2, "processing_time": 1}, 
    "CARD_SWIPE": {"work_units": 0.2, "reward": 2, "penalty": 1, "processing_time": 1},
    "WINDOW_STATUS_CHANGE": {"work_units": 0.1, "reward": 1, "penalty": 0, "processing_time": 1}, 
    "ADJUST_HVAC": {"work_units": 1.5, "reward": 8, "penalty": 5, "processing_time": 3}, 
    "SERVER_COMM_TASK": {"work_units": 3, "reward": 10, "penalty": 3, "processing_time": 10}, 
    "ZONE_SERVER_TASK": {"work_units": 1.0, "reward": 9, "penalty": 3, "processing_time": 5}, 
    "PERIODIC_HEALTH_CHECK": {"work_units": 0.2, "reward": 1, "penalty": 0, "processing_time": 1}
}

def generate_simple_control_scenario( 
    duration_minutes: int = DEFAULT_DURATION_MINUTES,
    num_zones: int = DEFAULT_NUM_ZONES,
    devices_per_zone_config: Optional[Dict[str, int]] = None, 
    num_central_servers: int = DEFAULT_NUM_CENTRAL_SERVERS
) -> List[Dict]: 
    
    if devices_per_zone_config is None:
        devices_per_zone_config = DEFAULT_DEVICES_PER_ZONE

    random.seed(FIXED_RANDOM_SEED)
    jobs: List[ScenarioJob] = []
    job_id_counter = 0

    device_name_map = get_device_names(num_zones, devices_per_zone_config, num_central_servers)
    
    zone_states: Dict[str, Dict[str, Any]] = {}
    for i in range(num_zones):
        zone_name = f"Zone{i+1}"
        zone_states[zone_name] = {
            "current_temperature": round(random.uniform(*INITIAL_ZONE_TEMP_RANGE), 1),
            "current_occupancy": 0,
            "hvac_status": {hvac_name: "OFF" for hvac_name in device_name_map["zones"].get(zone_name, {}).get("HVAC", [])} 
        }

    for minute in range(duration_minutes):
        hour_of_day = (minute // 60) % 24

        for zone_name in zone_states:
            current_temp = zone_states[zone_name]["current_temperature"]
            hvacs_in_zone = device_name_map["zones"].get(zone_name,{}).get("HVAC", []) 
            
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
            for zone_name, zone_devices_by_type in device_name_map["zones"].items():
                temp_sensors = zone_devices_by_type.get("TempSensor", [])
                hvacs = zone_devices_by_type.get("HVAC", [])
                current_zone_temp = zone_states[zone_name]["current_temperature"]
                
                for i in range(len(temp_sensors)):
                    ts_name = temp_sensors[i]
                    job_id_counter += 1; props_sense = JOB_PROPERTIES["SENSE_TEMPERATURE"]
                    jobs.append(ScenarioJob(id=f"job_{job_id_counter}",job_type="SENSE_TEMPERATURE",timestamp=minute,target_device_name=ts_name,target_zone=zone_name,work_units_required=props_sense["work_units"],base_reward=props_sense["reward"],penalty_for_failure=props_sense["penalty"],parameters={"sensed_temperature": current_zone_temp, "sensor_index": i+1}))
                    
                    if i < len(hvacs): 
                        hvac_name = hvacs[i]; hvac_action_params = {}; trigger_hvac = False
                        if current_zone_temp < DEFAULT_TARGET_TEMP_RANGE[0] and zone_states[zone_name]["hvac_status"].get(hvac_name) != "HEATING":
                            hvac_action_params = {"target_mode": "HEAT", "current_temp": current_zone_temp, "set_point": DEFAULT_TARGET_TEMP_RANGE[0]}; zone_states[zone_name]["hvac_status"][hvac_name] = "HEATING"; trigger_hvac = True
                        elif current_zone_temp > DEFAULT_TARGET_TEMP_RANGE[1] and zone_states[zone_name]["hvac_status"].get(hvac_name) != "COOLING":
                            hvac_action_params = {"target_mode": "COOL", "current_temp": current_zone_temp, "set_point": DEFAULT_TARGET_TEMP_RANGE[1]}; zone_states[zone_name]["hvac_status"][hvac_name] = "COOLING"; trigger_hvac = True
                        elif DEFAULT_TARGET_TEMP_RANGE[0] <= current_zone_temp <= DEFAULT_TARGET_TEMP_RANGE[1] and \
                             zone_states[zone_name]["hvac_status"].get(hvac_name) != "OFF":
                            hvac_action_params = {"target_mode": "OFF", "current_temp": current_zone_temp}; zone_states[zone_name]["hvac_status"][hvac_name] = "OFF"; trigger_hvac = True
                        if trigger_hvac:
                            job_id_counter += 1; props_hvac = JOB_PROPERTIES["ADJUST_HVAC"]
                            jobs.append(ScenarioJob(id=f"job_{job_id_counter}",job_type="ADJUST_HVAC",timestamp=minute + 1,target_device_name=hvac_name,target_zone=zone_name,work_units_required=props_hvac["work_units"],base_reward=props_hvac["reward"],penalty_for_failure=props_hvac["penalty"],parameters={**hvac_action_params, "triggered_by_sensor": ts_name}))
        
        swipe_probability = 0.0; direction = None
        if 7 <= hour_of_day < 9: swipe_probability = 0.4; direction = "IN"
        elif 12 <= hour_of_day < 14: swipe_probability = 0.2; direction = random.choice(["IN", "OUT"])
        elif 17 <= hour_of_day < 19: swipe_probability = 0.35; direction = "OUT"
        elif 9 <= hour_of_day < 17 : swipe_probability = 0.08; direction = random.choice(["IN", "OUT"])
        if random.random() < swipe_probability and direction:
            target_zone_name = random.choice(list(device_name_map["zones"].keys()))
            access_points = device_name_map["zones"].get(target_zone_name, {}).get("AccessPoint", [])
            if access_points:
                ap_name = random.choice(access_points); job_id_counter += 1; props_swipe = JOB_PROPERTIES["CARD_SWIPE"]
                jobs.append(ScenarioJob(id=f"job_{job_id_counter}", job_type="CARD_SWIPE", timestamp=minute,target_device_name=ap_name, target_zone=target_zone_name,parameters={"direction": direction, "user_id": f"user_{random.randint(1, 500)}"},work_units_required=props_swipe["work_units"], base_reward=props_swipe["reward"],penalty_for_failure=props_swipe["penalty"]))
                if direction == "IN": zone_states[target_zone_name]["current_occupancy"] += 1
                elif direction == "OUT" and zone_states[target_zone_name]["current_occupancy"] > 0: zone_states[target_zone_name]["current_occupancy"] -= 1

        if 8 <= hour_of_day < 17 and random.random() < 0.0025: 
            target_zone_name = random.choice(list(device_name_map["zones"].keys())); window_sensors = device_name_map["zones"].get(target_zone_name, {}).get("WindowSensor", []); hvacs_in_zone = device_name_map["zones"].get(target_zone_name, {}).get("HVAC", [])
            if window_sensors:
                window_sensor_name = random.choice(window_sensors); job_id_counter += 1; props_window = JOB_PROPERTIES["WINDOW_STATUS_CHANGE"]
                jobs.append(ScenarioJob(id=f"job_{job_id_counter}", job_type="WINDOW_STATUS_CHANGE", timestamp=minute,target_device_name=window_sensor_name, target_zone=target_zone_name,parameters={"status": "OPENED", "window_id": window_sensor_name.split("_")[-1]},work_units_required=props_window["work_units"], base_reward=props_window["reward"],penalty_for_failure=props_window["penalty"]))
                zone_states[target_zone_name]["current_temperature"] = round(zone_states[target_zone_name]["current_temperature"] - TEMP_DROP_WINDOW_OPEN, 1)
                current_zone_temp_after_window = zone_states[target_zone_name]["current_temperature"]
                if hvacs_in_zone:
                    hvac_to_react = hvacs_in_zone[0] ; hvac_action_params = {}; trigger_hvac_window = False
                    if current_zone_temp_after_window < DEFAULT_TARGET_TEMP_RANGE[0] and zone_states[target_zone_name]["hvac_status"].get(hvac_to_react) != "HEATING":
                        hvac_action_params = {"target_mode": "HEAT", "current_temp": current_zone_temp_after_window, "set_point": DEFAULT_TARGET_TEMP_RANGE[0]}; zone_states[target_zone_name]["hvac_status"][hvac_to_react] = "HEATING"; trigger_hvac_window = True
                    if trigger_hvac_window:
                        job_id_counter += 1; props_hvac_react = JOB_PROPERTIES["ADJUST_HVAC"]
                        jobs.append(ScenarioJob(id=f"job_{job_id_counter}", job_type="ADJUST_HVAC", timestamp=minute + 1,target_device_name=hvac_to_react, target_zone=target_zone_name,parameters={**hvac_action_params, "reason": "window_opened_event"},work_units_required=props_hvac_react["work_units"], base_reward=props_hvac_react["reward"],penalty_for_failure=props_hvac_react["penalty"]))
        
        if minute % 45 == 0: 
            for zone_name, zone_devices_by_type in device_name_map["zones"].items():
                zone_servers = zone_devices_by_type.get("ZoneServer", [])
                if zone_servers:
                    server_name = random.choice(zone_servers); current_occupancy = zone_states[zone_name]["current_occupancy"]; base_work_units = JOB_PROPERTIES["ZONE_SERVER_TASK"]["work_units"]; dynamic_work_units = round(base_work_units + min(5.0, current_occupancy * 0.1), 2) 
                    job_id_counter += 1; props_zserver = JOB_PROPERTIES["ZONE_SERVER_TASK"]
                    jobs.append(ScenarioJob(id=f"job_{job_id_counter}", job_type="ZONE_SERVER_TASK", timestamp=minute,target_device_name=server_name, target_zone=zone_name,parameters={"task_subtype": random.choice(["ZONE_DATA_CACHE", "LOCAL_AUTH_SYNC"]), "current_occupancy_for_load": current_occupancy},work_units_required=dynamic_work_units, base_reward=props_zserver["reward"],penalty_for_failure=props_zserver["penalty"]))

        if minute % 90 == 0 and device_name_map["central"].get("CentralServer"): 
            central_servers_list = device_name_map["central"]["CentralServer"]
            if central_servers_list: 
                server_name = random.choice(central_servers_list); job_id_counter += 1; props_cserver = JOB_PROPERTIES["SERVER_COMM_TASK"]
                jobs.append(ScenarioJob(id=f"job_{job_id_counter}", job_type="SERVER_COMM_TASK", timestamp=minute,target_device_name=server_name,parameters={"task_subtype": random.choice(["GLOBAL_DATA_AGGREGATION", "INTER_ZONE_SYNC", "MAIN_BACKUP"])},work_units_required=props_cserver["work_units"], base_reward=props_cserver["reward"],penalty_for_failure=props_cserver["penalty"]))
        
        if minute % 180 == 0: 
            all_device_names_in_scenario = []
            for _zone_name, zone_dev_types in device_name_map["zones"].items():
                for _dev_type, dev_type_list in zone_dev_types.items(): all_device_names_in_scenario.extend(dev_type_list)
            if device_name_map["central"].get("CentralServer"): all_device_names_in_scenario.extend(device_name_map["central"]["CentralServer"])
            for dev_name in all_device_names_in_scenario:
                job_id_counter +=1; props_health = JOB_PROPERTIES["PERIODIC_HEALTH_CHECK"]
                jobs.append(ScenarioJob(id=f"job_{job_id_counter}", job_type="PERIODIC_HEALTH_CHECK", timestamp=minute,target_device_name=dev_name, work_units_required=props_health["work_units"],base_reward=props_health["reward"], penalty_for_failure=props_health["penalty"]))

    jobs.sort(key=lambda j: j.timestamp)
    return [j.__dict__ for j in jobs]


def generate_high_load_scenario(
    duration_minutes: int = DEFAULT_DURATION_MINUTES,
    num_zones: int = DEFAULT_NUM_ZONES,
    devices_per_zone_config: Optional[Dict[str, int]] = None,
    num_central_servers: int = DEFAULT_NUM_CENTRAL_SERVERS
) -> Dict[str, Any]:
    """
    Generates a scenario with high load conditions and initial relationships for delegation.
    """
    if devices_per_zone_config is None:
        devices_per_zone_config = DEFAULT_DEVICES_PER_ZONE 

    random.seed(FIXED_RANDOM_SEED + 1) 
    
    device_name_map = get_device_names(num_zones, devices_per_zone_config, num_central_servers) # Corrected: singular 'device_name_map'
    
    jobs: List[ScenarioJob] = []
    job_id_counter = 0
    
    zone_states: Dict[str, Dict[str, Any]] = {}
    for i in range(num_zones):
        zone_name = f"Zone{i+1}"
        zone_states[zone_name] = {
            "current_temperature": round(random.uniform(*INITIAL_ZONE_TEMP_RANGE), 1),
            "current_occupancy": 0,
            "hvac_status": {hvac_name: "OFF" for hvac_name in device_name_map["zones"].get(zone_name, {}).get("HVAC", [])}
        }

    high_load_hvacs = []
    high_load_zone_servers = []
    
    # Use the correctly named variable: device_name_map
    for zone_name, zone_devices in device_name_map["zones"].items(): # Corrected variable name
        if zone_devices.get("HVAC"):
            high_load_hvacs.append(zone_devices["HVAC"][0]) 
        if zone_devices.get("ZoneServer"):
            high_load_zone_servers.extend(zone_devices["ZoneServer"][:2]) 

    HIGH_LOAD_MULTIPLIER = 2.5 
    HIGH_LOAD_JOB_FREQUENCY_DIVISOR = 2 

    for minute in range(duration_minutes):
        hour_of_day = (minute // 60) % 24

        for zone_name in zone_states: 
            current_temp = zone_states[zone_name]["current_temperature"]
            hvacs_in_zone = device_name_map["zones"].get(zone_name,{}).get("HVAC", [])
            is_any_hvac_active = False
            for hvac_name in hvacs_in_zone:
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
            for zone_name, zone_devices_by_type in device_name_map["zones"].items(): # Corrected variable name
                temp_sensors = zone_devices_by_type.get("TempSensor", [])
                hvacs = zone_devices_by_type.get("HVAC", [])
                current_zone_temp = zone_states[zone_name]["current_temperature"]
                for i in range(len(temp_sensors)):
                    ts_name = temp_sensors[i]; job_id_counter += 1; props_sense = JOB_PROPERTIES["SENSE_TEMPERATURE"]
                    jobs.append(ScenarioJob(id=f"hl_job_{job_id_counter}",job_type="SENSE_TEMPERATURE",timestamp=minute,target_device_name=ts_name,target_zone=zone_name,work_units_required=props_sense["work_units"],base_reward=props_sense["reward"],penalty_for_failure=props_sense["penalty"],parameters={"sensed_temperature": current_zone_temp, "sensor_index": i+1}))
                    if i < len(hvacs):
                        hvac_name = hvacs[i]; hvac_action_params = {}; trigger_hvac = False
                        if current_zone_temp < DEFAULT_TARGET_TEMP_RANGE[0] and zone_states[zone_name]["hvac_status"].get(hvac_name) != "HEATING":
                            hvac_action_params = {"target_mode": "HEAT", "current_temp": current_zone_temp, "set_point": DEFAULT_TARGET_TEMP_RANGE[0]}; zone_states[zone_name]["hvac_status"][hvac_name] = "HEATING"; trigger_hvac = True
                        elif current_zone_temp > DEFAULT_TARGET_TEMP_RANGE[1] and zone_states[zone_name]["hvac_status"].get(hvac_name) != "COOLING":
                            hvac_action_params = {"target_mode": "COOL", "current_temp": current_zone_temp, "set_point": DEFAULT_TARGET_TEMP_RANGE[1]}; zone_states[zone_name]["hvac_status"][hvac_name] = "COOLING"; trigger_hvac = True
                        elif DEFAULT_TARGET_TEMP_RANGE[0] <= current_zone_temp <= DEFAULT_TARGET_TEMP_RANGE[1] and \
                             zone_states[zone_name]["hvac_status"].get(hvac_name) != "OFF":
                            hvac_action_params = {"target_mode": "OFF", "current_temp": current_zone_temp}; zone_states[zone_name]["hvac_status"][hvac_name] = "OFF"; trigger_hvac = True
                        if trigger_hvac:
                            job_id_counter += 1; props_hvac = JOB_PROPERTIES["ADJUST_HVAC"]
                            work_units = props_hvac["work_units"]
                            if hvac_name in high_load_hvacs: work_units = round(work_units * HIGH_LOAD_MULTIPLIER, 2)
                            jobs.append(ScenarioJob(id=f"hl_job_{job_id_counter}",job_type="ADJUST_HVAC",timestamp=minute + 1,target_device_name=hvac_name,target_zone=zone_name,work_units_required=work_units,base_reward=props_hvac["reward"],penalty_for_failure=props_hvac["penalty"],parameters={**hvac_action_params, "triggered_by_sensor": ts_name}))
        
        swipe_probability = 0.0; direction = None
        if 7 <= hour_of_day < 10: swipe_probability = 0.6; direction = "IN" 
        elif 12 <= hour_of_day < 14: swipe_probability = 0.25; direction = random.choice(["IN", "OUT"])
        elif 16 <= hour_of_day < 19: swipe_probability = 0.4; direction = "OUT" 
        elif 9 <= hour_of_day < 17 : swipe_probability = 0.15; 
        if random.random() < swipe_probability : 
            if not direction: direction = random.choice(["IN","OUT"]) 
            target_zone_name = random.choice(list(device_name_map["zones"].keys()))
            access_points = device_name_map["zones"].get(target_zone_name, {}).get("AccessPoint", [])
            if access_points:
                ap_name = random.choice(access_points); job_id_counter += 1; props_swipe = JOB_PROPERTIES["CARD_SWIPE"]
                jobs.append(ScenarioJob(id=f"hl_job_{job_id_counter}", job_type="CARD_SWIPE", timestamp=minute,target_device_name=ap_name, target_zone=target_zone_name,parameters={"direction": direction, "user_id": f"user_{random.randint(1, 500)}"},work_units_required=props_swipe["work_units"], base_reward=props_swipe["reward"],penalty_for_failure=props_swipe["penalty"]))
                if direction == "IN": zone_states[target_zone_name]["current_occupancy"] += 1
                elif direction == "OUT" and zone_states[target_zone_name]["current_occupancy"] > 0: zone_states[target_zone_name]["current_occupancy"] -= 1
        
        if 8 <= hour_of_day < 17 and random.random() < 0.0035: 
            target_zone_name = random.choice(list(device_name_map["zones"].keys())); window_sensors = device_name_map["zones"].get(target_zone_name, {}).get("WindowSensor", []); hvacs_in_zone = device_name_map["zones"].get(target_zone_name, {}).get("HVAC", [])
            if window_sensors:
                window_sensor_name = random.choice(window_sensors); job_id_counter += 1; props_window = JOB_PROPERTIES["WINDOW_STATUS_CHANGE"]
                jobs.append(ScenarioJob(id=f"hl_job_{job_id_counter}", job_type="WINDOW_STATUS_CHANGE", timestamp=minute,target_device_name=window_sensor_name, target_zone=target_zone_name,parameters={"status": "OPENED", "window_id": window_sensor_name.split("_")[-1]},work_units_required=props_window["work_units"], base_reward=props_window["reward"],penalty_for_failure=props_window["penalty"]))
                zone_states[target_zone_name]["current_temperature"] = round(zone_states[target_zone_name]["current_temperature"] - TEMP_DROP_WINDOW_OPEN, 1)
                current_zone_temp_after_window = zone_states[target_zone_name]["current_temperature"]
                if hvacs_in_zone:
                    hvac_to_react = hvacs_in_zone[0] ; hvac_action_params = {}; trigger_hvac_window = False
                    if current_zone_temp_after_window < DEFAULT_TARGET_TEMP_RANGE[0] and zone_states[target_zone_name]["hvac_status"].get(hvac_to_react) != "HEATING":
                        hvac_action_params = {"target_mode": "HEAT", "current_temp": current_zone_temp_after_window, "set_point": DEFAULT_TARGET_TEMP_RANGE[0]}; zone_states[target_zone_name]["hvac_status"][hvac_to_react] = "HEATING"; trigger_hvac_window = True
                    if trigger_hvac_window:
                        job_id_counter += 1; props_hvac_react = JOB_PROPERTIES["ADJUST_HVAC"]; work_units_hvac_window = props_hvac_react["work_units"]
                        if hvac_to_react in high_load_hvacs: work_units_hvac_window = round(work_units_hvac_window * HIGH_LOAD_MULTIPLIER, 2)
                        jobs.append(ScenarioJob(id=f"hl_job_{job_id_counter}", job_type="ADJUST_HVAC", timestamp=minute + 1,target_device_name=hvac_to_react, target_zone=target_zone_name,parameters={**hvac_action_params, "reason": "window_opened_event"},work_units_required=work_units_hvac_window, base_reward=props_hvac_react["reward"],penalty_for_failure=props_hvac_react["penalty"]))
        
        if minute % (45 // HIGH_LOAD_JOB_FREQUENCY_DIVISOR) == 0: 
            for zone_name, zone_devices_by_type in device_name_map["zones"].items(): # Corrected variable name
                zone_servers = zone_devices_by_type.get("ZoneServer", [])
                if zone_servers:
                    server_name = random.choice(zone_servers); current_occupancy = zone_states[zone_name]["current_occupancy"]; base_work_units = JOB_PROPERTIES["ZONE_SERVER_TASK"]["work_units"]; dynamic_work_units = round(base_work_units + min(5.0, current_occupancy * 0.15), 2) 
                    if server_name in high_load_zone_servers: dynamic_work_units = round(dynamic_work_units * HIGH_LOAD_MULTIPLIER, 2)
                    job_id_counter += 1; props_zserver = JOB_PROPERTIES["ZONE_SERVER_TASK"]
                    jobs.append(ScenarioJob(id=f"hl_job_{job_id_counter}", job_type="ZONE_SERVER_TASK", timestamp=minute,target_device_name=server_name, target_zone=zone_name,parameters={"task_subtype": random.choice(["ZONE_DATA_PROCESSING", "LOCAL_REQUEST_QUEUE"]), "current_occupancy_for_load": current_occupancy},work_units_required=dynamic_work_units, base_reward=props_zserver["reward"],penalty_for_failure=props_zserver["penalty"]))

        if minute % 90 == 0 and device_name_map["central"].get("CentralServer"): 
            central_servers_list = device_name_map["central"]["CentralServer"]
            if central_servers_list: 
                server_name = random.choice(central_servers_list); job_id_counter += 1; props_cserver = JOB_PROPERTIES["SERVER_COMM_TASK"]
                work_units_cserver = props_cserver["work_units"]
                if server_name in high_load_zone_servers: # Simplified check
                    work_units_cserver = round(work_units_cserver * HIGH_LOAD_MULTIPLIER * 0.8, 2) 
                jobs.append(ScenarioJob(id=f"hl_job_{job_id_counter}", job_type="SERVER_COMM_TASK", timestamp=minute,target_device_name=server_name,parameters={"task_subtype": random.choice(["GLOBAL_DATA_AGGREGATION", "INTER_ZONE_SYNC", "MAIN_BACKUP"])},work_units_required=work_units_cserver, base_reward=props_cserver["reward"],penalty_for_failure=props_cserver["penalty"]))
        
        if minute % 180 == 0: 
            all_device_names_in_scenario = []
            for _zone_name, zone_dev_types in device_name_map["zones"].items(): # Corrected variable name
                for _dev_type, dev_type_list in zone_dev_types.items(): all_device_names_in_scenario.extend(dev_type_list)
            if device_name_map["central"].get("CentralServer"): all_device_names_in_scenario.extend(device_name_map["central"]["CentralServer"])
            for dev_name in all_device_names_in_scenario:
                job_id_counter +=1; props_health = JOB_PROPERTIES["PERIODIC_HEALTH_CHECK"]
                jobs.append(ScenarioJob(id=f"hl_job_{job_id_counter}", job_type="PERIODIC_HEALTH_CHECK", timestamp=minute,target_device_name=dev_name, work_units_required=props_health["work_units"],base_reward=props_health["reward"], penalty_for_failure=props_health["penalty"]))

    jobs.sort(key=lambda j: j.timestamp)
    
    initial_relationships: List[Dict[str, Any]] = []
    for zone_name, zone_devices_by_type in device_name_map["zones"].items(): # Corrected variable name
        hvacs = zone_devices_by_type.get("HVAC", [])
        if len(hvacs) > 1: 
            for i in range(len(hvacs)):
                backup_hvac_index = (i + 1) % len(hvacs)
                initial_relationships.append({'device1_name': hvacs[i], 'device2_name': hvacs[backup_hvac_index], 'type': 'back-me', 'policy_id': 'hvac_backup_policy_v1'})
        
        zone_servers = zone_devices_by_type.get("ZoneServer", [])
        if len(zone_servers) > 1: 
            for i in range(len(zone_servers)):
                for j in range(i + 1, len(zone_servers)): 
                    initial_relationships.append({'device1_name': zone_servers[i], 'device2_name': zone_servers[j], 'type': 'work-with-me', 'policy_id': 'server_collaboration_policy_v1'})
                    initial_relationships.append({'device1_name': zone_servers[j], 'device2_name': zone_servers[i], 'type': 'work-with-me', 'policy_id': 'server_collaboration_policy_v1'}) 

    return {
        "scenario_name": f"High Load Scenario ({num_zones}z, {duration_minutes}m)",
        "duration_minutes": duration_minutes,
        "device_configs_for_instantiation": device_name_map, 
        "jobs": [j.__dict__ for j in jobs],
        "initial_relationships": initial_relationships
    }
