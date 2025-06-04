# src/run_scenario_simulation.py

import json
import random 
import re 
import time 
from typing import List, Dict, Any, Tuple, Callable, Optional

# Corrected imports:
from .devices import (
    Device, SensingDevice, ActuatingDevice, 
    CommunicatingDevice, CompositeDevice
)
from .simulations.scenario_generator import (
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
    framework_variant: str,
    logger_instance: SimulationLogger,
    current_minute_provider: Callable[[], int]
) -> Tuple[Dict[str, Device], Dict[str, Any]]:
    """
    Initializes devices and the live environment state for the simulation run
    using the comprehensive scenario_data.
    """
    devices_map: Dict[str, Device] = {}
    
    device_configs_container = scenario_data.get("device_configs_for_instantiation")
    
    # --- CORRECTED CHECKS AND ACCESS TO DEVICE LIST ---
    if not isinstance(device_configs_container, dict) or \
       not isinstance(device_configs_container.get("config_details"), dict) or \
       not isinstance(device_configs_container.get("config_details", {}).get("device_list_for_instantiation_flat"), list):
        logger_instance.log_error("InitEnv", "device_configs_for_instantiation missing or malformed in scenario data. Expected structure: {'config_details': {'device_list_for_instantiation_flat': [...]}}")
        raise ValueError("Malformed device_configs_for_instantiation in scenario data.")

    sim_config_details = device_configs_container["config_details"]
    num_zones = sim_config_details.get("num_zones", DEFAULT_NUM_ZONES)
    
    # Access the flat list of device configurations correctly
    device_instantiation_list = sim_config_details.get("device_list_for_instantiation_flat", [])
    # --- END OF CORRECTION ---

    for dev_config in device_instantiation_list:
        device_name = dev_config.get("name")
        device_type_from_config = dev_config.get("type") 

        if not device_name or not device_type_from_config:
            logger_instance.log_warning("InitEnv", f"Skipping device instantiation due to missing name or type in config: {dev_config}")
            continue
        
        device_instance = None
        
        if device_type_from_config == "TempSensor":
            device_instance = SensingDevice(device_id=device_name, name=device_name, sensor_type="temperature", framework_variant=framework_variant, logger_instance=logger_instance, current_minute_provider=current_minute_provider, max_load=SIM_MAX_LOAD_DEFAULT, behavior_profile=SIM_BEHAVIOR_PROFILE_DEFAULT)
        elif device_type_from_config == "HVAC":
            device_instance = ActuatingDevice(device_id=device_name, name=device_name, actuator_type="hvac_control", framework_variant=framework_variant, logger_instance=logger_instance, current_minute_provider=current_minute_provider, max_load=SIM_MAX_LOAD_DEFAULT, behavior_profile=SIM_BEHAVIOR_PROFILE_DEFAULT)
        elif device_type_from_config == "AccessPoint":
            device_instance = SensingDevice(device_id=device_name, name=device_name, sensor_type="card_swipe", framework_variant=framework_variant, logger_instance=logger_instance, current_minute_provider=current_minute_provider, max_load=SIM_MAX_LOAD_DEFAULT, behavior_profile=SIM_BEHAVIOR_PROFILE_DEFAULT)
        elif device_type_from_config == "WindowSensor": 
            device_instance = SensingDevice(device_id=device_name, name=device_name, sensor_type="window_contact", framework_variant=framework_variant, logger_instance=logger_instance, current_minute_provider=current_minute_provider, max_load=SIM_MAX_LOAD_DEFAULT, behavior_profile=SIM_BEHAVIOR_PROFILE_DEFAULT)
        elif device_type_from_config == "ZoneServer":
            server_max_load = SIM_MAX_LOAD_DEFAULT * 3 
            device_instance = CommunicatingDevice(device_id=device_name, name=device_name, protocol="LocalBus", framework_variant=framework_variant, logger_instance=logger_instance, current_minute_provider=current_minute_provider, max_load=server_max_load, behavior_profile=SIM_BEHAVIOR_PROFILE_DEFAULT, is_server_type=True)
        elif device_type_from_config == "CentralServer":
            server_max_load = SIM_MAX_LOAD_DEFAULT * 3
            device_instance = CommunicatingDevice(device_id=device_name, name=device_name, protocol="Ethernet", framework_variant=framework_variant, logger_instance=logger_instance, current_minute_provider=current_minute_provider, max_load=server_max_load, behavior_profile=SIM_BEHAVIOR_PROFILE_DEFAULT, is_server_type=True)
        elif device_type_from_config == "CompositeController": 
             device_instance = CompositeDevice(device_id=device_name, name=device_name, framework_variant=framework_variant, logger_instance=logger_instance, current_minute_provider=current_minute_provider, max_load=SIM_MAX_LOAD_DEFAULT * 2)


        if device_instance:
            devices_map[device_name] = device_instance
            logger_instance.log_info("InitEnv", f"Instantiated device: {device_name} of type {device_instance.__class__.__name__} (config type: {device_type_from_config}) for framework {framework_variant}")
        else:
            logger_instance.log_warning("InitEnv", f"Could not determine type or instantiate device for name: {device_name} (config type: '{device_type_from_config}')")

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
            # Device.add_relationship expects the policy object or ID via the
            # 'policy' parameter. Passing 'policy_id' causes a TypeError.
            device1.add_relationship(device2, rel_type, policy=policy_identifier)
            logger_instance.log_info(
                "InitEnv",
                f"Added relationship: {dev1_name} --{rel_type}--> {dev2_name}"
                f" (Policy/ID: {policy_identifier or 'None'})",
            )
        else:
            logger_instance.log_warning("InitEnv", f"Could not establish relationship due to missing devices or type: {rel_data}")

    live_zone_states: Dict[str, Dict[str, Any]] = {}
    for i in range(1, num_zones + 1):
        zone_name = f"Zone{i}"
        zone_hvacs_list = [dev_name for dev_name, dev_obj in devices_map.items() 
                           if dev_name.startswith(f"{zone_name}_") and isinstance(dev_obj, ActuatingDevice) and dev_obj.actuator_type == "hvac_control"]
        live_zone_states[zone_name] = {
            "current_temperature": round(random.uniform(*INITIAL_ZONE_TEMP_RANGE), 1),
            "current_occupancy": 0,
            "hvac_status": {hvac_name: "OFF" for hvac_name in zone_hvacs_list}
        }
    logger_instance.log_info("InitEnv", f"Initialized live zone states: {live_zone_states}")
    
    return devices_map, live_zone_states


def run_simulation(
    script_filepath: str, 
    framework_variant: str,
    logger_instance: SimulationLogger 
) -> Dict[str, Any]:
    logger_instance.log_info("SimRunner", f"Starting simulation run. Framework: {framework_variant}, Script: {script_filepath}")
    
    try:
        scenario_data = load_full_scenario(script_filepath)
        loaded_jobs = scenario_data.get("jobs", [])
    except Exception as e:
        logger_instance.log_error("SimRunner", f"Failed to load scenario data: {str(e)}") 
        return {"error": f"Failed to load scenario data: {str(e)}"}
        
    if not loaded_jobs:
        logger_instance.log_error("SimRunner", "No jobs found in scenario data. Aborting simulation.")
        return {"error": "No jobs found in scenario data"}

    duration_minutes = scenario_data.get("duration_minutes", DEFAULT_DURATION_MINUTES)
    
    _current_sim_minute = 0
    def get_current_sim_minute():
        return _current_sim_minute

    try:
        devices, live_zone_states = _initialize_simulation_environment(
            scenario_data, 
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
        "work_with_me_delegations_successful": 0, 
        "work_with_me_delegations_failed": 0,   
        "redelegation_attempts": 0,             
        "redelegation_successes_after_failure": 0, 
        "redelegation_failures_after_failure": 0,  
        "sim_duration_minutes": duration_minutes, "framework_variant": framework_variant,
    }
    
    for device_obj in devices.values(): 
        if hasattr(device_obj, 'sim_metrics_ref'): 
            device_obj.sim_metrics_ref = metrics 

    job_idx = 0 
    for minute_step in range(duration_minutes):
        _current_sim_minute = minute_step
        
        if duration_minutes >= 10 and _current_sim_minute % (max(1, duration_minutes // 10)) == 0 : 
             logger_instance.log_debug("SimRunner", f"--- Minute {_current_sim_minute}/{duration_minutes} ({(minute_step/duration_minutes)*100:.0f}%) ---")
        elif duration_minutes < 10 and _current_sim_minute % 1 == 0: 
             logger_instance.log_debug("SimRunner", f"--- Minute {_current_sim_minute}/{duration_minutes} ({(minute_step/duration_minutes)*100:.0f}%) ---")

        for zone_name, state in live_zone_states.items():
            is_active_hvac_targeting = False
            for hvac_name_env, status_env in list(state["hvac_status"].items()):
                if status_env == "HEATING" and state["current_temperature"] < DEFAULT_TARGET_TEMP_RANGE[1]:
                    is_active_hvac_targeting = True; break
                if status_env == "COOLING" and state["current_temperature"] > DEFAULT_TARGET_TEMP_RANGE[0]:
                    is_active_hvac_targeting = True; break
            
            if not is_active_hvac_targeting: 
                if state["current_temperature"] > 15.0 : 
                    state["current_temperature"] = round(max(10.0, state["current_temperature"] - 0.02), 2) 
                elif state["current_temperature"] < 15.0 :
                    state["current_temperature"] = round(min(30.0, state["current_temperature"] + 0.02), 2)
            
            for hvac_name_env, status_env in list(state["hvac_status"].items()): 
                if status_env == "HEATING":
                    new_temp = round(min(DEFAULT_TARGET_TEMP_RANGE[1] + 3, state["current_temperature"] + TEMP_CHANGE_PER_HVAC_CYCLE / 10.0), 2) 
                    state["current_temperature"] = new_temp
                elif status_env == "COOLING":
                    new_temp = round(max(DEFAULT_TARGET_TEMP_RANGE[0] - 3, state["current_temperature"] - TEMP_CHANGE_PER_HVAC_CYCLE / 10.0), 2)
                    state["current_temperature"] = new_temp
        
        for device_obj in devices.values(): 
            if hasattr(device_obj, 'reduce_load'):
                 device_obj.reduce_load()

        while job_idx < len(loaded_jobs) and loaded_jobs[job_idx]["timestamp"] == _current_sim_minute:
            current_job_dict = loaded_jobs[job_idx].copy() 
            job_idx += 1
            metrics["jobs_processed"] += 1
            target_device_name = current_job_dict["target_device_name"]
            target_device = devices.get(target_device_name)

            if not target_device:
                logger_instance.log_warning("SimRunner", f"Job '{current_job_dict.get('id','N/A')}' targets unknown device '{target_device_name}'. Skipping.")
                metrics["jobs_failed"] += 1
                continue
            
            logger_instance.log_info("SimRunner", f"Dispatching job '{current_job_dict.get('id','N/A')}' ({current_job_dict['job_type']}) to {target_device_name}")
            
            job_params = current_job_dict.get("parameters", {}).copy() 
            job_params["id"] = current_job_dict.get("id", f"job_{metrics['jobs_processed']}") 
            job_params["iot_app_reward"] = current_job_dict.get("iot_app_reward", 0) 

            if current_job_dict["job_type"] == "SENSE_TEMPERATURE":
                target_zone = current_job_dict.get("target_zone")
                if target_zone and target_zone in live_zone_states: 
                    job_params["sensed_temperature_live"] = live_zone_states[target_zone]["current_temperature"]
                elif "sensed_temperature" not in job_params:
                     job_params["sensed_temperature"] = round(random.uniform(15,28),1) 

            outcome = target_device.handle_request(
                from_device=None, 
                task_type=current_job_dict["job_type"],
                load_requested=int(current_job_dict.get("work_units_required", 1)),
                details=job_params
            )
            
            current_job_dict["status"] = "COMPLETED_SUCCESS" if outcome.get("success") else "COMPLETED_FAILURE"
            current_job_dict["completion_time"] = _current_sim_minute 

            if outcome.get("success"):
                metrics["jobs_succeeded"] += 1
                if current_job_dict["completion_time"] <= current_job_dict.get("deadline_time", _current_sim_minute): 
                    metrics["jobs_deadline_met"] += 1
                else: 
                    metrics["jobs_deadline_missed"] += 1; current_job_dict["status"] = "COMPLETED_LATE"
            else:
                metrics["jobs_failed"] += 1; metrics["jobs_deadline_missed"] += 1 

            if outcome.get("success"):
                if current_job_dict["job_type"] == "CARD_SWIPE":
                    direction = job_params.get("direction"); target_zone = current_job_dict.get("target_zone")
                    if target_zone and target_zone in live_zone_states:
                        if direction == "IN": live_zone_states[target_zone]["current_occupancy"] += 1
                        elif direction == "OUT" and live_zone_states[target_zone]["current_occupancy"] > 0: live_zone_states[target_zone]["current_occupancy"] -= 1
                        logger_instance.log_event("EnvUpdate", f"Zone {target_zone} occupancy now {live_zone_states[target_zone]['current_occupancy']}", context_override="Environment")
                elif current_job_dict["job_type"] == "WINDOW_STATUS_CHANGE":
                    status = job_params.get("status"); target_zone = current_job_dict.get("target_zone")
                    if status == "OPENED" and target_zone and target_zone in live_zone_states:
                        old_temp = live_zone_states[target_zone]['current_temperature']; 
                        live_zone_states[target_zone]['current_temperature'] = round(max(10.0, old_temp - TEMP_DROP_WINDOW_OPEN), 1)
                        logger_instance.log_event("EnvUpdate", f"Window opened in {target_zone}. Temp dropped from {old_temp:.1f} to {live_zone_states[target_zone]['current_temperature']:.1f}°C", context_override="Environment")
                elif current_job_dict["job_type"] == "ADJUST_HVAC":
                    new_hvac_state_from_outcome = outcome.get("new_state") 
                    target_zone_hvac = current_job_dict.get("target_zone")
                    if isinstance(new_hvac_state_from_outcome, dict) and target_zone_hvac and target_zone_hvac in live_zone_states:
                        if target_device_name in live_zone_states[target_zone_hvac]["hvac_status"]:
                            live_zone_states[target_zone_hvac]["hvac_status"][target_device_name] = new_hvac_state_from_outcome.get('mode',"OFF")
                            logger_instance.log_event("EnvUpdate", f"HVAC {target_device_name} in {target_zone_hvac} new state: {new_hvac_state_from_outcome}", context_override="Environment")
                        else: logger_instance.log_warning("EnvUpdate", f"HVAC {target_device_name} not found in zone {target_zone_hvac} status for update.", context_override="Environment")

        if duration_minutes >= 30 and _current_sim_minute > 0 and _current_sim_minute % (max(1,duration_minutes // 20)) == 0: 
             for z_name, z_state in live_zone_states.items():
                 logger_instance.log_info("ZoneState", f"{z_name}: Temp={z_state['current_temperature']:.1f}°C, Occupancy={z_state['current_occupancy']}, HVACs={z_state['hvac_status']}")

    total_income_all_devices = 0.0
    total_penalties_all_devices = 0.0
    for dev_obj in devices.values(): 
        if hasattr(dev_obj, 'total_income_earned'): total_income_all_devices += dev_obj.total_income_earned 
        if hasattr(dev_obj, 'total_penalties_received'): total_penalties_all_devices += dev_obj.total_penalties_received
    metrics["total_rewards_achieved_by_devices"] = round(total_income_all_devices, 2)
    metrics["total_penalties_to_devices"] = round(total_penalties_all_devices, 2)
    
    logger_instance.log_info("SimRunner", f"Simulation run completed for framework {framework_variant}. Final Metrics: {json.dumps(metrics, indent=2)}")
    return metrics
