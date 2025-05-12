import argparse
from src.simulations.lab_simulation import LabSimulation 
from src.simulations.building_simulation import BuildingSimulation
from src.utils.logger import SimulationLogger 
import math 
import random 

# Define a fixed seed for reproducibility of random events across comparison runs
YOUR_FIXED_SEED = 42 # You can choose any integer value

def run_simulation_comparison(simulation_type, target_total_devices=20, duration_minutes=240):
    """
    Runs the specified simulation type (focus on 'building') three times:
    1. Baseline (No SIoT framework elements)
    2. Social Basic (Social relations & trust, but no advanced negotiation/misuse prevention)
    3. Full SIoT (Social relations, trust, ODRL-like negotiation, misuse considerations)
    Ensures all runs use the same random seed for fair comparison of random events.
    """
    # Overall logger for the entire set of comparisons for this simulation_type
    # The simulation_name for the logger will be the base type (e.g., "lab" or "building")
    # Individual runs will use a more specific run_context_name for their logs if needed by the sim class.
    comparison_set_logger = SimulationLogger(simulation_name=f"{simulation_type}_ComparisonRun")

    variants_to_run = []
    if simulation_type.lower() == 'building':
        variants_to_run = [
            ("Baseline_No_SIoT", "baseline"),
            ("Social_Basic_No_Negotiation_Misuse", "social_basic"),
            ("Full_SIoT_With_Negotiation_Misuse", "full_siot")
        ]
    elif simulation_type.lower() == 'lab': 
        # Lab sim might not fully implement all variant differences, but runs for structural consistency
         variants_to_run = [
            ("Baseline_No_SIoT", "baseline"),
            ("Social_Basic", "social_basic"), 
            ("Full_SIoT", "full_siot")
        ]
    else:
        print(f"Unsupported simulation type for three-way comparison: {simulation_type}")
        comparison_set_logger.log_error("MAIN_SETUP", f"Unsupported simulation type: {simulation_type}")
        return

    for run_name_display, framework_variant_key in variants_to_run:
        print(f"\n======= {simulation_type.upper()} SIMULATION ({run_name_display}) =======")
        comparison_set_logger.log_info("MAIN_RUN_START", f"Starting run: {run_name_display}", context_override=f"{simulation_type.upper()}_MAIN")
        
        random.seed(YOUR_FIXED_SEED) # Set/Reset the random seed before each run

        current_sim_instance = None
        # run_context_name is for the simulation instance to potentially tag its own logs differently
        # or for the logger to use if it creates sub-loggers (not current logger design)
        run_logger_context_name = f"{simulation_type}_{framework_variant_key}" 

        if simulation_type.lower() == 'lab':
            current_sim_instance = LabSimulation(
                framework_variant=framework_variant_key, 
                num_devices=target_total_devices, 
                duration_minutes=duration_minutes,
                logger_instance=comparison_set_logger, 
                run_context_name=run_logger_context_name 
            )
        elif simulation_type.lower() == 'building':
            # Calculate num_zones and devices_per_zone_avg for BuildingSimulation
            if target_total_devices <= 15: num_fixed_zones = 1
            elif target_total_devices <= 35: num_fixed_zones = 2
            elif target_total_devices <= 60: num_fixed_zones = 3
            else: num_fixed_zones = 4 # Cap at 4 zones for this heuristic
            
            if num_fixed_zones > 0:
                # target = (zones * avg_dev_per_zone) + zones (ZCs) + 1 (BMS)
                devices_per_zone_avg_float = (target_total_devices - 1 - num_fixed_zones) / num_fixed_zones
                devices_per_zone_avg_calculated = max(1, math.ceil(devices_per_zone_avg_float)) 
            else: # Should not happen if target_total_devices > 1 (BMS alone)
                devices_per_zone_avg_calculated = 1 
                num_fixed_zones = 1 # Ensure at least one zone if calculation leads to zero

            actual_num_devices_created = (num_fixed_zones * devices_per_zone_avg_calculated) + num_fixed_zones + 1
            comparison_set_logger.log_info("SIM_SETUP",f"Target devices: {target_total_devices}. Building sim ({run_name_display}) with: {num_fixed_zones} zones, {devices_per_zone_avg_calculated} avg devices/zone. Approx created: {actual_num_devices_created}", context_override=run_logger_context_name)

            current_sim_instance = BuildingSimulation(
                framework_variant=framework_variant_key, 
                num_zones=num_fixed_zones,
                devices_per_zone_avg=devices_per_zone_avg_calculated,
                duration_minutes=duration_minutes,
                logger_instance=comparison_set_logger,
                run_context_name=run_logger_context_name
            )
        
        if current_sim_instance:
            current_sim_instance.run() # This will call report(), which should store metrics via logger
        else:
            comparison_set_logger.log_error("MAIN_ERROR", f"Could not instantiate simulation for {run_name_display}", context_override=f"{simulation_type.upper()}_MAIN")
        
        comparison_set_logger.log_info("MAIN_RUN_END", f"Finished run: {run_name_display}", context_override=f"{simulation_type.upper()}_MAIN")


    # Log comparison after all runs are complete for this simulation_type
    comparison_set_logger.log_comparison(
        simulation_type_for_comparison_key=simulation_type.lower(), # e.g., "lab" or "building"
        variant_keys_in_order=[key for name, key in variants_to_run] # Pass the keys used for storing metrics
    )


def main():
    parser = argparse.ArgumentParser(description='Run Comparative IoT Device Simulation')
    parser.add_argument(
        'simulation_type',
        choices=['lab', 'building'],
        help='Type of simulation to run (lab or building)'
    )
    parser.add_argument(
        '--num_devices', 
        type=int,
        default=30, 
        help='Approximate total number of devices in the simulation (for building, this influences zones/devices_per_zone)'
    )
    parser.add_argument(
        '--duration',
        type=int,
        default=240, # Default 4 simulation hours
        help='Duration of the simulation in minutes'
    )
    
    args = parser.parse_args()
    run_simulation_comparison(args.simulation_type, args.num_devices, args.duration)


if __name__ == "__main__":
    main()
