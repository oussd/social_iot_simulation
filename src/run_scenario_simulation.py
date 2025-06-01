import os
from datetime import time
from src.simulations.building_scenario_config import (
    BuildingScenario, TimeParameters, ZoneConfig, DeviceConfig,
    EnvironmentalConfig, EventProbabilities,
    save_scenario_to_json
)
from src.simulations.scenario_generator import BuildingScenarioGenerator
from src.simulations.building_simulation import BuildingSimulation
from src.utils.logger import SimulationLogger


def create_sample_scenario() -> BuildingScenario:
    """Create a sample building scenario for testing."""
    # Time parameters
    time_params = TimeParameters(
        simulation_duration_minutes=1440,  # 24 hours
        working_hours_start=time(8, 0),    # 8 AM
        working_hours_end=time(18, 0),     # 6 PM
        time_zone="UTC"
    )
    
    # Zones
    zones = [
        ZoneConfig(
            zone_id="office_1",
            zone_type="office",
            size_m2=100.0,
            base_temperature=22.0,
            occupancy_pattern={
                "8": 0.8,   # 8 AM - 80% occupancy
                "9": 0.9,   # 9 AM - 90% occupancy
                "12": 0.3,  # 12 PM - 30% occupancy (lunch)
                "13": 0.8,  # 1 PM - 80% occupancy
                "17": 0.6,  # 5 PM - 60% occupancy
                "18": 0.1   # 6 PM - 10% occupancy
            }
        ),
        ZoneConfig(
            zone_id="meeting_1",
            zone_type="meeting_room",
            size_m2=50.0,
            base_temperature=21.0,
            occupancy_pattern={
                "9": 0.7,   # 9 AM - 70% occupancy
                "12": 0.1,  # 12 PM - 10% occupancy
                "14": 0.8,  # 2 PM - 80% occupancy
                "17": 0.3   # 5 PM - 30% occupancy
            }
        )
    ]
    
    # Devices
    devices = []
    for zone in zones:
        # Add temperature sensors
        devices.append(DeviceConfig(
            device_id=f"temp_sensor_{zone.zone_id}",
            device_type="temperature_sensor",
            zone_id=zone.zone_id,
            update_interval_minutes=5,
            capabilities=["temperature_reading"]
        ))
        
        # Add HVAC controls
        devices.append(DeviceConfig(
            device_id=f"hvac_{zone.zone_id}",
            device_type="hvac_control",
            zone_id=zone.zone_id,
            update_interval_minutes=1,
            capabilities=["temperature_control", "ventilation_control"]
        ))
    
    # Environmental configuration
    env_config = EnvironmentalConfig(
        base_temperature_range=(18.0, 26.0),
        weather_conditions=[
            {"type": "sunny", "temp_effect": 2.0},
            {"type": "cloudy", "temp_effect": 0.0},
            {"type": "rainy", "temp_effect": -1.0}
        ],
        temperature_variation_per_hour=1.5,
        window_effect_on_temperature=-2.0
    )
    
    # Event probabilities
    event_probs = EventProbabilities(
        window_open_probability=0.01,      # 1% chance per minute
        access_event_probability=0.05,     # 5% chance per minute during working hours
        emergency_event_probability=0.001,  # 0.1% chance per minute
        device_failure_probability=0.0001  # 0.01% chance per minute
    )
    
    # Generate the scenario
    generator = BuildingScenarioGenerator(
        time_parameters=time_params,
        zones=zones,
        devices=devices,
        environmental_config=env_config,
        event_probabilities=event_probs
    )
    
    return generator.generate_scenario()


def run_simulation(scenario: BuildingScenario, framework_variant: str):
    """Run a simulation with the given scenario and framework variant."""
    # Create logger
    logger = SimulationLogger()
    run_context = f"scenario_{framework_variant}"
    
    # Create and run simulation
    simulation = BuildingSimulation(
        framework_variant=framework_variant,
        scenario=scenario,
        logger_instance=logger,
        run_context_name=run_context
    )
    
    # Setup devices
    simulation.setup_devices()
    
    # Run simulation
    simulation.run()
    
    return simulation.metrics


def main():
    # Create output directory if it doesn't exist
    os.makedirs("output", exist_ok=True)
    
    # Generate scenario
    scenario = create_sample_scenario()
    
    # Save scenario to file
    scenario_file = save_scenario_to_json(scenario, "output/building_scenario")
    print(f"Saved scenario to {scenario_file}")
    
    # Run simulations with different framework variants
    framework_variants = ["baseline", "social_basic", "full_siot"]
    results = {}
    
    for variant in framework_variants:
        print(f"\nRunning simulation with {variant} framework...")
        metrics = run_simulation(scenario, variant)
        results[variant] = metrics
    
    # Print comparison
    print("\nSimulation Results Comparison:")
    print("-" * 80)
    print(f"{'Metric':<30} {'Baseline':<15} {'Social Basic':<15} {'Full SIoT':<15}")
    print("-" * 80)
    
    metrics_to_show = [
        "total_jobs_created",
        "total_jobs_done",
        "jobs_completed_on_time",
        "jobs_completed_late",
        "jobs_failed_deadline",
        "jobs_failed_internal",
        "total_rewards_earned",
        "total_penalties_incurred"
    ]
    
    for metric in metrics_to_show:
        values = [str(results[variant].get(metric, "N/A")) for variant in framework_variants]
        print(f"{metric:<30} {values[0]:<15} {values[1]:<15} {values[2]:<15}")


if __name__ == "__main__":
    main() 