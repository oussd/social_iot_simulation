import os
from src.simulations.building_scenario_config import save_scenario_to_json
from src.run_scenario_simulation import create_sample_scenario, run_simulation


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
