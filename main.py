import os
import argparse
import json
from datetime import datetime
from typing import Dict, List, Any, Optional 

from src.simulations.scenario_generator import (
    generate_simple_control_scenario,
    generate_high_load_scenario,
    DEFAULT_DURATION_MINUTES,
    DEFAULT_DEVICES_PER_ZONE,
    DEFAULT_NUM_ZONES, 
    DEFAULT_NUM_CENTRAL_SERVERS,
    get_device_names 
)

from src.run_scenario_simulation import run_simulation 
from src.utils.logger import SimulationLogger 

def save_scenario_to_json_main(scenario_data: Dict[str, Any], base_filename: str, output_dir: str = "scripts") -> str:
    """
    Saves the generated scenario dictionary (jobs, relationships, etc.) to a JSON file.
    The filename will include a timestamp.
    """
    os.makedirs(output_dir, exist_ok=True)
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{base_filename}_{timestamp_str}.json"
    filepath = os.path.join(output_dir, filename)
    
    with open(filepath, 'w') as f:
        json.dump(scenario_data, f, indent=4) 
    return filepath

def print_metrics_comparison(results: Dict[str, Dict[str, Any]], framework_variants: List[str]):
    """Prints a comparison table of simulation metrics."""
    print("\nSimulation Results Comparison:")
    table_width = 140 
    print("-" * table_width) 
    metric_name_col_width = 45 
    value_col_width = 20 

    header = f"{'Metric':<{metric_name_col_width}}" 
    for variant in framework_variants:
        header += f" {variant:<{value_col_width}}" 
    print(header)
    print("-" * table_width)

    all_metric_keys = set()
    for variant_metrics in results.values():
        if variant_metrics and isinstance(variant_metrics, dict): 
            all_metric_keys.update(variant_metrics.keys())
    
    ordered_keys = [
        "total_jobs_in_script", "jobs_processed", "jobs_succeeded", "jobs_failed",
        "jobs_deadline_met", "jobs_deadline_missed",
        "total_rewards_achieved_by_devices", "total_penalties_to_devices",
        "unresponsive_device_rejections", "faulty_device_actions_failed",
        "misuse_incidents_detected", "selfish_rejections",
        "successful_negotiations", "failed_negotiations",
        "back_me_invocations_successful", "back_me_invocations_failed",
        "work_with_me_delegations_successful", "work_with_me_delegations_failed", 
        "redelegation_attempts", "redelegation_successes_after_failure", "redelegation_failures_after_failure", 
        "sim_duration_minutes"
    ]
    
    display_keys = ordered_keys + sorted(list(all_metric_keys - set(ordered_keys)))

    for metric_key in display_keys:
        if metric_key == "framework_variant": continue 

        row = f"{metric_key:<{metric_name_col_width}}" 
        for variant in framework_variants:
            value = results.get(variant, {}).get(metric_key, "N/A")
            if isinstance(value, float):
                value_str = f"{value:<{value_col_width}.2f}" 
            else:
                value_str = f"{str(value):<{value_col_width}}" 
            row += f" {value_str}"
        print(row)
    print("-" * table_width)


def main():
    parser = argparse.ArgumentParser(description='Generate and run building simulation scenarios.')
    
    parser.add_argument('scenario_type', type=str, choices=['control_case', 'high_load_case'], 
                        help='The type of scenario to run (e.g., "control_case", "high_load_case")')
    
    parser.add_argument('--duration', type=int, default=DEFAULT_DURATION_MINUTES,
                        help=f'Simulation duration in minutes (default: {DEFAULT_DURATION_MINUTES})')
    parser.add_argument('--zones', type=int, default=DEFAULT_NUM_ZONES,
                        help=f'Number of zones (default: {DEFAULT_NUM_ZONES})')
    parser.add_argument('--devices_per_zone', type=json.loads, default=None, 
                        help='Devices per zone as JSON string e.g. \'{"TempSensor":2, "HVAC":1}\'. Uses defaults if not provided.')
    parser.add_argument('--servers_central', type=int, default=DEFAULT_NUM_CENTRAL_SERVERS,
                        help=f'Number of central servers (default: {DEFAULT_NUM_CENTRAL_SERVERS})')
    
    args = parser.parse_args()

    devices_config_to_use = args.devices_per_zone if args.devices_per_zone else DEFAULT_DEVICES_PER_ZONE

    scripts_output_dir = "scripts"
    os.makedirs(scripts_output_dir, exist_ok=True)
    logs_output_dir = "logs" # Logger will create files in "logs" based on its internal logic
    os.makedirs(logs_output_dir, exist_ok=True) # Ensure it exists for other potential logs

    scenario_data: Optional[Dict[str, Any]] = None 
    script_base_filename = ""

    if args.scenario_type == "control_case":
        print(f"Selected scenario: Control Case")
        print(f"Generating 'control_case' scenario script with duration: {args.duration} mins, zones: {args.zones}, central_servers: {args.servers_central}...")
        
        jobs_list = generate_simple_control_scenario(
            duration_minutes=args.duration,
            num_zones=args.zones,
            devices_per_zone_config=devices_config_to_use,
            num_central_servers=args.servers_central 
        )
        device_configs_map = get_device_names(args.zones, devices_config_to_use, args.servers_central)
        
        scenario_data = {
            "scenario_name": "Control Case Scenario",
            "duration_minutes": args.duration,
            "jobs": jobs_list,
            "initial_relationships": [], 
            "device_configs_for_instantiation": device_configs_map 
        }
        script_base_filename = "control_case_script"
        
    elif args.scenario_type == "high_load_case":
        print(f"Selected scenario: High Load Case")
        print(f"Generating 'high_load_case' scenario script with duration: {args.duration} mins, zones: {args.zones}, central_servers: {args.servers_central}...")
        
        scenario_data = generate_high_load_scenario(
            duration_minutes=args.duration,
            num_zones=args.zones,
            devices_per_zone_config=devices_config_to_use,
            num_central_servers=args.servers_central
        )
        script_base_filename = "high_load_case_script"
    
    else:
        print(f"Unknown scenario type: {args.scenario_type}")
        return

    if scenario_data:
        script_file_path = save_scenario_to_json_main(scenario_data, script_base_filename, scripts_output_dir)
        print(f"Saved '{args.scenario_type}' scenario data to {script_file_path}")
        print(f"Generated {len(scenario_data.get('jobs',[]))} jobs in the script.")

        framework_variants = ["baseline", "social_basic", "full_siot"]
        all_results = {}

        for variant in framework_variants:
            print(f"\nRunning '{args.scenario_type}' with framework '{variant}' using script: {script_file_path}...")
            
            # The SimulationLogger will create its own log file based on simulation_name.
            # The 'full_log_path' variable previously constructed by main.py is not directly used by the logger's __init__.
            logger = SimulationLogger(simulation_name=f"{args.scenario_type}_{variant}", log_to_file=True, log_to_console=True)
            
            metrics = run_simulation(
                script_filepath=script_file_path, 
                framework_variant=variant,
                logger_instance=logger 
            )
            all_results[variant] = metrics
            
            logger.log_info("Main", f"Completed simulation for {args.scenario_type} - {variant}. Metrics: {json.dumps(metrics, indent=2) if metrics else 'No metrics returned'}")
            
            if hasattr(logger, 'close') and callable(getattr(logger, 'close')):
                logger.close() 

        if all_results:
            print_metrics_comparison(all_results, framework_variants)
        else:
            print(f"No simulation results to compare for '{args.scenario_type}'.")

if __name__ == "__main__":
    main()

