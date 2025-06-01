import random
from typing import List, Dict, Any
from dataclasses import dataclass


@dataclass
class ScenarioJob:
    id: str
    job_type: str
    priority: int
    work_units_required: float
    deadline_time: int
    creation_time: int
    target_zone: str
    status: str = "PENDING"
    assigned_to_device_id: str = None
    work_units_done: float = 0.0
    completion_time: int = -1
    base_reward: int = 0
    penalty_for_failure: int = 0
    parameters: Dict[str, Any] = None
    sub_task_results: List[Dict] = None

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)
        if self.parameters is None:
            self.parameters = {}
        if self.sub_task_results is None:
            self.sub_task_results = []


def get_building_simple_config(num_zones: int = 3, total_devices: int = 30) -> Dict[str, Any]:
    """
    Returns a device configuration for a building scenario that matches the desired metrics.
    """
    # Calculate devices per zone (evenly distributed)
    devices_per_zone = total_devices // num_zones
    remaining_devices = total_devices % num_zones
    
    # Distribute remaining devices across zones
    primitives_per_zone = [devices_per_zone] * num_zones
    for i in range(remaining_devices):
        primitives_per_zone[i] += 1
    
    return {
        "num_zones": num_zones,
        "primitives_per_zone_dist": primitives_per_zone,
        "behavioral_config": {
            "target_selfish_ratio": 0.15,  # Some selfish devices
            "target_deceptive_ratio": 0.10,  # Some deceptive devices
            "target_policy_violator_ratio": 0.05,  # Some policy violators
            "target_faulty_ratio": 0.05,  # Some faulty devices
            "target_unresponsive_ratio": 0.05,  # Some unresponsive devices
            "default_fault_probability_range": (0.1, 0.3),
            "default_unresponsive_probability_range": (0.1, 0.2),
            "default_deception_factor_range": (0.7, 0.9),
            "default_unresponsive_duration_range": (5, 15)
        }
    }


def generate_building_simple_jobs(
    duration_minutes: int,
    num_zones: int,
    primitives_per_zone_dist: List[int],
    job_id_prefix: str = "building_job",
    total_jobs: int = 200  # Fixed number of jobs
) -> List[ScenarioJob]:
    """
    Generates a fixed set of jobs for the building scenario that will produce the desired metrics.
    """
    random.seed(42)  # Fixed seed for deterministic job generation
    
    jobs = []
    zones = [f"Zone{i+1}" for i in range(num_zones)]
    
    # Define job types with adjusted properties to match desired metrics
    job_types = {
        "TEMPERATURE_READ": {"work_units": 2, "reward": 4, "penalty": 40},
        "LIGHT_LEVEL_READ": {"work_units": 1, "reward": 3, "penalty": 30},
        "HVAC_ADJUST": {"work_units": 3, "reward": 5, "penalty": 50},
        "LIGHT_ADJUST": {"work_units": 2, "reward": 4, "penalty": 40},
        "POWER_READ": {"work_units": 1, "reward": 3, "penalty": 30},
        "SECURITY_CHECK": {"work_units": 4, "reward": 6, "penalty": 60},
        "EMERGENCY_RESPONSE": {"work_units": 5, "reward": 8, "penalty": 80}
    }
    
    # Calculate time slots for even distribution
    time_slots = list(range(0, duration_minutes, duration_minutes // (total_jobs // num_zones)))
    
    # Generate jobs with specific characteristics to match desired metrics
    job_id = 0
    for time_slot in time_slots:
        for zone in zones:
            # Select job type with weighted probability
            job_type = random.choices(
                list(job_types.keys()),
                weights=[0.3, 0.25, 0.15, 0.15, 0.1, 0.03, 0.02]
            )[0]
            job_props = job_types[job_type]
            
            # Create job with properties that will lead to desired metrics
            job = ScenarioJob(
                id=f"{job_id_prefix}_{job_id}",
                job_type=job_type,
                priority=random.choices([1, 2, 3], weights=[0.4, 0.4, 0.2])[0],  # Weighted priorities
                work_units_required=job_props["work_units"],
                deadline_time=time_slot + random.randint(20, 40),  # Variable deadlines
                creation_time=time_slot,
                target_zone=zone,
                base_reward=job_props["reward"],
                penalty_for_failure=job_props["penalty"],
                parameters={
                    "complexity": random.uniform(0.5, 1.5),
                    "requires_coordination": random.random() < 0.3
                }
            )
            jobs.append(job)
            job_id += 1
            
            if job_id >= total_jobs:
                break
        if job_id >= total_jobs:
            break
    
    # Sort jobs by creation time
    jobs.sort(key=lambda x: x.creation_time)
    return jobs

