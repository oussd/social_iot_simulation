# src/run_scenario_simulation.py

import json
import random 
import re 
from typing import List, Dict, Any, Tuple, Callable

# Corrected imports:
from .devices import (
    Device, SensingDevice, ActuatingDevice, 
    CommunicatingDevice, CompositeDevice
)
from .simulations.scenario_generator import (
    get_device_names, 
    DEFAULT_DEVICES_PER_ZONE, 
    DEFAULT_NUM_ZONES,
    DEFAULT_NUM_CENTRAL_SERVERS,
    DEFAULT_DURATION_MINUTES, 
    INITIAL_ZONE_TEMP_RANGE, 
    TEMP_DROP_WINDOW_OPEN,
    TEMP_CHANGE_PER_HVAC_CYCLE,
    DEFAULT_TARGET_TEMP_RANGE
)
from .utils.logger import SimulationLogger 

# --- Constants for Simulation Execution ---
SIM_MAX_LOAD_DEFAULT = 100 
SIM_BEHAVIOR_PROFILE_DEFAULT = "normal"


def load_full_scenario(script_filepath: str) -> Dict[str, Any]: 
    """Loads the full scenario dictionary from a JSON file."""
    try:
        with open(script_filepath, 'r') as f:
            scenario_data = json.load(f)
        if not isinstance(scenario_data, dict) or "jobs" not in scenario_data or \
           "device_configs_for_instantiation" not in scenario_data:
            raise ValueError("Script file should contain a scenario dictionary with 'jobs' and 'device_configs_for_instantiation' keys.")
        return scenario_data
    except FileNotFoundError:
        print(f"ERROR: Script file not found at {script_filepath}")
        raise
    except json.JSONDecodeError:
        print(f"ERROR: Could not decode JSON from script file {script_filepath}")
        raise

def _initialize_simulation_environment(
    scenario_data: Dict[str, Any], 
    sim_config_fallback: Dict[str, Any], 
    framework_variant: str,
    logger_instance: SimulationLogger,
    current_minute_provider: Callable[[], int]
) -> Tuple[Dict[str, Device], Dict[str, Any]]:
    """
    Initializes devices and the live environment state for the simulation run
    using the comprehensive scenario_data.
    """
    devices_map: Dict[str, Device] = {}
    
    device_configs_map = scenario_data.get("device_configs_for_instantiation")
    if not device_configs_map or not isinstance(device_configs_map.get("config_details"), dict):
        logger_instance.log_warning("InitEnv", "device_configs_for_instantiation missing or malformed in scenario data. Using fallback sim_config_from_main.")
        num_zones = sim_config_fallback.get("num_zones", DEFAULT_NUM_ZONES)
        devices_per_zone_cfg = sim_config_fallback.get("devices_per_zone_config", DEFAULT_DEVICES_PER_ZONE)
        num_central_servers = sim_config_fallback.get("num_central_servers", DEFAULT_NUM_CENTRAL_SERVERS)
        expected_device_names_map = get_device_names(num_zones, devices_per_zone_cfg, num_central_servers)
    else:
        sim_config_details = device_configs_map["config_details"]
        num_zones = sim_config_details["num_zones"]
        expected_device_names_map = device_configs_map 

    
    all_expected_device_names = []
    if "zones" in expected_device_names_map:
        for zone_name, zone_dev_types in expected_device_names_map["zones"].items():
            for dev_type, dev_list in zone_dev_types.items():
                all_expected_device_names.extend(dev_list)
    if "central" in expected_device_names_map and expected_device_names_map["central"].get("CentralServer"):
        all_expected_device_names.extend(expected_device_names_map["central"]["CentralServer"])
    
    for device_name in all_expected_device_names:
        device_type_from_name = ""
        if device_name.startswith("Zone"): 
            parts = device_name.split('_', 1) 
            if len(parts) == 2:
                type_part_with_num = parts[1] 
                match = re.match(r"([a-zA-Z_]+)", type_part_with_num) 
                if match:
                    device_type_from_name = match.group(1)
        elif device_name.startswith("CentralServer"): 
            match = re.match(r"([a-zA-Z_]+)", device_name) 
            if match:
                device_type_from_name = match.group(1) 
        
        device_instance = None
        
        if "TempSensor" == device_type_from_name:
            device_instance = SensingDevice(device_id=device_name, name=device_name, sensor_type="temperature", framework_variant=framework_variant, logger_instance=logger_instance, current_minute_provider=current_minute_provider, max_load=SIM_MAX_LOAD_DEFAULT, behavior_profile=SIM_BEHAVIOR_PROFILE_DEFAULT)
        elif "HVAC" == device_type_from_name:
            device_instance = ActuatingDevice(device_id=device_name, name=device_name, actuator_type="hvac_control", framework_variant=framework_variant, logger_instance=logger_instance, current_minute_provider=current_minute_provider, max_load=SIM_MAX_LOAD_DEFAULT, behavior_profile=SIM_BEHAVIOR_PROFILE_DEFAULT)
        elif "AccessPoint" == device_type_from_name:
            device_instance = SensingDevice(device_id=device_name, name=device_name, sensor_type="card_swipe", framework_variant=framework_variant, logger_instance=logger_instance, current_minute_provider=current_minute_provider, max_load=SIM_MAX_LOAD_DEFAULT, behavior_profile=SIM_BEHAVIOR_PROFILE_DEFAULT)
        elif "WindowSensor" == device_type_from_name: 
            device_instance = SensingDevice(device_id=device_name, name=device_name, sensor_type="window_contact", framework_variant=framework_variant, logger_instance=logger_instance, current_minute_provider=current_minute_provider, max_load=SIM_MAX_LOAD_DEFAULT, behavior_profile=SIM_BEHAVIOR_PROFILE_DEFAULT)
        elif "ZoneServer" == device_type_from_name or "CentralServer" == device_type_from_name:
            protocol = "Ethernet" if "CentralServer" == device_type_from_name else "LocalBus"
            server_max_load = SIM_MAX_LOAD_DEFAULT * 3 
            device_instance = CommunicatingDevice(device_id=device_name, name=device_name, protocol=protocol, framework_variant=framework_variant, logger_instance=logger_instance, current_minute_provider=current_minute_provider, max_load=server_max_load, behavior_profile=SIM_BEHAVIOR_PROFILE_DEFAULT, is_server_type=True)
        
        if device_instance:
            devices_map[device_name] = device_instance
            logger_instance.log_info("InitEnv", f"Instantiated device: {device_name} of type {device_instance.__class__.__name__} for framework {framework_variant}")
        else:
            logger_instance.log_warning("InitEnv", f"Could not determine type or instantiate device for name: {device_name} (derived type: '{device_type_from_name}')")

    initial_relationships = scenario_data.get("initial_relationships", [])
    logger_instance.log_info("InitEnv", f"Processing {len(initial_relationships)} initial relationships.")
    for rel_data in initial_relationships:
        dev1_name = rel_data.get('device1_name')
        dev2_name = rel_data.get('device2_name')
        rel_type = rel_data.get('type')
        policy_identifier = rel_data.get('policy_id') 

        device1 = devices_map.get(dev1_name)
        device2 = devices_map.get(dev2_name)

        if device1 and device2 and rel_type:
            # Assuming Device.add_relationship expects 'policy' as a keyword argument
            # based on the uploaded device.py (ID: uploaded:device.py)
            device1.add_relationship(device2, rel_type, policy=policy_identifier)
            logger_instance.log_info("InitEnv", f"Added relationship: {dev1_name} --{rel_type}--> {dev2_name} (Policy/ID: {policy_identifier or 'None'})")
        else:
            logger_instance.log_warning("InitEnv", f"Could not establish relationship due to missing devices or type: {rel_data}")

    live_zone_states: Dict[str, Dict[str, Any]] = {}
    hvac_map_for_init_zones = expected_device_names_map.get("zones", {})
    for i in range(num_zones):
        zone_name = f"Zone{i+1}"
        hvacs_in_zone_list = hvac_map_for_init_zones.get(zone_name, {}).get("HVAC", [])
        live_zone_states[zone_name] = {
            "current_temperature": round(random.uniform(*INITIAL_ZONE_TEMP_RANGE), 1),
            "current_occupancy": 0,
            "hvac_status": {hvac_name: "OFF" for hvac_name in hvacs_in_zone_list}
        }
    logger_instance.log_info("InitEnv", f"Initialized live zone states: {live_zone_states}")
    
    return devices_map, live_zone_states


def run_simulation(
    script_filepath: str, 
    sim_config_from_main: Dict[str, Any], 
    framework_variant: str,
    logger_instance: SimulationLogger 
) -> Dict[str, Any]:
    logger_instance.log_info("SimRunner", f"Starting simulation run. Framework: {framework_variant}, Script: {script_filepath}")
    
    try:
        scenario_data = load_full_scenario(script_filepath)
        loaded_jobs = scenario_data.get("jobs", [])
        device_init_config = scenario_data.get("device_configs_for_instantiation", {}).get("config_details", sim_config_from_main)
    except Exception as e:
        logger_instance.log_error("SimRunner", f"Failed to load scenario data: {str(e)}") 
        return {"error": f"Failed to load scenario data: {str(e)}"}
        
    if not loaded_jobs:
        logger_instance.log_error("SimRunner", "No jobs found in scenario data. Aborting simulation.")
        return {"error": "No jobs found in scenario data"}

    duration_minutes = scenario_data.get("duration_minutes", 
                                       sim_config_from_main.get("duration_minutes", DEFAULT_DURATION_MINUTES))
    
    _current_sim_minute = 0
    def get_current_sim_minute():
        return _current_sim_minute

    try:
        devices, live_zone_states = _initialize_simulation_environment(
            scenario_data, 
            device_init_config, 
            framework_variant, 
            logger_instance, 
            get_current_sim_minute
        )
    except Exception as e: 
        logger_instance.log_error("SimRunner", f"Failed to initialize simulation environment: {str(e)}") 
        return {"error": f"Failed to initialize simulation environment: {str(e)}"}

    if not devices: 
        logger_instance.log_error("SimRunner", "Device instantiation failed or key devices are missing. Aborting simulation.")
        if not any("ZoneServer" in name or "CentralServer" in name for name in devices.keys()): 
            logger_instance.log_error("SimRunner", "Server devices (ZoneServer/CentralServer) were not instantiated.")
        return {"error": "Device instantiation failed or key devices are missing."}

    metrics = {
        "total_jobs_in_script": len(loaded_jobs), "jobs_processed": 0, "jobs_succeeded": 0,
        "jobs_failed": 0, "jobs_deadline_met": 0, "jobs_deadline_missed": 0,
        "total_rewards_achieved_by_devices": 0.0, "total_penalties_to_devices": 0.0,
        "unresponsive_device_rejections":0, "faulty_device_actions_failed":0,
        "misuse_incidents_detected":0, "selfish_rejections":0,
        "successful_negotiations":0, "failed_negotiations":0,
        "back_me_invocations_successful":0, "back_me_invocations_failed":0,
        "sim_duration_minutes": duration_minutes, "framework_variant": framework_variant,
    }
    
    for device_obj in devices.values(): 
        if hasattr(device_obj, 'sim_metrics_ref'): 
            device_obj.sim_metrics_ref = metrics 

    job_idx = 0 
    for minute_step in range(duration_minutes):
        _current_sim_minute = minute_step
        
        if _current_sim_minute % (max(1, duration_minutes // 10 if duration_minutes >=10 else 1)) == 0 : 
             logger_instance.log_debug("SimRunner", f"--- Minute {_current_sim_minute}/{duration_minutes} ({(minute_step/duration_minutes)*100:.0f}%) ---")

        for zone_name, state in live_zone_states.items():
            if not any(s != "OFF" for s in state["hvac_status"].values()):
                if state["current_temperature"] > 15.0 :
                    state["current_temperature"] = round(max(10.0, state["current_temperature"] - 0.01), 2)
                elif state["current_temperature"] < 15.0 :
                    state["current_temperature"] = round(min(30.0, state["current_temperature"] + 0.01), 2)
            for hvac_name, status in list(state["hvac_status"].items()): 
                if status == "HEATING":
                    new_temp = round(min(DEFAULT_TARGET_TEMP_RANGE[1] + 2, state["current_temperature"] + TEMP_CHANGE_PER_HVAC_CYCLE / 5.0), 2)
                    state["current_temperature"] = new_temp
                    if new_temp >= DEFAULT_TARGET_TEMP_RANGE[1]: 
                        state["hvac_status"][hvac_name] = "OFF"
                        logger_instance.log_event("EnvUpdate", f"HVAC {hvac_name} in {zone_name} turned OFF, reached target heating temp ({new_temp}°C).", context_override="Environment")
                elif status == "COOLING":
                    new_temp = round(max(DEFAULT_TARGET_TEMP_RANGE[0] - 2, state["current_temperature"] - TEMP_CHANGE_PER_HVAC_CYCLE / 5.0), 2)
                    state["current_temperature"] = new_temp
                    if new_temp <= DEFAULT_TARGET_TEMP_RANGE[0]: 
                        state["hvac_status"][hvac_name] = "OFF"
                        logger_instance.log_event("EnvUpdate", f"HVAC {hvac_name} in {zone_name} turned OFF, reached target cooling temp ({new_temp}°C).", context_override="Environment")
        
        for device_obj in devices.values(): 
            if hasattr(device_obj, 'reduce_load'):
                 device_obj.reduce_load()

        while job_idx < len(loaded_jobs) and loaded_jobs[job_idx]["timestamp"] == _current_sim_minute:
            current_job_dict = loaded_jobs[job_idx]
            job_idx += 1
            metrics["jobs_processed"] += 1
            target_device_name = current_job_dict["target_device_name"]
            target_device = devices.get(target_device_name)

            if not target_device:
                logger_instance.log_warning("SimRunner", f"Job '{current_job_dict['id']}' targets unknown device '{target_device_name}'. Skipping.")
                metrics["jobs_failed"] += 1
                continue
            
            logger_instance.log_info("SimRunner", f"Dispatching job '{current_job_dict['id']}' ({current_job_dict['job_type']}) to {target_device_name}")
            job_params = current_job_dict.get("parameters", {}).copy() 
            if current_job_dict["job_type"] == "SENSE_TEMPERATURE":
                target_zone = current_job_dict.get("target_zone")
                if target_zone and target_zone in live_zone_states: job_params["sensed_temperature_live"] = live_zone_states[target_zone]["current_temperature"]
                else: job_params["sensed_temperature_live"] = job_params.get("sensed_temperature") 

            if hasattr(target_device, 'current_job_id'): target_device.current_job_id = current_job_dict['id']
            outcome = target_device.handle_request(from_device=None, task_type=current_job_dict["job_type"],load_requested=int(current_job_dict.get("work_units_required", 1)),details=job_params)
            if hasattr(target_device, 'current_job_id'): target_device.current_job_id = None 

            current_job_dict["status"] = "COMPLETED_SUCCESS" if outcome.get("success") else "COMPLETED_FAILURE"
            current_job_dict["completion_time"] = _current_sim_minute 

            if outcome.get("success"):
                metrics["jobs_succeeded"] += 1
                if current_job_dict["completion_time"] <= current_job_dict.get("deadline_time", _current_sim_minute): metrics["jobs_deadline_met"] += 1
                else: metrics["jobs_deadline_missed"] += 1; current_job_dict["status"] = "COMPLETED_LATE"
            else:
                metrics["jobs_failed"] += 1; metrics["jobs_deadline_missed"] += 1 

            if current_job_dict["job_type"] == "CARD_SWIPE":
                direction = current_job_dict.get("parameters", {}).get("direction"); target_zone = current_job_dict.get("target_zone")
                if target_zone and target_zone in live_zone_states:
                    if direction == "IN": live_zone_states[target_zone]["current_occupancy"] += 1
                    elif direction == "OUT" and live_zone_states[target_zone]["current_occupancy"] > 0: live_zone_states[target_zone]["current_occupancy"] -= 1
                    logger_instance.log_event("EnvUpdate", f"Zone {target_zone} occupancy now {live_zone_states[target_zone]['current_occupancy']}", context_override="Environment")
            elif current_job_dict["job_type"] == "WINDOW_STATUS_CHANGE":
                status = current_job_dict.get("parameters", {}).get("status"); target_zone = current_job_dict.get("target_zone")
                if status == "OPENED" and target_zone and target_zone in live_zone_states:
                    old_temp = live_zone_states[target_zone]['current_temperature']; live_zone_states[target_zone]['current_temperature'] = round(old_temp - TEMP_DROP_WINDOW_OPEN, 1)
                    logger_instance.log_event("EnvUpdate", f"Window opened in {target_zone}. Temp dropped from {old_temp:.1f} to {live_zone_states[target_zone]['current_temperature']:.1f}°C", context_override="Environment")
            elif current_job_dict["job_type"] == "ADJUST_HVAC" and outcome.get("success"):
                target_mode = current_job_dict.get("parameters", {}).get("target_mode", "OFF").upper(); target_zone = current_job_dict.get("target_zone")
                if target_mode and target_zone and target_zone in live_zone_states:
                    if target_device_name in live_zone_states[target_zone]["hvac_status"]:
                        live_zone_states[target_zone]["hvac_status"][target_device_name] = target_mode 
                        logger_instance.log_event("EnvUpdate", f"HVAC {target_device_name} in {target_zone} set to {target_mode}", context_override="Environment")
                    else: logger_instance.log_warning("EnvUpdate", f"HVAC {target_device_name} not found in zone {target_zone} status for update.", context_override="Environment")

        if _current_sim_minute > 0 and _current_sim_minute % (max(1,duration_minutes // 4)) == 0: 
             for z_name, z_state in live_zone_states.items():
                 logger_instance.log_info("ZoneState", f"{z_name}: Temp={z_state['current_temperature']:.1f}°C, Occupancy={z_state['current_occupancy']}, HVACs={z_state['hvac_status']}")

    total_income = 0; total_penalties_devices_received = 0
    for device_obj in devices.values(): 
        if hasattr(device_obj, 'total_income_earned'): total_income += device_obj.total_income_earned 
        if hasattr(device_obj, 'total_penalties_received'): total_penalties_devices_received += device_obj.total_penalties_received
    metrics["total_rewards_achieved_by_devices"] = round(total_income, 2)
    metrics["total_penalties_to_devices"] = round(total_penalties_devices_received, 2)
    
    logger_instance.log_info("SimRunner", f"Simulation run completed for framework {framework_variant}. Final Metrics: {json.dumps(metrics, indent=2)}")
    return metrics
