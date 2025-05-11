import random
import time
import uuid # For unique job IDs
from collections import deque # For job queue
from typing import List, Dict, Any, Optional

# Assuming these are in ..devices.device (adjust path if needed)
from ..devices.device import Device, QoELevel 
from ..devices.sensing_device import SensingDevice
from ..devices.actuating_device import ActuatingDevice
from ..devices.communicating_device import CommunicatingDevice
from ..devices.composite_device import CompositeDevice 
# Ensure your logger is correctly imported
from ..utils.logger import SimulationLogger 

# Enhanced Job structure for Building Simulation
class BuildingJob:
    def __init__(self, job_id: str, creation_time: int, job_type: str, 
                 target_zone: Optional[str], work_units_required: int, 
                 deadline_time: int, base_reward: int, 
                 parameters: Optional[Dict[str, Any]] = None, penalty_multiplier: float = 1.5):
        self.id = job_id
        self.creation_time = creation_time
        self.job_type = job_type # e.g., "HVAC_ADJUST", "LIGHTING_SET", "SECURITY_SWEEP"
        self.target_zone = target_zone # e.g., "Office1", "Lobby", or None for building-wide
        self.parameters = parameters if parameters else {} # e.g., {'target_temp': 22}
        
        self.work_units_required = work_units_required # Represents complexity/sub-tasks
        self.work_units_done = 0
        
        self.deadline_time = deadline_time # Absolute simulation time
        self.assigned_to_device_id = None # Could be BMS, ZoneController, or primitive device
        self.status = "PENDING" # PENDING, ASSIGNED, IN_PROGRESS, COMPLETED_ON_TIME, COMPLETED_LATE, FAILED_DEADLINE, FAILED_INTERNAL
        self.completion_time = -1
        self.base_reward = base_reward
        self.penalty_for_failure = int(base_reward * penalty_multiplier)
        self.sub_task_results = [] # To store outcomes of sub-tasks if job is complex

    def __repr__(self):
        return (f"Job(id={self.id}, type={self.job_type}, zone={self.target_zone}, "
                f"wu={self.work_units_done}/{self.work_units_required}, "
                f"dl={self.deadline_time}, status={self.status}, assigned_to={self.assigned_to_device_id})")

class BuildingSimulation:
    def __init__(self, framework_enabled=True, num_zones=3, devices_per_zone_avg=4, 
                 duration_minutes=480, logger_instance=None): # devices_per_zone_avg used for num_devices calculation
        
        self.framework_enabled = framework_enabled
        self.num_zones = num_zones
        self.devices_per_zone_avg = devices_per_zone_avg
        self.num_devices = (num_zones * devices_per_zone_avg) + num_zones + 1 # Primitives + ZoneControllers + BMS
        
        self.devices: List[Device] = []
        self.zone_controllers: Dict[str, CompositeDevice] = {}
        self.bms: Optional[CompositeDevice] = None
        self.zones: List[str] = [f"Zone{i+1}" for i in range(num_zones)]

        self.time_frame = duration_minutes 
        
        if logger_instance:
            self.logger = logger_instance
        else:
            self.logger = SimulationLogger(simulation_name=f"BldgSim_Framework{'ON' if framework_enabled else 'OFF'}")
        
        self.current_minute = 0

        # Job Management
        self.job_queue = deque()
        self.active_jobs: Dict[str, BuildingJob] = {} # Jobs currently IN_PROGRESS or ASSIGNED, keyed by job_id
        self.processed_jobs: List[BuildingJob] = [] # Completed or Failed jobs
        self.next_job_id_counter = 0
        
        # Job Generation Parameters
        self.scheduled_job_interval = 60 # e.g., every hour for HVAC schedule check
        self.event_trigger_chance = 0.1 # Chance per cycle for a random event
        self.sudden_workload_chance = 0.03

        # Metrics
        self.metrics = {
            'framework_mode': "SIoT_Framework_ENABLED" if framework_enabled else "Baseline_Framework_DISABLED",
            'jobs_generated': 0, 'jobs_assigned':0, 'jobs_completed_on_time': 0,
            'jobs_completed_late': 0, 'jobs_failed_deadline': 0, 'jobs_failed_internal': 0,
            'total_work_units_processed': 0, 'avg_job_completion_time': 0, 'avg_job_tardiness': 0,
            'device_cycles_working': {f"dev_placeholder_{i}":0 for i in range(self.num_devices)}, # Will be updated with actual IDs
            'device_cycles_idle': {f"dev_placeholder_{i}":0 for i in range(self.num_devices)},
            'total_rewards_earned': 0, 'total_penalties_incurred': 0,
            'qoe_interaction_samples': [], 'avg_trust_at_end': "N/A",
            'final_total_balance_network': 0, 'total_income_generated_network': 0,
            'min_income_check_interval': duration_minutes // 4 if duration_minutes > 0 else 60, # Check quarterly
            'delegation_to_zone_controller_count': 0,
            'delegation_to_primitive_count': 0,
            'back_me_invocations_successful': 0,
            # Add more specific metrics as needed
        }
        self.logger.log_info("SIM_INIT", f"Building Simulation ({self.metrics['framework_mode']}) | Devices: approx {self.num_devices} | Zones: {num_zones} | Duration: {self.time_frame}m", 
                             context_override=f"BldgSim_Framework{'ON' if framework_enabled else 'OFF'}")

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
        min_income_per_period = self.metrics['min_income_check_interval'] * 0.5 # e.g. 0.5 currency unit per minute

        # 1. Create BMS
        bms_id = f"bldg_bms_{dev_id_counter}"; dev_id_counter+=1
        self.bms = CompositeDevice(bms_id, "CentralBMS", max_load=500, 
                                   capabilities=["coordinate_zones", "set_global_policy", "emergency_response", "energy_management"])
        self.bms.balance = base_starting_balance * 2
        self.bms.min_acceptable_income_threshold = min_income_per_period * 2
        self.devices.append(self.bms)
        self.logger.log_info("DEV_SETUP", f"Created {self.bms.nameShort()}")

        # 2. Create Zone Controllers and Devices per Zone
        for zone_name in self.zones:
            zc_id = f"bldg_zc_{zone_name.lower()}_{dev_id_counter}"; dev_id_counter+=1
            zone_controller = CompositeDevice(zc_id, f"ZoneController_{zone_name}", max_load=200,
                                              capabilities=["manage_hvac", "manage_lighting", "zone_security", "delegate_tasks"])
            setattr(zone_controller, 'zone', zone_name) # Assign zone using setattr
            zone_controller.balance = base_starting_balance * 1.5
            zone_controller.min_acceptable_income_threshold = min_income_per_period * 1.5
            self.devices.append(zone_controller)
            self.zone_controllers[zone_name] = zone_controller
            self.logger.log_info("DEV_SETUP", f"Created {zone_controller.nameShort()} for {zone_name}")

            if self.framework_enabled and self.bms:
                self.bms.add_worker(zone_controller, constraints={'role': 'zone_management'}) # BMS controls ZCs

            # Create primitive devices for this zone
            for i in range(random.randint(max(1, self.devices_per_zone_avg -1), self.devices_per_zone_avg + 1)): # Ensure at least 1
                dev_id = f"bldg_dev{dev_id_counter}_{zone_name.lower()}"; dev_id_counter+=1
                dev_type = random.choice(["sensor", "actuator", "communicator"]) 
                primitive_device: Optional[Device] = None

                if dev_type == "sensor":
                    sensor_kind = random.choice(["temperature", "occupancy", "light_level", "co2", "door_contact"])
                    primitive_device = SensingDevice(dev_id, f"{sensor_kind.capitalize()}Sensor_{zone_name}_{i+1}", sensor_type=sensor_kind)
                elif dev_type == "actuator":
                    actuator_kind = random.choice(["hvac_control", "light_switch", "smart_blind", "door_lock"])
                    primitive_device = ActuatingDevice(dev_id, f"{actuator_kind.capitalize()}Actuator_{zone_name}_{i+1}", actuator_type=actuator_kind)
                elif dev_type == "communicator": 
                    primitive_device = CommunicatingDevice(dev_id, f"CommRelay_{zone_name}_{i+1}")
                
                if primitive_device:
                    setattr(primitive_device, 'zone', zone_name) # Assign zone
                    primitive_device.balance = base_starting_balance + random.randint(-200, 50)
                    primitive_device.min_acceptable_income_threshold = min_income_per_period
                    self.devices.append(primitive_device)
                    self.logger.log_info("DEV_SETUP", f"Created {primitive_device.nameShort()} in {zone_name}")
                    if self.framework_enabled:
                        zone_controller.add_worker(primitive_device, constraints={'role': f'{primitive_device.__class__.__name__}_in_{zone_name}'})

        # Initialize metrics for actual device IDs
        self.metrics['device_cycles_working'] = {dev.device_id: 0 for dev in self.devices}
        self.metrics['device_cycles_idle'] = {dev.device_id: 0 for dev in self.devices}

        # Establish other social relations if framework is enabled
        if self.framework_enabled:
            all_composites = ([self.bms] if self.bms else []) + list(self.zone_controllers.values())
            for i in range(len(all_composites)):
                for j in range(i + 1, len(all_composites)):
                    if random.random() < 0.4: 
                        all_composites[i].add_relationship('work_with_me', all_composites[j])
                        all_composites[j].add_relationship('work_with_me', all_composites[i])
            
            for dev in self.devices: 
                if isinstance(dev, (SensingDevice, ActuatingDevice)) and random.random() < 0.2:
                    # Ensure dev has 'zone' attribute before accessing
                    dev_zone = getattr(dev, 'zone', None)
                    if dev_zone:
                        potential_backups = [
                            d for d in self.devices 
                            if d != dev and getattr(d, 'zone', None) == dev_zone and type(d) == type(dev)
                        ]
                        if potential_backups:
                            backup_dev = random.choice(potential_backups)
                            dev.add_relationship('back_me', backup_dev)
        self.logger.log_info("DEV_SETUP", f"Total devices created: {len(self.devices)}")


    def _generate_jobs(self):
        # 1. Scheduled Jobs (e.g., HVAC adjustments)
        if self.current_minute % self.scheduled_job_interval == 0:
            for zone in self.zones:
                job_type = "HVAC_SCHEDULE_CHECK"
                params = {'target_mode': "AUTO", 'current_time_of_day': self.current_minute % (24*60)}
                work = random.randint(3,7) 
                deadline = self.current_minute + 15 
                reward = work * 8
                job = BuildingJob(self._get_next_job_id(), self.current_minute, job_type, zone, work, deadline, reward, params)
                self.job_queue.append(job)
                self.metrics['jobs_generated'] += 1
                self.logger.log_info("JOB_GEN_SCHED", f"{job}")

        # 2. Event-Triggered Jobs (Simulated events)
        if random.random() < self.event_trigger_chance:
            event_zone = random.choice(self.zones)
            event_type = random.choice(["MOTION_UNEXPECTED", "DOOR_AJAR", "TEMP_ANOMALY", "LIGHT_MALFUNCTION"])
            job_type = f"EVENT_{event_type}"
            params = {'source_event': event_type}
            work = random.randint(5,15)
            deadline = self.current_minute + random.randint(10, 30)
            reward = work * 10
            job = BuildingJob(self._get_next_job_id(), self.current_minute, job_type, event_zone, work, deadline, reward, params)
            self.job_queue.append(job)
            self.metrics['jobs_generated'] += 1
            self.logger.log_info("JOB_GEN_EVENT", f"{job}")

        # 3. Sudden Global Workload (e.g., "Prepare for VIP visit", "Energy saving drill")
        if random.random() < self.sudden_workload_chance:
            num_sudden = random.randint(1,2)
            for _ in range(num_sudden):
                job_type = "GLOBAL_SYSTEM_CHECK" 
                work = random.randint(10, 20) * self.num_zones 
                deadline = self.current_minute + random.randint(30, 90)
                reward = work * 5 
                job = BuildingJob(self._get_next_job_id(), self.current_minute, job_type, None, work, deadline, reward, {'reason': "Sudden Drill"})
                self.job_queue.append(job)
                self.metrics['jobs_generated'] += 1
                self.logger.log_info("JOB_GEN_SUDDEN", f"{job}")

    def _assign_jobs_to_devices(self):
        jobs_processed_this_assignment_round = set()

        for job in list(self.job_queue): 
            if job.id in jobs_processed_this_assignment_round or job.status != "PENDING":
                continue

            assigned_entity: Optional[Device] = None 

            if self.framework_enabled:
                if job.target_zone is None and self.bms: 
                    if not getattr(self.bms, 'current_job_id', None) and self.bms.current_load < self.bms.max_load * 0.7:
                        assigned_entity = self.bms
                elif job.target_zone in self.zone_controllers:
                    zc = self.zone_controllers[job.target_zone]
                    if not getattr(zc, 'current_job_id', None) and zc.current_load < zc.max_load * 0.7: 
                        assigned_entity = zc
                else: 
                    pass 
            else:
                candidate_devices = [
                    d for d in self.devices 
                    if (job.target_zone is None or getattr(d,'zone', None) == job.target_zone) and \
                       not getattr(d, 'current_job_id', None) and \
                       d.current_load < d.max_load * 0.9
                ]
                if candidate_devices:
                    suitable_devices = []
                    # Corrected Basic capability match 
                    if "HVAC" in job.job_type or "TEMP" in job.job_type:
                        suitable_devices = [
                            d for d in candidate_devices if 
                            (isinstance(d, ActuatingDevice) and "hvac" in d.actuator_type) or 
                            (isinstance(d, SensingDevice) and "temp" in d.sensor_type) or 
                            isinstance(d, CompositeDevice) # Composites might manage HVAC/Temp
                        ]
                    elif "LIGHT" in job.job_type:
                         suitable_devices = [
                             d for d in candidate_devices if 
                             (isinstance(d, ActuatingDevice) and "light" in d.actuator_type) or 
                             (isinstance(d, SensingDevice) and "light" in d.sensor_type) or 
                             isinstance(d, CompositeDevice) # Composites might manage lights
                         ]
                    else: 
                        suitable_devices = candidate_devices
                    
                    if suitable_devices:
                        assigned_entity = random.choice(suitable_devices)
            
            if assigned_entity:
                job.assigned_to_device_id = assigned_entity.device_id
                job.status = "ASSIGNED"
                setattr(assigned_entity, 'current_job_id', job.id) # Mark device as busy
                self.metrics['jobs_assigned'] += 1
                self.active_jobs[job.id] = job 
                if job in self.job_queue: self.job_queue.remove(job)
                jobs_processed_this_assignment_round.add(job.id)
                self.logger.log_info("JOB_ASSIGN", f"Job {job.id} ({job.job_type}) assigned to {assigned_entity.nameShort()}")
            else:
                 self.logger.log_info("JOB_ASSIGN_PEND", f"Job {job.id} ({job.job_type}) remains PENDING.")


    def _process_device_job(self, device: Device, job: BuildingJob):
        work_performed_this_cycle = False
        if device.current_load < device.max_load * 0.9: 
            if not device.consume_load(15): 
                self.logger.log_info("JOB_PROGRESS", f"Device {device.nameShort()} on Job {job.id} FAILED to consume load for work.")
                self.metrics['device_cycles_idle'][device.device_id] +=1
                return 

            job.work_units_done += 1
            self.metrics['total_work_units_processed'] += 1
            self.metrics['device_cycles_working'][device.device_id] +=1
            work_performed_this_cycle = True
            self.logger.log_info("JOB_PROGRESS", f"{device.nameShort()} worked on Job {job.id}: {job.work_units_done}/{job.work_units_required} WU. Load: {device.current_load}")

            # --- Framework ON: Simulate sub-task interactions for complex jobs ---
            if self.framework_enabled and isinstance(device, CompositeDevice) and job.work_units_done < job.work_units_required :
                # This is where a CompositeDevice would call handle_request on its workers,
                # and QoS/Trust would be updated based on those sub-interactions.
                # This logic needs to be fleshed out based on job_type and parameters.
                # For example, for "HVAC_ADJUST":
                if job.job_type == "HVAC_ADJUST":
                    self.logger.log_info("COMPOSITE_ACTION", f"{device.nameShort()} attempting to manage HVAC for job {job.id}")
                    # Find relevant sensor and actuator workers
                    sensors = [w_rel['device'] for w_rel in device.relationships.get('controller_for', []) if isinstance(w_rel['device'], SensingDevice) and 'temp' in w_rel['device'].sensor_type]
                    actuators = [w_rel['device'] for w_rel in device.relationships.get('controller_for', []) if isinstance(w_rel['device'], ActuatingDevice) and 'hvac' in w_rel['device'].actuator_type]

                    if sensors and actuators:
                        sensor = random.choice(sensors) # In reality, might pick most trusted or specific one
                        actuator = random.choice(actuators)
                        
                        # 1. Sense temperature
                        sensor_details = {'iot_app_reward': 0} # No direct reward for this sub-task from job perspective
                        sensor_outcome = sensor.handle_request(device, 'sense', load_requested=5, details=sensor_details)
                        device.update_trust_from_qoe(sensor, 'sense', sensor_outcome['measured_qos_for_requestor'], "requester")
                        
                        if sensor_outcome.get('success'):
                            current_temp = sensor_outcome.get('value', 25) # Default if no value
                            target_temp = job.parameters.get('target_temp', 22)
                            self.logger.log_info("COMPOSITE_ACTION", f"Job {job.id}: Current temp {current_temp}, Target {target_temp}")
                            if abs(current_temp - target_temp) > 0.5: # If adjustment needed
                                actuator_details = {'iot_app_reward': 0, 'command': 'SET_TEMP', 'value': target_temp} # Example command
                                actuator_outcome = actuator.handle_request(device, 'actuate', load_requested=10, details=actuator_details)
                                device.update_trust_from_qoe(actuator, 'actuate', actuator_outcome['measured_qos_for_requestor'], "requester")
                                job.sub_task_results.append({'actuator_success': actuator_outcome.get('success', False)})
                                if actuator_outcome.get('success'):
                                     self.logger.log_info("COMPOSITE_ACTION", f"Job {job.id}: HVAC actuated by {actuator.nameShort()} for {device.nameShort()}")
                                else:
                                     self.logger.log_info("COMPOSITE_ACTION", f"Job {job.id}: HVAC actuation FAILED by {actuator.nameShort()}")
                            else:
                                self.logger.log_info("COMPOSITE_ACTION", f"Job {job.id}: Temp already optimal, no HVAC actuation needed.")
                                job.sub_task_results.append({'hvac_optimal': True})
                        else:
                            self.logger.log_info("COMPOSITE_ACTION", f"Job {job.id}: Temperature sensing FAILED by {sensor.nameShort()}")
                            job.sub_task_results.append({'sensor_success': False})
                    else:
                        self.logger.log_info("COMPOSITE_ACTION", f"Composite {device.nameShort()} couldn't find necessary HVAC sensor/actuator workers for job {job.id}")
                        # This could be a reason for job.status = "FAILED_INTERNAL" if it prevents progress
            # End of placeholder for detailed sub-task logic
        else: 
            self.logger.log_info("JOB_PROGRESS", f"Device {device.nameShort()} on Job {job.id} is OVERLOADED (load: {device.current_load}), no progress.")
            self.metrics['device_cycles_idle'][device.device_id] +=1

        if job.work_units_done >= job.work_units_required:
            job.completion_time = self.current_minute
            status_log_prefix = f"Job {job.id} ({job.job_type})"
            if self.current_minute <= job.deadline_time:
                job.status = "COMPLETED_ON_TIME"
                self.metrics['jobs_completed_on_time'] += 1
                device.receive_income(job.base_reward, f"{status_log_prefix} on time")
                self.metrics['total_rewards_earned'] += job.base_reward
                self.logger.log_info("JOB_COMPLETE", f"{status_log_prefix} COMPLETED ON TIME by {device.nameShort()}. Reward: {job.base_reward}")
            else:
                job.status = "COMPLETED_LATE"
                self.metrics['jobs_completed_late'] += 1
                reduced_reward = int(job.base_reward * 0.6) 
                device.receive_income(reduced_reward, f"{status_log_prefix} late")
                self.metrics['total_rewards_earned'] += reduced_reward
                self.logger.log_info("JOB_COMPLETE", f"{status_log_prefix} COMPLETED LATE by {device.nameShort()}. Reward: {reduced_reward}")
            
            self.processed_jobs.append(job)
            if job.id in self.active_jobs: del self.active_jobs[job.id]
            setattr(device, 'current_job_id', None) # Free up device

        elif self.current_minute > job.deadline_time:
            job.status = "FAILED_DEADLINE"
            job.completion_time = self.current_minute 
            self.metrics['jobs_failed_deadline'] += 1
            device.receive_penalty(job.penalty_for_failure, "System", f"Job {job.id} missed deadline")
            self.metrics['total_penalties_incurred'] += job.penalty_for_failure
            self.logger.log_info("JOB_FAIL", f"Job {job.id} ({job.job_type}) FAILED DEADLINE on {device.nameShort()}. Penalty: {job.penalty_for_failure}")
            self.processed_jobs.append(job)
            if job.id in self.active_jobs: del self.active_jobs[job.id]
            setattr(device, 'current_job_id', None)


    def simulate_cycle(self, minute):
        self.current_minute = minute
        self.logger.log_info("CYCLE_START", f"Minute: {self.current_minute} ({self.metrics['framework_mode']})")
        
        self._generate_jobs()
        self._assign_jobs_to_devices() 

        random.shuffle(self.devices) 

        for device in self.devices:
            if getattr(device, 'current_job_id', None) and device.current_job_id in self.active_jobs:
                job = self.active_jobs[device.current_job_id]
                if job.status == "ASSIGNED": 
                    job.status = "IN_PROGRESS"
                    self.logger.log_info("JOB_START", f"Device {device.nameShort()} starting Job {job.id} ({job.job_type})")
                
                if job.status == "IN_PROGRESS":
                    self._process_device_job(device, job)
            
            else: 
                 self.metrics['device_cycles_idle'][device.device_id] +=1
                 if self.framework_enabled and random.random() < 0.03 and len(self.devices) > 1: 
                    requestor = device
                    potential_targets = [rel['device'] for rel in requestor.relationships.get('work_with_me', []) if rel.get('status')=='active']
                    if not potential_targets:
                        potential_targets = [d for d in self.devices if d != requestor and isinstance(d, CompositeDevice) and not any(r['device']==requestor for r in d.relationships.get('avoid_me',[]))]
                    if not potential_targets : 
                        potential_targets = [d for d in self.devices if d != requestor and not any(r['device']==requestor for r in d.relationships.get('avoid_me',[]))]

                    if potential_targets:
                        target_performer = random.choice(potential_targets)
                        requested_task = random.choice(['sense', 'transmit']) 
                        load_for_task = random.randint(2,5)
                        details = {'iot_app_reward': 0, 'message': f"Coordination ping from {requestor.nameShort()}"}
                        if requested_task == 'transmit': details['target_comm_device'] = target_performer 

                        outcome = target_performer.handle_request(requestor, requested_task, load_for_task, details)
                        if 'measured_qos_for_requestor' in outcome: # Check if key exists
                            requestor.update_trust_from_qoe(target_performer, requested_task, outcome['measured_qos_for_requestor'], "requester")
                            if outcome.get('success'): 
                                self.logger.log_info("SIM_INTERACTION", f"{requestor.nameShort()} successful background '{requested_task}' with {target_performer.nameShort()}")

            device.reduce_load(random.randint(5,10)) 
            if self.current_minute > 0 and self.current_minute % self.metrics['min_income_check_interval'] == 0:
                device.check_min_income_satisfied()

        for job in list(self.job_queue): 
            if job.status == "PENDING" and self.current_minute > job.deadline_time:
                job.status = "FAILED_DEADLINE_UNASSIGNED"
                self.metrics['jobs_failed_deadline'] += 1
                self.logger.log_info("JOB_FAIL_QUEUE", f"Job {job.id} ({job.job_type}) FAILED DEADLINE (unassigned from queue).")
                self.processed_jobs.append(job)
                self.job_queue.remove(job)

        self.logger.log_info("CYCLE_END", f"Minute: {self.current_minute} | Pending Jobs: {len(self.job_queue)} | Active Jobs: {len(self.active_jobs)}")


    def run(self):
        self.setup_devices()
        for minute_cycle in range(self.time_frame):
            self.simulate_cycle(minute_cycle)
            if minute_cycle > 0 and (minute_cycle % (self.time_frame // 10 if self.time_frame >=10 else 1) == 0 or minute_cycle == self.time_frame -1) :
                 self.logger.log_info("PERIODIC_SUM", f"Min {minute_cycle} | Jobs (Pend/Act/Fail): {len(self.job_queue)}/{len(self.active_jobs)}/{sum(1 for j in self.processed_jobs if 'FAIL' in j.status)} | Comp(OK/Late):{self.metrics['jobs_completed_on_time']}/{self.metrics['jobs_completed_late']}")
        self.report()

    def report(self):
        self.logger.log_info("FINAL_REPORT_START", "\n" + "="*25 + f" BUILDING SIMULATION FINAL REPORT ({self.metrics['framework_mode']}) " + "="*25, context_override=f"BldgReport_{self.metrics['framework_mode']}")
        
        total_completed = self.metrics['jobs_completed_on_time'] + self.metrics['jobs_completed_late']
        if total_completed > 0:
            completion_times = [job.completion_time - job.creation_time for job in self.processed_jobs if job.status.startswith("COMPLETED") and job.completion_time != -1 and job.creation_time != -1]
            self.metrics['avg_job_completion_time'] = sum(completion_times) / len(completion_times) if completion_times else 0
            
            late_jobs = [job for job in self.processed_jobs if job.status == "COMPLETED_LATE" and job.completion_time != -1 and job.deadline_time != -1]
            tardiness_values = [job.completion_time - job.deadline_time for job in late_jobs]
            self.metrics['avg_job_tardiness'] = sum(tardiness_values) / len(tardiness_values) if tardiness_values else 0
        
        self.metrics['final_total_balance_network'] = sum(d.balance for d in self.devices)
        self.metrics['total_income_generated_network'] = sum(d.total_income_earned for d in self.devices) 
        
        avg_trust_val_report = "N/A (Framework Disabled)"
        if self.framework_enabled and self.devices: # Check if self.devices is not empty
            avg_trust_val_report = sum(d.trust_score for d in self.devices) / len(self.devices)
            self.metrics['avg_trust_at_end'] = avg_trust_val_report 
        else:
             self.metrics['avg_trust_at_end'] = avg_trust_val_report 

        avg_trust_display = f"{self.metrics['avg_trust_at_end']:.2f}" if isinstance(self.metrics['avg_trust_at_end'], float) else self.metrics['avg_trust_at_end']

        summary_report_lines = [
            f"Framework Mode: {self.metrics['framework_mode']}",
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
            f"Average Final Trust (Framework ON only): {avg_trust_display}",
            f"Delegations to Zone Controllers: {self.metrics['delegation_to_zone_controller_count']}",
            f"Delegations to Primitives (by ZC/BMS): {self.metrics['delegation_to_primitive_count']}",
            f"Successful Back-me Invocations: {self.metrics['back_me_invocations_successful']}"
        ]
        self.logger.log_info("OVERALL_SIM_SUMMARY", "\n".join(summary_report_lines), context_override=f"BldgReport_{self.metrics['framework_mode']}")
        
        self.logger.store_simulation_metrics(
            simulation_run_key=f"building_{'framework_on' if self.framework_enabled else 'framework_off'}", 
            metrics_dict=self.metrics 
        )
        self.logger.log_info("FINAL_REPORT_END", "="*70, context_override=f"BldgReport_{self.metrics['framework_mode']}")

