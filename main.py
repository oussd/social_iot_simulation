import argparse
from src.simulations.lab_simulation import LabSimulation
from src.simulations.building_simulation import BuildingSimulation
from src.simulations.building_simulation_complex import BuildingSimulationComplex
from src.simulations.building_simulation_complex_v2 import BuildingSimulationComplex_V2 # New import
from src.utils.logger import SimulationLogger
import math
import random

YOUR_FIXED_SEED = 42

def run_simulation_comparison(simulation_type, target_total_devices=30, duration_minutes=240):
    comparison_set_logger = SimulationLogger(simulation_name=f"{simulation_type}_ComparisonRun")

    variants_to_run = []
    if simulation_type.lower() in ['building', 'building_complex', 'building_complex_v2']: # Added new type
        variants_to_run = [
            ("Baseline_No_SIoT", "baseline"),
            ("Social_Basic_No_Negotiation_Misuse", "social_basic"),
            ("Full_SIoT_With_Negotiation_Misuse", "full_siot")
        ]
    elif simulation_type.lower() == 'lab':
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
        print(f"\n======= {simulation_type.upper()} SIMULATION ({run_name_display} - Variant: {framework_variant_key}) =======")
        comparison_set_logger.log_info("MAIN_RUN_START", f"Starting run: {run_name_display} for {simulation_type} with variant {framework_variant_key}",
                                     context_override=f"{simulation_type.upper()}_MAIN")

        random.seed(YOUR_FIXED_SEED)
        current_sim_instance = None
        run_logger_context_name = f"{simulation_type}_{framework_variant_key}"

        if simulation_type.lower() == 'lab':
            current_sim_instance = LabSimulation(
                framework_variant=framework_variant_key,
                num_devices=target_total_devices,
                duration_minutes=duration_minutes,
                logger_instance=comparison_set_logger,
                run_context_name=run_logger_context_name
            )
        elif simulation_type.lower() in ['building', 'building_complex', 'building_complex_v2']:
            if target_total_devices <= 1:
                num_fixed_zones = 0
                devices_per_zone_avg_calculated = 0
            elif target_total_devices <= 15: num_fixed_zones = 1
            elif target_total_devices <= 35: num_fixed_zones = 2
            elif target_total_devices <= 60: num_fixed_zones = 3
            else: num_fixed_zones = 4

            if num_fixed_zones > 0:
                devices_per_zone_avg_float = (target_total_devices - 1 - num_fixed_zones) / num_fixed_zones
                devices_per_zone_avg_calculated = max(1, math.ceil(devices_per_zone_avg_float))
            elif num_fixed_zones == 0 and target_total_devices == 1:
                 devices_per_zone_avg_calculated = 0
            else:
                devices_per_zone_avg_calculated = 1
                num_fixed_zones = 1

            actual_num_devices_created = (num_fixed_zones * devices_per_zone_avg_calculated) + num_fixed_zones + (1 if num_fixed_zones > 0 else target_total_devices)
            comparison_set_logger.log_info("SIM_SETUP",f"Target devices: {target_total_devices}. {simulation_type} sim ({run_name_display}) with: {num_fixed_zones} zones, {devices_per_zone_avg_calculated} avg devices/zone. Approx created: {actual_num_devices_created}",
                                         context_override=run_logger_context_name)

            common_sim_args = {
                'framework_variant': framework_variant_key,
                'num_zones': num_fixed_zones,
                'devices_per_zone_avg': devices_per_zone_avg_calculated,
                'duration_minutes': duration_minutes,
                'logger_instance': comparison_set_logger,
                'run_context_name': run_logger_context_name
            }

            if simulation_type.lower() == 'building':
                current_sim_instance = BuildingSimulation(**common_sim_args)
            elif simulation_type.lower() == 'building_complex':
                current_sim_instance = BuildingSimulationComplex(**common_sim_args)
            elif simulation_type.lower() == 'building_complex_v2': # New condition
                current_sim_instance = BuildingSimulationComplex_V2(**common_sim_args)

        if current_sim_instance:
            current_sim_instance.run()
        else:
            comparison_set_logger.log_error("MAIN_ERROR", f"Could not instantiate simulation for {run_name_display} of type {simulation_type}",
                                          context_override=f"{simulation_type.upper()}_MAIN")

        comparison_set_logger.log_info("MAIN_RUN_END", f"Finished run: {run_name_display} for {simulation_type} with variant {framework_variant_key}",
                                     context_override=f"{simulation_type.upper()}_MAIN")

    comparison_set_logger.log_comparison(
        simulation_type_for_comparison_key=simulation_type.lower(),
        variant_keys_in_order=[key for name, key in variants_to_run]
    )

def main():
    parser = argparse.ArgumentParser(description='Run Comparative IoT Device Simulation')
    parser.add_argument(
        'simulation_type',
        choices=['lab', 'building', 'building_complex', 'building_complex_v2'], # Added 'building_complex_v2'
        help='Type of simulation to run (lab, building, building_complex, or building_complex_v2)'
    )
    parser.add_argument(
        '--num_devices',
        type=int,
        default=30,
        help='Approximate total number of devices in the simulation (for building types, this influences zones/devices_per_zone)'
    )
    parser.add_argument(
        '--duration',
        type=int,
        default=240,
        help='Duration of the simulation in minutes'
    )

    args = parser.parse_args()
    run_simulation_comparison(args.simulation_type, args.num_devices, args.duration)

if __name__ == "__main__":
    main()
