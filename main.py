import argparse
from src.simulations.lab_simulation import LabSimulation
from src.simulations.building_simulation import BuildingSimulation
from src.utils.logger import SimulationLogger # Assuming your logger is here
import math # For ceiling function
import random # Import the random module to set the seed

# Define a fixed seed for reproducibility of random events across comparison runs
YOUR_FIXED_SEED = 42 # You can choose any integer value

def run_simulation_comparison(simulation_type, target_total_devices=10, duration_minutes=240):
    """
    Runs the specified simulation type twice: once with the SIoT framework enabled,
    and once with it disabled (baseline), then logs a comparison.
    Ensures both runs use the same random seed for fair comparison of random events.
    """
    logger = SimulationLogger(simulation_name=simulation_type) # Logger for this comparison set

    # --- SIoT Framework ENABLED Run ---
    print(f"\n======= {simulation_type.upper()} SIMULATION (SIoT Framework ENABLED) =======")
    random.seed(YOUR_FIXED_SEED) # Set the random seed before the first run
    sim_framework_on = None
    if simulation_type.lower() == 'lab':
        sim_framework_on = LabSimulation(
            framework_enabled=True, 
            num_devices=target_total_devices, # LabSimulation takes num_devices directly
            duration_minutes=duration_minutes,
            logger_instance=logger 
        )
    elif simulation_type.lower() == 'building':
        # Calculate num_zones and devices_per_zone_avg for BuildingSimulation
        if target_total_devices <= 10:
            num_fixed_zones = 1
        elif target_total_devices <= 25:
            num_fixed_zones = 2
        else:
            num_fixed_zones = 3 
            
        if num_fixed_zones > 0:
            devices_per_zone_avg_float = (target_total_devices - 1 - num_fixed_zones) / num_fixed_zones
            devices_per_zone_avg_calculated = max(1, math.ceil(devices_per_zone_avg_float)) 
        else: 
            devices_per_zone_avg_calculated = 1 
            num_fixed_zones = 1 

        actual_num_devices_created = (num_fixed_zones * devices_per_zone_avg_calculated) + num_fixed_zones + 1
        logger.log_info("SIM_SETUP",f"Target devices: {target_total_devices}. Building sim (ON) with: {num_fixed_zones} zones, {devices_per_zone_avg_calculated} avg devices/zone. Approx created: {actual_num_devices_created}")

        sim_framework_on = BuildingSimulation(
            framework_enabled=True, 
            num_zones=num_fixed_zones,
            devices_per_zone_avg=devices_per_zone_avg_calculated,
            duration_minutes=duration_minutes,
            logger_instance=logger
        )
    
    if sim_framework_on:
        sim_framework_on.run()

    # --- Baseline - Framework DISABLED Run ---
    print(f"\n======= {simulation_type.upper()} SIMULATION (Baseline - Framework DISABLED) =======")
    random.seed(YOUR_FIXED_SEED) # RESET the random seed to the SAME VALUE before the second run
    sim_framework_off = None
    if simulation_type.lower() == 'lab':
        sim_framework_off = LabSimulation(
            framework_enabled=False, 
            num_devices=target_total_devices, 
            duration_minutes=duration_minutes,
            logger_instance=logger
        )
    elif simulation_type.lower() == 'building':
        # Use the same calculated num_zones and devices_per_zone_avg for the baseline comparison
        # Recalculate for clarity, ensuring they are identical to the 'ON' run setup parameters
        if target_total_devices <= 10:
            num_fixed_zones_off = 1
        elif target_total_devices <= 25:
            num_fixed_zones_off = 2
        else:
            num_fixed_zones_off = 3
            
        if num_fixed_zones_off > 0:
            devices_per_zone_avg_float_off = (target_total_devices - 1 - num_fixed_zones_off) / num_fixed_zones_off
            devices_per_zone_avg_calculated_off = max(1, math.ceil(devices_per_zone_avg_float_off))
        else:
            devices_per_zone_avg_calculated_off = 1
            num_fixed_zones_off = 1
        
        actual_num_devices_created_off = (num_fixed_zones_off * devices_per_zone_avg_calculated_off) + num_fixed_zones_off + 1
        logger.log_info("SIM_SETUP",f"Target devices: {target_total_devices}. Building sim (OFF) with: {num_fixed_zones_off} zones, {devices_per_zone_avg_calculated_off} avg devices/zone. Approx created: {actual_num_devices_created_off}")


        sim_framework_off = BuildingSimulation(
            framework_enabled=False, 
            num_zones=num_fixed_zones_off,
            devices_per_zone_avg=devices_per_zone_avg_calculated_off,
            duration_minutes=duration_minutes,
            logger_instance=logger
        )

    if sim_framework_off:
        sim_framework_off.run()

    # Log comparison after both runs are complete
    logger.log_comparison(simulation_type_for_comparison_key=simulation_type.lower())


def main():
    parser = argparse.ArgumentParser(description='Run Comparative IoT Device Simulation')
    parser.add_argument(
        'simulation_type',
        choices=['lab', 'building'],
        help='Type of simulation to run (lab or building)'
    )
    parser.add_argument(
        '--num_devices', # This will be the target total devices
        type=int,
        default=10, 
        help='Approximate total number of devices in the simulation (for building, this influences zones/devices_per_zone)'
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
