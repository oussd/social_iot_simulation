import random
from typing import List, Dict, Any, Optional

# This Job class should mirror the structure of BuildingJob used in your simulations
# if BuildingJob is defined elsewhere and accessible, prefer importing it.
class ScenarioJob:
    def __init__(self, job_id: str, creation_time: int, job_type: str,
                 target_zone: Optional[str], work_units_required: int,
                 deadline_time: int, base_reward: int,
                 parameters: Optional[Dict[str, Any]] = None, penalty_multiplier: float = 1.5,
                 priority: int = 2):
        self.id = job_id
        self.creation_time = creation_time # Minute the job becomes available
        self.job_type = job_type
        self.target_zone = target_zone
        self.parameters = parameters if parameters else {}
        self.work_units_required = work_units_required
        self.deadline_time = deadline_time # Absolute minute for deadline
        self.base_reward = base_reward
        self.priority = priority # Lower number is higher priority
        
        # Attributes typically set/updated by the simulation engine
        self.work_units_done = 0
        self.assigned_to_device_id: Optional[str] = None
        self.status = "PRE_GENERATED" # Initial status
        self.completion_time = -1
        self.penalty_for_failure = int(base_reward * penalty_multiplier)
        self.sub_task_results: List[Dict[str, Any]] = [] # Ensure this is present

    def __repr__(self):
        return (f"Job(id={self.id}, type={self.job_type}, zone={self.target_zone}, prio={self.priority}, "
                f"wu={self.work_units_required}, created_at={self.creation_time} dl={self.deadline_time})")

def get_device_config_for_50_devices() -> Dict[str, Any]:
    """
    Returns a fixed configuration targeting 50 devices for building simulations.
    """
    num_zones = 3
    # 1 BMS + 3 ZCs = 4 control devices. Need 46 primitives for 50 total.
    primitives_per_zone_dist = [16, 15, 15] # 16 + 15 + 15 = 46 primitives
    
    # Configuration for assigning behavioral profiles (used by V2 and V3 simulations)
    behavioral_config = {
        'target_selfish_ratio': 0.10,       # 10% of devices to be selfish
        'target_deceptive_ratio': 0.10,     # 10% to be deceptive
        'target_policy_violator_ratio': 0.05, # 5% to be policy violators
        'target_faulty_ratio': 0.15,        # 15% to have a chance of faults
        'target_unresponsive_ratio': 0.10,  # 10% to have a chance of becoming unresponsive
        'default_fault_probability_range': (0.05, 0.20), # Min/max fault chance if faulty
        'default_unresponsive_probability_range': (0.02, 0.10), # Min/max unresp. chance if unresponsive
        'default_deception_factor_range': (0.4, 0.7), # How much worse deceptive devices perform
        'default_unresponsive_duration_range': (5, 15) # Min/max duration of unresponsiveness
    }

    return {
        "num_zones": num_zones,
        "primitives_per_zone_dist": primitives_per_zone_dist, # e.g. [16, 15, 15]
        "behavioral_config": behavioral_config, # Rules for assigning misbehaviors
        "total_target_devices": 1 + num_zones + sum(primitives_per_zone_dist) # Should be 50
    }

def generate_building_job_list(
    duration_minutes: int,
    num_zones: int, # From device_config
    primitives_per_zone_dist: List[int], # From device_config
    job_id_prefix: str = "pregen_bldg_job",
    # Allow passing job generation parameters for more control if needed
    scheduled_job_interval_hvac: int = 10, # Every 10 min for HVAC (was sched_interval // 2 with 20)
    hvac_job_chance: float = 0.5,
    access_event_chance_per_min: float = 0.25,
    access_attempts_per_event_max_zones_div: int = 2,
    sudden_influx_interval_div: int = 5, # Triggers every duration/5 minutes
    sudden_influx_trigger_chance: float = 0.75,
    sudden_influx_job_multiplier: float = 1.5,
    energy_job_interval: int = 20,
    energy_job_chance: float = 0.45
    ) -> List[ScenarioJob]:
    """
    Generates a deterministic list of all jobs for the entire simulation duration.
    The random seed MUST be set externally ONCE before calling this function.
    """
    all_jobs: List[ScenarioJob] = []
    next_job_id_counter = 0
    
    zones_list = [f"Zone{i+1}" for i in range(num_zones)]
    avg_primitives_per_zone = sum(primitives_per_zone_dist) / num_zones if num_zones > 0 else 3 # For scaling sudden influx

    for current_minute in range(duration_minutes):
        # 1. HVAC_ADJUST Jobs
        if current_minute % scheduled_job_interval_hvac == 0:
            for zone_name in zones_list:
                if random.random() < hvac_job_chance: 
                    job_type = "HVAC_ADJUST"
                    target_temp = random.randint(19, 24)
                    current_temp_sim = target_temp + random.randint(-4, 4) 
                    params = {'target_temp': target_temp, 'current_temp_simulated': current_temp_sim, 'reason': "Scheduled Comfort"}
                    work = random.randint(8, 15) 
                    deadline = current_minute + random.randint(work + 5, work + 25) 
                    reward = work * 8 + (25 - abs(target_temp - 21)*3) 
                    priority = 2 
                    if random.random() < 0.25: priority = 1 
                    next_job_id_counter += 1
                    job = ScenarioJob(f"{job_id_prefix}_{next_job_id_counter}", current_minute, job_type, zone_name, work, deadline, int(reward), params, priority=priority)
                    all_jobs.append(job)

        # 2. ACCESS_REQUEST Jobs
        if random.random() < access_event_chance_per_min : 
            num_access_attempts = random.randint(1, max(2, num_zones // access_attempts_per_event_max_zones_div if access_attempts_per_event_max_zones_div > 0 else 2 ) + 1)
            for _ in range(num_access_attempts):
                target_zone_for_access = random.choice(zones_list)
                job_type = "ACCESS_REQUEST"
                user_id = f"user{random.randint(101,150)}" 
                params = {'user_id': user_id, 'door_id': f"Door_{target_zone_for_access}_MainEntry", 'access_level_required': random.randint(1,3)}
                work = random.randint(3,6) 
                deadline = current_minute + random.randint(2, 4) 
                reward = work * 7
                priority = 1 
                next_job_id_counter += 1
                job = ScenarioJob(f"{job_id_prefix}_{next_job_id_counter}", current_minute, job_type, target_zone_for_access, work, deadline, reward, params, priority=priority)
                all_jobs.append(job)

        # 3. Sudden INFLUX of ACCESS_REQUEST jobs
        if current_minute > 0 and current_minute % (duration_minutes // sudden_influx_interval_div if duration_minutes >= sudden_influx_interval_div else 1) == 0 and random.random() < sudden_influx_trigger_chance: 
            influx_zone = random.choice(zones_list)
            num_influx = random.randint(int(max(3,avg_primitives_per_zone) * sudden_influx_job_multiplier),
                                        int(max(4,avg_primitives_per_zone * 2) * sudden_influx_job_multiplier))
            for i in range(num_influx):
                next_job_id_counter += 1
                job = ScenarioJob(f"{job_id_prefix}_{next_job_id_counter}", current_minute, "ACCESS_REQUEST", influx_zone,
                                  random.randint(2,4), current_minute + 1 + i//4, # Staggered tight deadlines
                                  10, {'user_id': f"influx_user{i}", 'door_id': f"Door_{influx_zone}_Entry{i%2+1}"}, priority=1)
                all_jobs.append(job)
        
        # 4. Energy Management Jobs
        if current_minute > 0 and current_minute % energy_job_interval == 0: 
            if random.random() < energy_job_chance: 
                target_zone_name_or_none = random.choice(zones_list + [None]) 
                job_type = "OPTIMIZE_ZONE_ENERGY" if target_zone_name_or_none else "BUILDING_ENERGY_STRATEGY"
                params = {'reason': "Scheduled Review"}
                if target_zone_name_or_none and random.random() < 0.6:
                    params['target_reduction_kwh_simulated'] = random.uniform(0.5, 2.0) 
                elif not target_zone_name_or_none: 
                    params['mode'] = random.choice(["PEAK_DEMAND_AVOIDANCE", "NIGHT_SETBACK", "LOAD_BALANCING"])
                work = random.randint(10, 25) if target_zone_name_or_none else random.randint(15,30) 
                deadline = current_minute + random.randint(work + 10, work + 45) 
                reward = work * 6
                priority = 3 
                next_job_id_counter += 1
                job = ScenarioJob(f"{job_id_prefix}_{next_job_id_counter}", current_minute, job_type, target_zone_name_or_none, work, deadline, reward, params, priority=priority)
                all_jobs.append(job)

    all_jobs.sort(key=lambda j: (j.creation_time, j.priority, j.deadline_time))
    return all_jobs

