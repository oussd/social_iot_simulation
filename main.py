import argparse
from src.simulations.lab_simulation import LabSimulation
from src.simulations.building_simulation import BuildingSimulation
from src.simulations.building_simulation_complex import BuildingSimulationComplex
from src.simulations.building_simulation_complex_v2 import BuildingSimulationComplex_V2
from src.simulations.building_simulation_complex_v3 import BuildingSimulationComplex_V3
from src.simulations.scenario_loader import get_device_config_for_50_devices, generate_building_job_list 
# Removed SimpleJob alias, assume BuildingJob defined in V3 sim is compatible with ScenarioJob
from src.utils.logger import SimulationLogger
import math
import random

YOUR_FIXED_SEED = 42

def run_simulation_comparison(simulation_type, target_total_devices_param=50, duration_minutes=240):
    random.seed(YOUR_FIXED_SEED) # Set seed ONCE for the entire comparison set

    comparison_set_logger = SimulationLogger(simulation_name=f"{simulation_type}_ComparisonRun")
    variants_to_run = [
        ("Baseline_No_SIoT", "baseline"),
        ("Social_Basic", "social_basic"),
        ("Full_SIoT", "full_siot")
    ]

    # --- Prepare Device Configuration and Pregenerated Jobs ---
    # This device_config will be used by ALL building simulations to aim for 50 devices
    # The pregenerated_job_list is ONLY for building_complex_v3
    
    device_config_for_50 = get_device_config_for_50_devices()
    pregenerated_jobs_for_v3 = None

    if simulation_type.lower() == 'building_complex_v3':
        pregenerated_jobs_for_v3 = generate_building_job_list(
            duration_minutes=duration_minutes,
            num_zones=device_config_for_50['num_zones'],
            primitives_per_zone_dist=device_config_for_50['primitives_per_zone_dist'],
            job_id_prefix="bldg_cplx3_job"
        )
        comparison_set_logger.log_info("MAIN_SETUP", f"Pregenerated {len(pregenerated_jobs_for_v3)} jobs for {simulation_type}.",
                                     context_override=f"{simulation_type.upper()}_MAIN")
    elif simulation_type.lower().startswith('building'):
         comparison_set_logger.log_info("MAIN_SETUP", f"Targeting ~{device_config_for_50['total_target_devices']} devices for {simulation_type}. Using: {device_config_for_50['num_zones']} zones, primitives per zone: {device_config_for_50['primitives_per_zone_dist']}.",
                                     context_override=f"{simulation_type.upper()}_MAIN")


    for run_name_display, framework_variant_key in variants_to_run:
        print(f"\n======= {simulation_type.upper()} SIMULATION ({run_name_display} - Variant: {framework_variant_key}) =======")
        comparison_set_logger.log_info("MAIN_RUN_START", f"Starting run: {run_name_display} for {simulation_type} with variant {framework_variant_key}",
                                     context_override=f"{simulation_type.upper()}_MAIN")
        
        current_sim_instance = None
        run_logger_context_name = f"{simulation_type}_{framework_variant_key}"

        if simulation_type.lower() == 'lab':
            current_sim_instance = LabSimulation(
                framework_variant=framework_variant_key,
                num_devices=target_total_devices_param, 
                duration_minutes=duration_minutes,
                logger_instance=comparison_set_logger,
                run_context_name=run_logger_context_name
            )
        elif simulation_type.lower() == 'building_complex_v3':
            v3_args = {
                'framework_variant': framework_variant_key,
                'duration_minutes': duration_minutes,
                'logger_instance': comparison_set_logger,
                'run_context_name': run_logger_context_name,
                'device_config': device_config_for_50, # This now contains num_zones, primitive_dist, behavioral_config
                'pregenerated_job_list': list(pregenerated_jobs_for_v3) if pregenerated_jobs_for_v3 else [] # Pass a copy
            }
            current_sim_instance = BuildingSimulationComplex_V3(**v3_args)
        elif simulation_type.lower().startswith('building'): # For building, building_complex, building_complex_v2
            # These older sims expect num_zones and primitives_per_zone_dist directly
            # They will use their internal job generation (now deterministic due to master seed)
            # They also need to handle **kwargs in their __init__ for behavioral params if they use device.py directly
            sim_constructor_args = {
                'framework_variant': framework_variant_key,
                'duration_minutes': duration_minutes,
                'logger_instance': comparison_set_logger,
                'run_context_name': run_logger_context_name,
                'num_zones': device_config_for_50['num_zones'],
                'primitives_per_zone_dist': device_config_for_50['primitives_per_zone_dist']
            }
            if simulation_type.lower() == 'building':
                current_sim_instance = BuildingSimulation(**sim_constructor_args)
            elif simulation_type.lower() == 'building_complex':
                current_sim_instance = BuildingSimulationComplex(**sim_constructor_args)
            elif simulation_type.lower() == 'building_complex_v2':
                # V2 specifically uses behavioral_config for its device setup
                sim_constructor_args['behavioral_config_override'] = device_config_for_50['behavioral_config']
                current_sim_instance = BuildingSimulationComplex_V2(**sim_constructor_args)

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
        choices=['lab', 'building', 'building_complex', 'building_complex_v2', 'building_complex_v3'], 
        help='Type of simulation to run'
    )
    parser.add_argument(
        '--num_devices',
        type=int,
        default=50, 
        help='Target number of devices (used for Lab; building types now deterministically aim for ~50 via scenario_loader)'
    )
    parser.add_argument(
        '--duration',
        type=int,
        default=240,
        help='Duration of the simulation in minutes'
    )

    args = parser.parse_args()
    # For building simulations, the device count is primarily driven by get_device_config_for_50_devices()
    # For lab, num_devices argument is used directly.
    run_simulation_comparison(args.simulation_type, args.num_devices, args.duration)

if __name__ == "__main__":
    main()
