import os
import argparse
import json
from datetime import datetime
from typing import Dict, List, Any 

# Assuming scenario_generator.py is in src.simulations
from src.simulations.scenario_generator import (
    generate_simple_control_scenario,
    generate_high_load_scenario, 
    DEFAULT_DURATION_MINUTES,
    DEFAULT_NUM_ZONES,
    DEFAULT_NUM_CENTRAL_SERVERS,
    DEFAULT_DEVICES_PER_ZONE 
)

# Assuming run_scenario_simulation.py is in src
from src.run_scenario_simulation import run_simulation 
from src.utils.logger import SimulationLogger 

def save_scenario_to_json(scenario_data: Dict[str, Any], base_filename: str, output_dir: str = "scripts") -> str:
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
    print("-" * 90)
    header = f"{'Metric':<35}"
    for variant in framework_variants:
        header += f" {variant:<17}"
    print(header)
    print("-" * 90)

    all_metric_keys = set()
    for variant_metrics in results.values():
        if variant_metrics: 
            all_metric_keys.update(variant_metrics.keys())
    
    ordered_keys = [
        "total_jobs_in_script", "jobs_processed", "jobs_succeeded", "jobs_failed",
        "jobs_deadline_met", "jobs_deadline_missed",
        "total_rewards_achieved_by_devices", "total_penalties_to_devices",
        "unresponsive_device_rejections", "faulty_device_actions_failed",
        "misuse_incidents_detected", "selfish_rejections",
        "successful_negotiations", "failed_negotiations",
        "back_me_invocations_successful", "back_me_invocations_failed",
        "sim_duration_minutes"
    ]
    display_keys = ordered_keys + sorted(list(all_metric_keys - set(ordered_keys)))

    for metric_key in display_keys:
        if metric_key == "framework_variant": continue 

        row = f"{metric_key:<35}"
        for variant in framework_variants:
            value = results.get(variant, {}).get(metric_key, "N/A")
            if isinstance(value, float):
                value_str = f"{value:<17.2f}"
            else:
                value_str = f"{str(value):<17}"
            row += f" {value_str}"
        print(row)
    print("-" * 90)


def main():
    parser = argparse.ArgumentParser(description='Generate and run building simulation scenarios.')
    
    parser.add_argument('scenario_type', type=str, choices=['control_case', 'high_load_case'], 
                        help='The type of scenario to run (e.g., "control_case", "high_load_case")')
    
    parser.add_argument('--duration', type=int, default=DEFAULT_DURATION_MINUTES,
                        help=f'Simulation duration in minutes (default: {DEFAULT_DURATION_MINUTES})')
    parser.add_argument('--zones', type=int, default=DEFAULT_NUM_ZONES,
                        help=f'Number of zones (default: {DEFAULT_NUM_ZONES})')
    parser.add_argument('--servers_central', type=int, default=DEFAULT_NUM_CENTRAL_SERVERS,
                        help=f'Number of central servers (default: {DEFAULT_NUM_CENTRAL_SERVERS})')
    
    args = parser.parse_args()

    scripts_output_dir = "scripts"
    os.makedirs(scripts_output_dir, exist_ok=True)
    logs_output_dir = "logs"
    os.makedirs(logs_output_dir, exist_ok=True)

    scenario_data = None
    script_base_filename = ""

    if args.scenario_type == "control_case":
        print(f"Selected scenario: Control Case")
        print(f"Generating 'control_case' scenario script with duration: {args.duration} mins, zones: {args.zones}, central_servers: {args.servers_central}...")
        
        jobs_list = generate_simple_control_scenario(
            duration_minutes=args.duration,
            num_zones=args.zones,
            num_central_servers=args.servers_central 
        )
        from src.simulations.scenario_generator import get_device_names 
        device_configs = get_device_names(args.zones, DEFAULT_DEVICES_PER_ZONE, args.servers_central)
        scenario_data = {
            "scenario_name": "Control Case Scenario", # Added for consistency
            "duration_minutes": args.duration,
            "jobs": jobs_list,
            "initial_relationships": [], 
            "device_configs_for_instantiation": device_configs 
        }
        script_base_filename = "control_case_script"
        
    elif args.scenario_type == "high_load_case":
        print(f"Selected scenario: High Load Case")
        print(f"Generating 'high_load_case' scenario script with duration: {args.duration} mins, zones: {args.zones}, central_servers: {args.servers_central}...")
        
        scenario_data = generate_high_load_scenario(
            duration_minutes=args.duration,
            num_zones=args.zones,
            num_central_servers=args.servers_central
        )
        script_base_filename = "high_load_case_script"
    
    else:
        print(f"Unknown scenario type: {args.scenario_type}")
        return

    if scenario_data:
        script_file_path = save_scenario_to_json(scenario_data, script_base_filename, scripts_output_dir)
        print(f"Saved '{args.scenario_type}' scenario data to {script_file_path}")
        print(f"Generated {len(scenario_data.get('jobs',[]))} jobs in the script.")

        framework_variants = ["baseline", "social_basic", "full_siot"]
        all_results = {}

        sim_config_for_run_param = { # Renamed to avoid conflict with outer scope sim_config
            "duration_minutes": args.duration,
            "num_zones": args.zones,
            "devices_per_zone_config": scenario_data.get('device_configs_for_instantiation', {}).get('config_details',{}).get('devices_per_zone_config', DEFAULT_DEVICES_PER_ZONE),
            "num_central_servers": args.servers_central
        }

        for variant in framework_variants:
            print(f"\nRunning '{args.scenario_type}' with framework '{variant}' using script: {script_file_path}...")
            
            log_file_name = f"sim_log_{args.scenario_type}_{variant}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            full_log_path = os.path.join(logs_output_dir, log_file_name)

            logger = SimulationLogger() 
            
            metrics = run_simulation(
                script_filepath=script_file_path, 
                sim_config_from_main=sim_config_for_run_param, # Corrected keyword argument
                framework_variant=variant,
                logger_instance=logger
            )
            all_results[variant] = metrics
            
            if hasattr(logger, 'log_info') and callable(getattr(logger, 'log_info')):
                logger.log_info("Main", f"Completed simulation for {args.scenario_type} - {variant}. Metrics: {json.dumps(metrics, indent=2) if metrics else 'No metrics returned'}")
            
            if hasattr(logger, 'close') and callable(getattr(logger, 'close')):
                logger.close() 

        if all_results:
            print_metrics_comparison(all_results, framework_variants)
        else:
            print(f"No simulation results to compare for '{args.scenario_type}'.")

if __name__ == "__main__":
    main()
