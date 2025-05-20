import random
import time
import uuid # For unique job IDs
from collections import deque # For job queue
from typing import List, Dict, Any, Optional

# Assuming these are in ..devices.device (adjust path if needed)
# We will modify Device.py and CompositeDevice.py separately, 
# but for now, this simulation file will assume they have a 'framework_variant' attribute
# and their handle_request methods might behave differently based on it.
from ..devices.device import Device, QoELevel 
from ..devices.sensing_device import SensingDevice
from ..devices.actuating_device import ActuatingDevice
from ..devices.communicating_device import CommunicatingDevice
from ..devices.composite_device import CompositeDevice 
# Ensure your logger is correctly imported
from ..utils.logger import SimulationLogger 

# --- New/Enhanced Device Types (from previous step) ---
class CardReaderSensor(SensingDevice):
    def __init__(self, device_id, name, max_load=50, framework_variant="full_siot"): # Add framework_variant
        super().__init__(device_id, name, max_load, sensor_type="card_swipe", framework_variant=framework_variant)
        self.access_log = []
        self.current_minute_provider = None # To be set by simulation for self.current_minute

    def _perform_sense_action(self, expected_load_for_task):
        action_start_time = time.time()
        action_load_cost = int(expected_load_for_task * random.uniform(0.8, 1.2))
        
        if not self.consume_load(action_load_cost):
            return {'success': False, 'reason': 'overload_at_action', 'load_consumed': 0, 'processing_time_ms': (time.time() - action_start_time) * 1000}

        time.sleep(random.uniform(0.005, 0.02)) 
        card_data = f"card_data_{random.randint(1000,9999)}_user{random.randint(1,10)}"
        
        current_sim_minute = self.current_minute_provider() if self.current_minute_provider else -1
        self.access_log.append({'time': current_sim_minute, 'card': card_data})
        
        processing_time_ms = (time.time() - action_start_time) * 1000
        self.log_event(f"Card swipe detected: {card_data} in {processing_time_ms:.0f}ms, Load: {action_load_cost}")
        return {
            'success': True, 'value': card_data, 'load_consumed': action_load_cost,
            'processing_time_ms': processing_time_ms, 'data_accuracy_measured': 1.0 
        }

class PowerMeterSensor(SensingDevice):
    def __init__(self, device_id, name, max_load=50, zone_name="", framework_variant="full_siot"): # Add framework_variant
        super().__init__(device_id, name, max_load, sensor_type="power_usage", framework_variant=framework_variant)
        self.current_power_draw_kw = random.uniform(0.5, 5.0) 
        self.zone_name = zone_name

    def _perform_sense_action(self, expected_load_for_task):
        action_start_time = time.time()
        action_load_cost = int(expected_load_for_task * random.uniform(0.8, 1.2))
        if not self.consume_load(action_load_cost):
            return {'success': False, 'reason': 'overload_at_action', 'load_consumed': 0, 'processing_time_ms': (time.time() - action_start_time) * 1000}
        
        self.current_power_draw_kw += random.uniform(-0.2, 0.2)
        self.current_power_draw_kw = max(0.1, self.current_power_draw_kw) 
        time.sleep(random.uniform(0.005, 0.01))
        processing_time_ms = (time.time() - action_start_time) * 1000
        self.log_event(f"Power usage for {self.zone_name}: {self.current_power_draw_kw:.2f} kW")
        return {
            'success': True, 'value': self.current_power_draw_kw, 'load_consumed': action_load_cost,
            'processing_time_ms': processing_time_ms, 'data_accuracy_measured': random.uniform(0.98, 1.0)
        }

class SmartPlugActuator(ActuatingDevice):
    def __init__(self, device_id, name, max_load=30, framework_variant="full_siot"): # Add framework_variant
        super().__init__(device_id, name, max_load, actuator_type="smart_plug", framework_variant=framework_variant)
        self.current_state = "ON" 


# Enhanced Job structure (remains mostly the same as defined in previous step)
class BuildingJob:
    def __init__(self, job_id: str, creation_time: int, job_type: str, 
                 target_zone: Optional[str], work_units_required: int, 
                 deadline_time: int, base_reward: int, 
                 parameters: Optional[Dict[str, Any]] = None, penalty_multiplier: float = 1.5,
                 priority: int = 2):
        self.id = job_id
        self.creation_time = creation_time
        self.job_type = job_type 
        self.target_zone = target_zone 
        self.parameters = parameters if parameters else {} 
        self.work_units_required = work_units_required 
        self.work_units_done = 0
        self.deadline_time = deadline_time 
        self.assigned_to_device_id = None 
        self.status = "PENDING" 
        self.completion_time = -1
        self.base_reward = base_reward
        self.penalty_for_failure = int(base_reward * penalty_multiplier)
        self.priority = priority
        self.sub_task_results = [] 

    def __repr__(self):
        return (f"Job(id={self.id}, type={self.job_type}, zone={self.target_zone}, prio={self.priority}, "
                f"wu={self.work_units_done}/{self.work_units_required}, "
                f"dl={self.deadline_time}, status={self.status}, assigned_to={self.assigned_to_device_id})")

class BuildingSimulation:
    def __init__(self, framework_variant: str = "full_siot", 
                 num_zones=2, devices_per_zone_avg=3, 
                 duration_minutes=240, logger_instance=None, run_context_name: str = "BldgSimRun"):
        
        self.framework_variant = framework_variant 
        self.num_zones = num_zones
        self.devices_per_zone_avg = devices_per_zone_avg
        self.num_devices_approx = (num_zones * devices_per_zone_avg) + num_zones + 1 
        
        self.devices: List[Device] = []
        self.zone_controllers: Dict[str, CompositeDevice] = {}
        self.bms: Optional[CompositeDevice] = None
        self.zones: List[str] = [f"Zone{i+1}" for i in range(num_zones)]

        self.time_frame = duration_minutes 
        self.run_context_name = run_context_name 
        
        if logger_instance:
            self.logger = logger_instance
        else:
            self.logger = SimulationLogger(simulation_name=run_context_name) 
        
        self.current_minute = 0

        self.job_queue = deque()
        self.active_jobs: Dict[str, BuildingJob] = {} 
        self.processed_jobs: List[BuildingJob] = [] 
        self.next_job_id_counter = 0
        
        self.scheduled_job_interval = 30 
        self.event_trigger_chance = 0.15 
        self.sudden_workload_chance = 0.05 

        self.metrics = {
            'framework_variant': framework_variant,
            'jobs_generated': 0, 'jobs_assigned':0, 'jobs_completed_on_time': 0,
            'jobs_completed_late': 0, 'jobs_failed_deadline': 0, 'jobs_failed_internal': 0,
            'total_work_units_processed': 0, 'avg_job_completion_time': 0, 'avg_job_tardiness': 0,
            'device_cycles_working': {}, 'device_cycles_idle': {},
            'total_rewards_earned': 0, 'total_penalties_incurred': 0,
            'qoe_interaction_samples': [], 'avg_trust_at_end': "N/A", 
            'final_total_balance_network': 0, 'total_income_generated_network': 0,
            'min_income_check_interval': duration_minutes // 4 if duration_minutes >= 40 else 10,
            'delegation_to_zone_controller_count': 0,
            'delegation_to_primitive_count': 0, 
            'successful_negotiations': 0, 'failed_negotiations': 0,    
            'misuse_incidents_detected': 0, 
            'back_me_invocations_successful': 0, 'back_me_invocations_failed': 0,
        }
        self.logger.log_info("SIM_INIT", f"Building Simulation ({self.framework_variant}) | Devices: approx {self.num_devices_approx} | Zones: {num_zones} | Duration: {self.time_frame}m", 
                             context_override=self.run_context_name)

    def _get_next_job_id(self):
        self.next_job_id_counter += 1
        return f"bldg_job_{self.next_job_id_counter}"

    def _get_device_by_id(self, device_id: Optional[str]) -> Optional[Device]:
        if not device_id: return None
        for dev in self.devices:
            if dev.device_id == device_id:
                return dev
        return None

    def setup_devices(self):
        dev_id_counter = 0
        base_starting_balance = 1000
        min_income_per_period = self.metrics.get('min_income_check_interval', 60) * 0.5

        # 1. Create BMS
        bms_id = f"bldg_bms_{dev_id_counter}"; dev_id_counter+=1
        self.bms = CompositeDevice(bms_id, "CentralBMS", max_load=500, 
                                   capabilities=["coordinate_zones", "set_global_policy", "emergency_response", "energy_management", "assign_global_jobs"],
                                   framework_variant=self.framework_variant) # Pass variant
        self.bms.balance = base_starting_balance * 2
        self.bms.min_acceptable_income_threshold = min_income_per_period * 2
        self.devices.append(self.bms)
        self.logger.log_info("DEV_SETUP", f"Created {self.bms.nameShort()}", context_override=self.run_context_name)

        # 2. Create Zone Controllers and Devices per Zone
        for zone_idx, zone_name in enumerate(self.zones):
            zc_id = f"bldg_zc{zone_idx+1}_{dev_id_counter}"; dev_id_counter+=1
            zone_controller = CompositeDevice(zc_id, f"ZoneCtrl_{zone_name}", max_load=200,
                                              capabilities=["manage_hvac", "manage_lighting", "zone_security_local", "delegate_zone_tasks", "access_control_zone"],
                                              framework_variant=self.framework_variant) # Pass variant
            setattr(zone_controller, 'zone', zone_name) 
            zone_controller.balance = base_starting_balance * 1.5
            zone_controller.min_acceptable_income_threshold = min_income_per_period * 1.5
            self.devices.append(zone_controller)
            self.zone_controllers[zone_name] = zone_controller
            self.logger.log_info("DEV_SETUP", f"Created {zone_controller.nameShort()} for {zone_name}", context_override=self.run_context_name)

            if self.framework_variant in ["social_basic", "full_siot"] and self.bms:
                self.bms.add_worker(zone_controller, constraints={'role': 'zone_management', 'zone': zone_name}) 
                # self.logger.log_info("REL_SETUP", f"{self.bms.nameShort()} now controls {zone_controller.nameShort()}", context_override=self.run_context_name)

            num_primitives_this_zone = random.randint(max(1, self.devices_per_zone_avg -1), self.devices_per_zone_avg + 1)
            for i in range(num_primitives_this_zone):
                dev_id = f"bldg_d{dev_id_counter}_{zone_name[:2].lower()}{i}"; dev_id_counter+=1
                dev_type_roll = random.random()
                primitive_device: Optional[Device] = None

                if dev_type_roll < 0.4: 
                    sensor_kind = random.choice(["temperature", "occupancy", "light_level", "co2", "door_contact", "window_contact", "power_meter", "card_reader"])
                    if sensor_kind == "card_reader":
                        primitive_device = CardReaderSensor(dev_id, f"CardReader_{zone_name}_{i+1}", framework_variant=self.framework_variant)
                        # Pass a lambda to provide current_minute to the device for its internal logging if needed
                        setattr(primitive_device, 'current_minute_provider', lambda: self.current_minute) 
                    elif sensor_kind == "power_meter":
                        primitive_device = PowerMeterSensor(dev_id, f"PowerMeter_{zone_name}_{i+1}", zone_name=zone_name, framework_variant=self.framework_variant)
                    else:
                        primitive_device = SensingDevice(dev_id, f"{sensor_kind.capitalize()}Sens_{zone_name}_{i+1}", sensor_type=sensor_kind, framework_variant=self.framework_variant)
                elif dev_type_roll < 0.8: 
                    actuator_kind = random.choice(["hvac_control", "light_switch", "smart_blind", "door_lock", "smart_plug", "alarm_siren"])
                    if actuator_kind == "smart_plug":
                        primitive_device = SmartPlugActuator(dev_id, f"SmartPlug_{zone_name}_{i+1}", framework_variant=self.framework_variant)
                    else:
                        primitive_device = ActuatingDevice(dev_id, f"{actuator_kind.capitalize()}Act_{zone_name}_{i+1}", actuator_type=actuator_kind, framework_variant=self.framework_variant)
                else: 
                    primitive_device = CommunicatingDevice(dev_id, f"CommRelay_{zone_name}_{i+1}", framework_variant=self.framework_variant)
                
                if primitive_device:
                    setattr(primitive_device, 'zone', zone_name) 
                    primitive_device.balance = base_starting_balance + random.randint(-200, 50)
                    primitive_device.min_acceptable_income_threshold = min_income_per_period
                    self.devices.append(primitive_device)
                    if self.framework_variant in ["social_basic", "full_siot"]:
                        zone_controller.add_worker(primitive_device, constraints={'role': f'{primitive_device.__class__.__name__}_in_{zone_name}'})
        
        actual_device_count = len(self.devices)
        self.metrics['device_cycles_working'] = {dev.device_id: 0 for dev in self.devices}
        self.metrics['device_cycles_idle'] = {dev.device_id: 0 for dev in self.devices}

        if self.framework_variant in ["social_basic", "full_siot"]:
            all_composites = ([self.bms] if self.bms else []) + list(self.zone_controllers.values())
            for i in range(len(all_composites)):
                for j in range(i + 1, len(all_composites)):
                    if random.random() < 0.5: 
                        all_composites[i].add_relationship('work_with_me', all_composites[j])
                        all_composites[j].add_relationship('work_with_me', all_composites[i])
            
            for dev in self.devices: 
                if isinstance(dev, (SensingDevice, ActuatingDevice)) and random.random() < 0.3: # Only some devices get backups
                    dev_zone = getattr(dev, 'zone', None)
                    if dev_zone:
                        potential_backups = [d for d in self.devices if d != dev and getattr(d, 'zone', None) == dev_zone and type(d) == type(dev) and d.device_id != dev.device_id]
                        if potential_backups:
                            backup_dev = random.choice(potential_backups)
                            dev.add_relationship('back_me', backup_dev)
        
        self.logger.log_info("DEV_SETUP_COMPLETE", f"Total devices created: {actual_device_count}. Framework: {self.framework_variant}", context_override=self.run_context_name)

    def _generate_jobs(self):
        # ... (Job generation logic from previous step, ensuring BuildingJob is used) ...
        # 1. Temperature Control / HVAC Jobs
        if self.current_minute % (self.scheduled_job_interval // 2) == 0 : 
            for zone in self.zones:
                if random.random() < 0.4: 
                    job_type = "HVAC_ADJUST"
                    target_temp = random.randint(19, 24)
                    current_temp_sim = target_temp + random.randint(-3, 3) 
                    params = {'target_temp': target_temp, 'current_temp_simulated': current_temp_sim, 'reason': "Scheduled Comfort/Occupancy"}
                    if random.random() < 0.2: params['priority_override'] = 1 
                    
                    work = random.randint(5, 10) 
                    deadline = self.current_minute + random.randint(15, 45) 
                    reward = work * 7 + (25 - abs(target_temp - 21)*2) # Reward higher for ideal temps
                    priority = params.get('priority_override', 2)
                    job = BuildingJob(self._get_next_job_id(), self.current_minute, job_type, zone, work, deadline, int(reward), params, priority=priority)
                    self.job_queue.append(job)
                    self.metrics['jobs_generated'] += 1

        # 2. Access Control Jobs
        if random.random() < self.event_trigger_chance * 1.5 : # Access events are fairly frequent
            num_access_attempts = random.randint(1, max(1, self.num_zones // 2)) 
            for _ in range(num_access_attempts):
                target_zone_for_access = random.choice(self.zones)
                job_type = "ACCESS_REQUEST"
                user_id = f"user{random.randint(101,120)}"
                params = {'user_id': user_id, 'door_id': f"Door_{target_zone_for_access}_MainEntry", 'access_level_required': random.randint(1,3)}
                work = random.randint(2,4) # Verify credential, log, unlock
                deadline = self.current_minute + 3 # Access should be very quick
                reward = work * 6 
                priority = 1 
                job = BuildingJob(self._get_next_job_id(), self.current_minute, job_type, target_zone_for_access, work, deadline, reward, params, priority=priority)
                self.job_queue.append(job)
                self.metrics['jobs_generated'] += 1
        
        # Simulate sudden influx for access control
        if self.current_minute > 0 and self.current_minute % (self.time_frame // 4) == 0 and random.random() < 0.6: # More frequent influx
            influx_zone = random.choice(self.zones)
            num_influx = random.randint(max(2,self.devices_per_zone_avg), max(3,self.devices_per_zone_avg * 2))
            self.logger.log_info("JOB_GEN_EVENT", f"SUDDEN INFLUX of {num_influx} access requests for {influx_zone}", context_override=self.run_context_name)
            for i in range(num_influx):
                job = BuildingJob(self._get_next_job_id(), self.current_minute, "ACCESS_REQUEST", influx_zone, 
                                  random.randint(1,3), self.current_minute + 1 + i//3, # Very tight, staggered
                                  8, {'user_id': f"influx_user{i}", 'door_id': f"Door_{influx_zone}_Entry{i%2+1}"}, priority=1)
                self.job_queue.append(job)
                self.metrics['jobs_generated'] += 1

        # 3. Energy Management Jobs
        if self.current_minute > 0 and self.current_minute % self.scheduled_job_interval == 0: 
            if random.random() < 0.35: 
                target_zone_energy = random.choice(self.zones + [None]) 
                job_type = "OPTIMIZE_ZONE_ENERGY" if target_zone_energy else "BUILDING_ENERGY_STRATEGY"
                params = {'reason': "Scheduled Review/Optimization"}
                if target_zone_energy and random.random() < 0.5:
                    params['target_reduction_kwh_simulated'] = random.uniform(0.3, 1.5) 
                elif not target_zone_energy: 
                    params['mode'] = random.choice(["PEAK_DEMAND_AVOIDANCE", "NIGHT_SETBACK"])
                
                work = random.randint(6, 18) if target_zone_energy else random.randint(12,25) 
                deadline = self.current_minute + random.randint(25, 60)
                reward = work * 5
                priority = 3 
                job = BuildingJob(self._get_next_job_id(), self.current_minute, job_type, target_zone_energy, work, deadline, reward, params, priority=priority)
                self.job_queue.append(job)
                self.metrics['jobs_generated'] += 1
        
        self.job_queue = deque(sorted(list(self.job_queue), key=lambda j: (j.priority, j.deadline_time)))


    def _assign_jobs_to_devices(self):
        jobs_assigned_this_round_ids = set()

        for job in list(self.job_queue): 
            if job.id in jobs_assigned_this_round_ids or job.status != "PENDING":
                continue

            assigned_entity: Optional[Device] = None
            
            # --- Framework ENABLED Scenarios: Hierarchical Assignment ---
            if self.framework_variant in ["social_basic", "full_siot"]:
                if job.target_zone is None and self.bms: # Building-wide job -> BMS
                    # BMS should be less likely to take on too many direct jobs if it's a coordinator
                    if not getattr(self.bms, 'current_job_id', None) and self.bms.current_load < self.bms.max_load * 0.6:
                        assigned_entity = self.bms
                elif job.target_zone in self.zone_controllers:
                    zc = self.zone_controllers[job.target_zone]
                    if not getattr(zc, 'current_job_id', None) and zc.current_load < zc.max_load * 0.7:
                        assigned_entity = zc
                # If no controller is free/suitable, job remains pending for now.
                # More advanced: BMS/ZC could try to find backup controllers or negotiate.
            
            # --- Framework DISABLED (Baseline): Direct to best-guess primitive/composite in zone ---
            else: # baseline
                candidate_devices_in_zone = [
                    d for d in self.devices 
                    if (job.target_zone is None or getattr(d,'zone', None) == job.target_zone) and
                       not getattr(d, 'current_job_id', None) and 
                       d.current_load < d.max_load * 0.85 # Baseline devices might take more load before refusing
                ]
                if not candidate_devices_in_zone and job.target_zone is not None: # If no device in zone, try any device (less realistic)
                    candidate_devices_in_zone = [d for d in self.devices if not getattr(d, 'current_job_id', None) and d.current_load < d.max_load * 0.85]


                if candidate_devices_in_zone:
                    # Simple capability matching for baseline (can be improved)
                    # This logic needs to be robust and consider device types correctly
                    suitable_devices = []
                    if "HVAC" in job.job_type or "TEMP" in job.job_type:
                        suitable_devices = [d for d in candidate_devices_in_zone if (isinstance(d, ActuatingDevice) and "hvac" in d.actuator_type) or (isinstance(d, SensingDevice) and "temp" in d.sensor_type) or (isinstance(d, CompositeDevice) and "hvac" in d.capabilities)]
                    elif "LIGHT" in job.job_type:
                         suitable_devices = [d for d in candidate_devices_in_zone if (isinstance(d, ActuatingDevice) and "light" in d.actuator_type) or (isinstance(d, SensingDevice) and "light" in d.sensor_type) or (isinstance(d, CompositeDevice) and "light" in d.capabilities)]
                    elif "ACCESS" in job.job_type:
                         suitable_devices = [d for d in candidate_devices_in_zone if isinstance(d, CardReaderSensor) or (isinstance(d, ActuatingDevice) and "door_lock" in d.actuator_type) or (isinstance(d, CompositeDevice) and "access" in d.capabilities)]
                    elif "ENERGY" in job.job_type:
                         suitable_devices = [d for d in candidate_devices_in_zone if isinstance(d, PowerMeterSensor) or isinstance(d, SmartPlugActuator) or (isinstance(d, CompositeDevice) and "energy" in d.capabilities)]
                    
                    if not suitable_devices: suitable_devices = candidate_devices_in_zone # Fallback

                    if suitable_devices:
                        # In baseline, maybe pick the least loaded one
                        assigned_entity = min(suitable_devices, key=lambda d: d.current_load) 
            
            if assigned_entity:
                job.assigned_to_device_id = assigned_entity.device_id
                job.status = "ASSIGNED"
                setattr(assigned_entity, 'current_job_id', job.id) 
                self.metrics['jobs_assigned'] += 1
                self.active_jobs[job.id] = job 
                if job in self.job_queue: self.job_queue.remove(job)
                jobs_assigned_this_round_ids.add(job.id)
                self.logger.log_info("JOB_ASSIGN", f"Job {job.id} ({job.job_type} for {job.target_zone if job.target_zone else 'BUILDING'}) assigned to {assigned_entity.nameShort()}", context_override=self.run_context_name)
        
        self.job_queue = deque(sorted(list(self.job_queue), key=lambda j: (j.priority, j.deadline_time)))


    def _process_device_job(self, device: Device, job: BuildingJob):
        """
        Simulates one cycle of a device working on its assigned job.
        This is where the job's "work_units" translate into device actions.
        This method will become the core differentiator between framework variants.
        """
        if device.current_load >= device.max_load * 0.95: # Device is too overloaded to work
            self.logger.log_info("JOB_PROGRESS", f"Device {device.nameShort()} on Job {job.id} is CRITICALLY OVERLOADED, no progress.", context_override=self.run_context_name)
            self.metrics['device_cycles_idle'][device.device_id] +=1
            return

        # Abstract load consumption for working on the job's main coordination/execution
        # Primitive devices might consume less, composites more for coordination.
        base_work_load = 10 if isinstance(device, CompositeDevice) else 5
        if not device.consume_load(base_work_load):
            self.logger.log_info("JOB_PROGRESS", f"Device {device.nameShort()} on Job {job.id} FAILED to consume its base work load.", context_override=self.run_context_name)
            self.metrics['device_cycles_idle'][device.device_id] +=1
            return

        work_units_completed_this_cycle = 0
        job_failed_internally_this_cycle = False

        # --- Framework-Specific Job Processing Logic ---
        if self.framework_variant == "baseline":
            # Device attempts to do 1 WU. If job needs coordination it can't do, it might get stuck.
            # For complex jobs, it's likely to make slow progress or fail if it's not a capable Composite.
            if isinstance(device, CompositeDevice) and job.work_units_required > 3: # Composite might do a bit more
                work_units_completed_this_cycle = random.uniform(0.5, 1.0) # Slower progress
            else:
                work_units_completed_this_cycle = 1.0 # Primitive or simple composite job
            # No sophisticated delegation, trust, or negotiation.

        elif self.framework_variant == "social_basic" or self.framework_variant == "full_siot":
            if isinstance(device, CompositeDevice): # BMS or Zone Controller
                # This CompositeDevice needs to delegate sub-tasks to its workers or collaborate.
                # This is a placeholder for the detailed logic that would make handle_request calls.
                # For now, simulate that it successfully coordinates some work based on its "social ability".
                
                # Example: HVAC_ADJUST job for a ZoneController
                if job.job_type == "HVAC_ADJUST" and hasattr(device, 'zone'):
                    # 1. Find a temperature sensor worker
                    temp_sensors = [w_rel['device'] for w_rel in device.relationships.get('controller_for', []) 
                                    if isinstance(w_rel['device'], SensingDevice) and 'temp' in w_rel['device'].sensor_type]
                    # 2. Find an HVAC actuator worker
                    hvac_actuators = [w_rel['device'] for w_rel in device.relationships.get('controller_for', [])
                                      if isinstance(w_rel['device'], ActuatingDevice) and 'hvac' in w_rel['device'].actuator_type]

                    if temp_sensors and hvac_actuators:
                        # Select based on trust if framework is ON (simplified: pick first for now)
                        # In full_siot, negotiation with sensor/actuator would occur here.
                        sensor = device.select_worker_for_task(temp_sensors, "sense_temperature") # New method needed in Composite
                        actuator = device.select_worker_for_task(hvac_actuators, "actuate_hvac") # New method

                        if sensor and actuator:
                            self.metrics['delegation_to_primitive_count'] += 2 # Count delegations
                            # Simulate sensing
                            sense_details = {'iot_app_reward': 0} # Sub-task, no direct job reward
                            sense_outcome = sensor.handle_request(device, 'sense', load_requested=5, details=sense_details)
                            device.update_trust_from_qoe(sensor, 'sense', sense_outcome['measured_qos_for_requestor'], "requester")
                            job.sub_task_results.append({'sensor_outcome': sense_outcome})

                            if sense_outcome.get('success'):
                                current_temp = sense_outcome.get('value', job.parameters.get('current_temp_simulated', 25))
                                target_temp = job.parameters.get('target_temp', 22)
                                if abs(current_temp - target_temp) > 0.5:
                                    act_details = {'iot_app_reward': 0, 'command': 'SET_TEMP', 'value': target_temp}
                                    act_outcome = actuator.handle_request(device, 'actuate', load_requested=10, details=act_details)
                                    device.update_trust_from_qoe(actuator, 'actuate', act_outcome['measured_qos_for_requestor'], "requester")
                                    job.sub_task_results.append({'actuator_outcome': act_outcome})
                                    if act_outcome.get('success'): work_units_completed_this_cycle = 1.0 # Successful sub-cycle
                                    else: job_failed_internally_this_cycle = True; self.logger.log_warning("JOB_SUB_FAIL", f"Job {job.id} HVAC actuation failed by {actuator.nameShort()}", context_override=self.run_context_name)
                                else: # Temp is fine
                                    work_units_completed_this_cycle = 1.0 # Considered a successful check
                                    job.sub_task_results.append({'hvac_already_optimal': True})
                            else: # Sensor failed
                                job_failed_internally_this_cycle = True
                                self.logger.log_warning("JOB_SUB_FAIL", f"Job {job.id} HVAC sensing failed by {sensor.nameShort()}", context_override=self.run_context_name)
                                # Try backup for sensor if framework allows
                                if self.framework_variant == "full_siot" and hasattr(sensor, 'relationships') and sensor.relationships.get('back_me'):
                                    # ... (backup logic) ...
                                    pass

                        else: # Could not find/select suitable workers
                             self.logger.log_warning("JOB_SUB_FAIL", f"Composite {device.nameShort()} couldn't select workers for HVAC Job {job.id}", context_override=self.run_context_name)
                             job_failed_internally_this_cycle = True
                    else: # Missing sensor or actuator types under its control
                        self.logger.log_warning("JOB_SUB_FAIL", f"Composite {device.nameShort()} lacks sensor/actuator for HVAC Job {job.id}", context_override=self.run_context_name)
                        job_failed_internally_this_cycle = True
                
                elif job.job_type == "ACCESS_REQUEST" and isinstance(device, CompositeDevice) and hasattr(device, 'zone'): # Likely a ZC
                    # Find CardReader and DoorLock
                    card_readers = [w_rel['device'] for w_rel in device.relationships.get('controller_for', []) if isinstance(w_rel['device'], CardReaderSensor)]
                    door_locks = [w_rel['device'] for w_rel in device.relationships.get('controller_for', []) if isinstance(w_rel['device'], ActuatingDevice) and 'door_lock' in w_rel['device'].actuator_type]

                    if card_readers and door_locks:
                        reader = device.select_worker_for_task(card_readers, "read_card")
                        lock = device.select_worker_for_task(door_locks, "control_lock")

                        if reader and lock:
                            self.metrics['delegation_to_primitive_count'] += 2
                            swipe_outcome = reader.handle_request(device, 'sense', 5, {'simulated_card_user': job.parameters.get('user_id')})
                            device.update_trust_from_qoe(reader, 'sense', swipe_outcome['measured_qos_for_requestor'], "requester")
                            job.sub_task_results.append({'card_swipe': swipe_outcome})

                            if swipe_outcome.get('success'):
                                card_data = swipe_outcome.get('value')
                                # Simplified policy: allow if user_id matches and level is okay
                                access_granted = (job.parameters.get('user_id') in card_data and 
                                                  random.random() < 0.95) # Small chance of policy denial
                                
                                if self.framework_variant == "full_siot": # Negotiation/Policy Check
                                    # ZC might check a central policy via BMS or its own stricter rules
                                    if device.trust_score < 50 and job.parameters.get('access_level_required',1) > 1 : # Example policy
                                        access_granted = False
                                        self.metrics['failed_negotiations'] += 1
                                        self.logger.log_info("ACCESS_POLICY", f"Job {job.id} access denied by ZC policy (low ZC trust, high level req).", context_override=self.run_context_name)


                                if access_granted:
                                    self.logger.log_info("ACCESS_POLICY", f"Job {job.id} access GRANTED for {job.parameters.get('user_id')}.", context_override=self.run_context_name)
                                    unlock_outcome = lock.handle_request(device, 'actuate', 5, {'command': "UNLOCK"})
                                    device.update_trust_from_qoe(lock, 'actuate', unlock_outcome['measured_qos_for_requestor'], "requester")
                                    job.sub_task_results.append({'door_unlock': unlock_outcome})
                                    if unlock_outcome.get('success'): work_units_completed_this_cycle = 1.0
                                    else: job_failed_internally_this_cycle = True
                                else: # Access denied by policy
                                    self.logger.log_info("ACCESS_POLICY", f"Job {job.id} access DENIED for {job.parameters.get('user_id')}.", context_override=self.run_context_name)
                                    job.sub_task_results.append({'access_denied_policy': True})
                                    work_units_completed_this_cycle = 1.0 # Job is "done" by denying access
                            else: job_failed_internally_this_cycle = True # Card read failed
                        else: job_failed_internally_this_cycle = True # Could not select reader/lock
                    else: job_failed_internally_this_cycle = True # Missing reader/lock types
                
                else: # Other job types for Composite or primitive device direct assignment
                    # Fallback to simpler WU completion for now for other job types or if not composite
                    if isinstance(device, CompositeDevice): # If composite, it still "coordinates"
                         work_units_completed_this_cycle = random.uniform(0.7, 1.2) if self.framework_variant != "baseline" else random.uniform(0.5,1.0)
                    else: # Primitive device
                         work_units_completed_this_cycle = 1.0
            
            else: # Should not happen if device.framework_variant is always set
                 work_units_completed_this_cycle = 0.5


            # Misuse detection for "full_siot" (simplified)
            if self.framework_variant == "full_siot" and isinstance(device, CompositeDevice):
                for res in job.sub_task_results:
                    if isinstance(res, dict):
                        for sub_task_key, sub_outcome in res.items():
                            if isinstance(sub_outcome, dict) and sub_outcome.get('success') == False:
                                # If a worker consistently fails or provides very bad QoS for this composite...
                                # (requires tracking history with workers, which is in Device.interaction_history)
                                # For now, just a placeholder.
                                # self.metrics['misuse_incidents_detected'] += 1 
                                pass
            
            job.work_units_done += work_units_completed_this_cycle
            self.metrics['total_work_units_processed'] += work_units_completed_this_cycle
            self.metrics['device_cycles_working'][device.device_id] +=1
            if work_units_completed_this_cycle > 0:
                self.logger.log_info("JOB_PROGRESS", f"{device.nameShort()} on Job {job.id}: {job.work_units_done:.1f}/{job.work_units_required} WU. Load: {device.current_load}", context_override=self.run_context_name)
            elif not job_failed_internally_this_cycle: # No progress but not an internal failure (e.g. waiting)
                self.logger.log_info("JOB_PROGRESS", f"{device.nameShort()} on Job {job.id}: NO PROGRESS this cycle. Load: {device.current_load}", context_override=self.run_context_name)

        else: 
            self.logger.log_info("JOB_PROGRESS", f"Device {device.nameShort()} on Job {job.id} is OVERLOADED (load: {device.current_load}), no progress.", context_override=self.run_context_name)
            self.metrics['device_cycles_idle'][device.device_id] +=1

        # Check job completion/failure
        if job_failed_internally_this_cycle and job.status == "IN_PROGRESS":
            job.status = "FAILED_INTERNAL"
            job.completion_time = self.current_minute
            self.metrics['jobs_failed_internal'] += 1
            # Penalty might be on the composite, or it might penalize a failing worker
            device.receive_penalty(job.penalty_for_failure / 2, "System", f"Job {job.id} failed due to internal sub-task failure.")
            self.metrics['total_penalties_incurred'] += job.penalty_for_failure / 2
            self.logger.log_info("JOB_FAIL", f"Job {job.id} ({job.job_type}) FAILED INTERNALLY on {device.nameShort()}.", context_override=self.run_context_name)
            self.processed_jobs.append(job)
            if job.id in self.active_jobs: del self.active_jobs[job.id]
            setattr(device, 'current_job_id', None)
            return # Stop further processing for this job this cycle

        if job.work_units_done >= job.work_units_required:
            job.completion_time = self.current_minute
            status_log_prefix = f"Job {job.id} ({job.job_type})"
            if self.current_minute <= job.deadline_time:
                job.status = "COMPLETED_ON_TIME"
                self.metrics['jobs_completed_on_time'] += 1
                device.receive_income(job.base_reward, f"{status_log_prefix} on time")
                self.metrics['total_rewards_earned'] += job.base_reward
                self.logger.log_info("JOB_COMPLETE", f"{status_log_prefix} COMPLETED ON TIME by {device.nameShort()}. Reward: {job.base_reward}", context_override=self.run_context_name)
            else:
                job.status = "COMPLETED_LATE"
                self.metrics['jobs_completed_late'] += 1
                reduced_reward = int(job.base_reward * 0.6) 
                device.receive_income(reduced_reward, f"{status_log_prefix} late")
                self.metrics['total_rewards_earned'] += reduced_reward
                self.logger.log_info("JOB_COMPLETE", f"{status_log_prefix} COMPLETED LATE by {device.nameShort()}. Reward: {reduced_reward}", context_override=self.run_context_name)
            
            self.processed_jobs.append(job)
            if job.id in self.active_jobs: del self.active_jobs[job.id]
            setattr(device, 'current_job_id', None) 

        elif self.current_minute > job.deadline_time and job.status == "IN_PROGRESS": # Check deadline miss only if still in progress
            job.status = "FAILED_DEADLINE"
            job.completion_time = self.current_minute 
            self.metrics['jobs_failed_deadline'] += 1
            device.receive_penalty(job.penalty_for_failure, "System", f"Job {job.id} missed deadline")
            self.metrics['total_penalties_incurred'] += job.penalty_for_failure
            self.logger.log_info("JOB_FAIL", f"Job {job.id} ({job.job_type}) FAILED DEADLINE on {device.nameShort()}. Penalty: {job.penalty_for_failure}", context_override=self.run_context_name)
            self.processed_jobs.append(job)
            if job.id in self.active_jobs: del self.active_jobs[job.id]
            setattr(device, 'current_job_id', None)


    def simulate_cycle(self, minute):
        self.current_minute = minute
        self.logger.log_info("CYCLE_START", f"Minute: {self.current_minute} ({self.framework_variant})", context_override=self.run_context_name)
        
        self._generate_jobs()
        self._assign_jobs_to_devices() 

        # random.shuffle(self.devices) # Process in a fixed order for debugging, can re-enable shuffle

        for device in self.devices:
            current_job_id_attr = getattr(device, 'current_job_id', None)
            if current_job_id_attr and current_job_id_attr in self.active_jobs:
                job = self.active_jobs[current_job_id_attr]
                # Ensure job is still assigned to this device and in a processable state
                if job.assigned_to_device_id == device.device_id and job.status in ["ASSIGNED", "IN_PROGRESS"]:
                    if job.status == "ASSIGNED": 
                        job.status = "IN_PROGRESS"
                        self.logger.log_info("JOB_START", f"Device {device.nameShort()} starting Job {job.id} ({job.job_type})", context_override=self.run_context_name)
                    
                    if job.status == "IN_PROGRESS": 
                        self._process_device_job(device, job)
                elif job.assigned_to_device_id != device.device_id and current_job_id_attr == job.id:
                    # Job was reassigned or device still thinks it has it. Clear current_job_id.
                    self.logger.log_warning("STATE_MISMATCH", f"Device {device.nameShort()} thought it had job {job.id}, but job is assigned to {job.assigned_to_device_id}. Clearing.", context_override=self.run_context_name)
                    setattr(device, 'current_job_id', None)

            else: # Device is idle or its job was completed/failed by another logic path
                 if current_job_id_attr and current_job_id_attr not in self.active_jobs:
                     setattr(device, 'current_job_id', None) # Clear stale job ID
                 
                 self.metrics['device_cycles_idle'][device.device_id] +=1
                 # Framework-specific background interactions
                 if self.framework_variant in ["social_basic", "full_siot"] and random.random() < 0.01 and len(self.devices) > 1: # Reduced chance
                    requestor = device
                    potential_targets = [rel['device'] for rel in requestor.relationships.get('work_with_me', []) if rel.get('status')=='active']
                    if not potential_targets: # Fallback to other composites or any non-avoided
                        potential_targets = [d for d in self.devices if d != requestor and isinstance(d, CompositeDevice) and not any(r['device']==requestor for r in d.relationships.get('avoid_me',[]))]
                    if not potential_targets : 
                        potential_targets = [d for d in self.devices if d != requestor and not any(r['device']==requestor for r in d.relationships.get('avoid_me',[]))]

                    if potential_targets:
                        target_performer = random.choice(potential_targets)
                        requested_task = random.choice(['sense', 'transmit']) 
                        load_for_task = random.randint(2,5)
                        details = {'iot_app_reward': 0, 'message': f"Bldg coord ping from {requestor.nameShort()}", 'is_background_task': True}
                        if requested_task == 'transmit': details['target_comm_device'] = target_performer 

                        outcome = target_performer.handle_request(requestor, requested_task, load_for_task, details)
                        if 'measured_qos_for_requestor' in outcome: 
                            requestor.update_trust_from_qoe(target_performer, requested_task, outcome['measured_qos_for_requestor'], "requester")
                            # if outcome.get('success'): 
                                # self.logger.log_info("SIM_INTERACTION", f"{requestor.nameShort()} successful background '{requested_task}' with {target_performer.nameShort()}", context_override=self.run_context_name)

            device.reduce_load(random.randint(3,8)) # Slightly less reduction to show load impact
            if self.current_minute > 0 and self.current_minute % self.metrics['min_income_check_interval'] == 0:
                device.check_min_income_satisfied()

        # Cleanup PENDING jobs in main queue that missed deadline
        for job in list(self.job_queue): 
            if job.status == "PENDING" and self.current_minute > job.deadline_time:
                job.status = "FAILED_DEADLINE_UNASSIGNED"
                self.metrics['jobs_failed_deadline'] += 1
                self.logger.log_info("JOB_FAIL_QUEUE", f"Job {job.id} ({job.job_type}) FAILED DEADLINE (unassigned from queue).", context_override=self.run_context_name)
                self.processed_jobs.append(job)
                if job in self.job_queue: self.job_queue.remove(job)

        self.logger.log_info("CYCLE_END", f"Minute: {self.current_minute} | Pending Jobs: {len(self.job_queue)} | Active Jobs: {len(self.active_jobs)}", context_override=self.run_context_name)


    def run(self):
        self.setup_devices()
        for minute_cycle in range(self.time_frame):
            self.simulate_cycle(minute_cycle)
            if minute_cycle > 0 and (minute_cycle % (self.time_frame // 20 if self.time_frame >=20 else 1) == 0 or minute_cycle == self.time_frame -1) : # More frequent summary
                 self.logger.log_info("PERIODIC_SUM", f"Min {minute_cycle} | Jobs (Pend/Act/Fail): {len(self.job_queue)}/{len(self.active_jobs)}/{sum(1 for j in self.processed_jobs if 'FAIL' in j.status)} | Comp(OK/Late):{self.metrics['jobs_completed_on_time']}/{self.metrics['jobs_completed_late']}", context_override=self.run_context_name)
        self.report()

    def report(self):
        # ... (Report method remains largely the same, ensure it uses self.framework_variant for keys and display) ...
        report_context = f"BldgReport_{self.framework_variant}"
        self.logger.log_info("FINAL_REPORT_START", "\n" + "="*25 + f" BUILDING SIMULATION FINAL REPORT ({self.framework_variant}) " + "="*25, context_override=report_context)
        
        total_completed = self.metrics['jobs_completed_on_time'] + self.metrics['jobs_completed_late']
        if total_completed > 0:
            completion_times = [job.completion_time - job.creation_time for job in self.processed_jobs if job.status.startswith("COMPLETED") and job.completion_time != -1 and hasattr(job, 'creation_time') and job.creation_time != -1]
            self.metrics['avg_job_completion_time'] = sum(completion_times) / len(completion_times) if completion_times else 0
            
            late_jobs = [job for job in self.processed_jobs if job.status == "COMPLETED_LATE" and job.completion_time != -1 and hasattr(job, 'deadline_time') and job.deadline_time != -1]
            tardiness_values = [job.completion_time - job.deadline_time for job in late_jobs]
            self.metrics['avg_job_tardiness'] = sum(tardiness_values) / len(tardiness_values) if tardiness_values else 0
        
        self.metrics['final_total_balance_network'] = sum(d.balance for d in self.devices) if self.devices else 0
        self.metrics['total_income_generated_network'] = sum(d.total_income_earned for d in self.devices) if self.devices else 0
        
        avg_trust_val_report = "N/A"
        if self.framework_variant in ["social_basic", "full_siot"] and self.devices:
            avg_trust_val_report = sum(d.trust_score for d in self.devices) / len(self.devices)
            self.metrics['avg_trust_at_end'] = avg_trust_val_report 
        else:
             self.metrics['avg_trust_at_end'] = "N/A"

        avg_trust_display = f"{self.metrics['avg_trust_at_end']:.2f}" if isinstance(self.metrics['avg_trust_at_end'], float) else self.metrics['avg_trust_at_end']

        summary_report_lines = [
            f"Framework Variant: {self.metrics['framework_variant']}",
            f"Duration: {self.time_frame}m | Devices: {len(self.devices)} | Zones: {self.num_zones}",
            "--- Job Statistics ---",
            f"Jobs Generated: {self.metrics['jobs_generated']}",
            f"Jobs Assigned: {self.metrics['jobs_assigned']}",
            f"Jobs Completed On Time: {self.metrics['jobs_completed_on_time']}",
            f"Jobs Completed Late: {self.metrics['jobs_completed_late']}",
            f"Jobs Failed (Deadline or Internal): {self.metrics['jobs_failed_deadline'] + self.metrics['jobs_failed_internal']}",
            f"Total Work Units Processed: {self.metrics['total_work_units_processed']}",
            f"Avg Job Completion Time (for completed): {self.metrics['avg_job_completion_time']:.2f} min",
            f"Avg Job Tardiness (for late): {self.metrics['avg_job_tardiness']:.2f} min",
            "--- Device & Network Monetary & Trust ---",
            f"Total Rewards Earned by Devices (from jobs): {self.metrics['total_rewards_earned']:.0f}",
            f"Total Penalties Incurred by Devices (from jobs): {self.metrics['total_penalties_incurred']:.0f}",
            f"Final Total Network Balance: {self.metrics['final_total_balance_network']:.0f}",
            f"Average Final Trust (Social Modes only): {avg_trust_display}",
            f"Delegations to Zone Controllers (by BMS): {self.metrics['delegation_to_zone_controller_count']}",
            f"Delegations to Primitives (by ZC/BMS): {self.metrics['delegation_to_primitive_count']}",
            f"Successful Back-me Invocations: {self.metrics['back_me_invocations_successful']}",
            f"Successful Negotiations (Full SIoT): {self.metrics['successful_negotiations']}",
            f"Failed Negotiations (Full SIoT): {self.metrics['failed_negotiations']}",
            f"Misuse Incidents Detected (Full SIoT): {self.metrics['misuse_incidents_detected']}",
        ]
        self.logger.log_info("OVERALL_SIM_SUMMARY", "\n".join(summary_report_lines), context_override=report_context)
        
        self.logger.store_simulation_metrics(
            simulation_run_key=f"building_{self.framework_variant.lower()}", 
            metrics_dict=self.metrics 
        )
        self.logger.log_info("FINAL_REPORT_END", "="*70, context_override=report_context)