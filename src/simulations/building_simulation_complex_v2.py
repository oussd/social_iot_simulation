import random
import time
import uuid # For unique job IDs
from collections import deque # For job queue
from typing import List, Dict, Any, Optional

from ..devices.device import Device, QoELevel
from ..devices.sensing_device import SensingDevice
from ..devices.actuating_device import ActuatingDevice
from ..devices.communicating_device import CommunicatingDevice
from ..devices.composite_device import CompositeDevice
from ..utils.logger import SimulationLogger

class CardReaderSensor(SensingDevice):
    def __init__(self, device_id, name, max_load=50, framework_variant="full_siot", logger_instance=None, current_minute_provider=None, **kwargs):
        super().__init__(device_id, name, max_load, sensor_type="card_swipe", framework_variant=framework_variant, logger_instance=logger_instance, current_minute_provider=current_minute_provider, **kwargs)
        self.access_log = []
    # _perform_sense_action is inherited

class PowerMeterSensor(SensingDevice):
    def __init__(self, device_id, name, max_load=50, zone_name="", framework_variant="full_siot", logger_instance=None, current_minute_provider=None, **kwargs):
        super().__init__(device_id, name, max_load, sensor_type="power_usage", framework_variant=framework_variant, logger_instance=logger_instance, current_minute_provider=current_minute_provider, **kwargs)
        self.current_power_draw_kw = random.uniform(0.5, 5.0)
        self.zone_name = zone_name
    # _perform_sense_action is inherited

class SmartPlugActuator(ActuatingDevice):
    def __init__(self, device_id, name, max_load=30, framework_variant="full_siot", logger_instance=None, current_minute_provider=None, **kwargs):
        super().__init__(device_id, name, max_load, actuator_type="smart_plug", framework_variant=framework_variant, logger_instance=logger_instance, current_minute_provider=current_minute_provider, **kwargs)
        self.current_state = "ON"
    # _perform_actuation_action is inherited

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
        self.assigned_to_device_id: Optional[str] = None
        self.status = "PENDING"
        self.completion_time = -1
        self.base_reward = base_reward
        self.penalty_for_failure = int(base_reward * penalty_multiplier)
        self.priority = priority
        self.sub_task_results: List[Dict[str, Any]] = []

    def __repr__(self):
        return (f"Job(id={self.id}, type={self.job_type}, zone={self.target_zone}, prio={self.priority}, "
                f"wu={self.work_units_done}/{self.work_units_required}, "
                f"dl={self.deadline_time}, status={self.status}, assigned_to={self.assigned_to_device_id})")

class BuildingSimulationComplex_V2:
    def __init__(self, framework_variant: str = "full_siot",
                 num_zones: int = 2, devices_per_zone_avg: int = 3,
                 duration_minutes: int = 240, logger_instance: Optional[SimulationLogger] = None,
                 run_context_name: str = "BldgComplexSimV2Run"):

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
        self.job_queue: deque[BuildingJob] = deque()
        self.active_jobs: Dict[str, BuildingJob] = {}
        self.processed_jobs: List[BuildingJob] = []
        self.next_job_id_counter = 0
        self.scheduled_job_interval = 20 
        self.event_trigger_chance = 0.25 
        self.sudden_workload_chance = 0.10 
        self.sudden_workload_multiplier = 1.5 

        self.metrics: Dict[str, Any] = {
            'framework_variant': framework_variant,
            'jobs_generated': 0, 'jobs_assigned':0, 'jobs_completed_on_time': 0,
            'jobs_completed_late': 0, 'jobs_failed_deadline': 0, 'jobs_failed_internal': 0,
            'total_work_units_processed': 0, 'avg_job_completion_time': 0.0, 'avg_job_tardiness': 0.0,
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
            'selfish_rejections': 0,
            'faulty_device_actions_failed': 0,
            'unresponsive_device_rejections': 0,
            'total_policy_violations_blamed': 0, 
        }
        self.logger.log_info(self.run_context_name, f"BuildingSimulationComplex_V2 ({self.framework_variant}) | Devices: approx {self.num_devices_approx} | Zones: {num_zones} | Duration: {self.time_frame}m")
    
    def _get_next_job_id(self) -> str:
        self.next_job_id_counter += 1
        return f"bldg_cplx2_job_{self.next_job_id_counter}"

    def _get_device_by_id(self, device_id: Optional[str]) -> Optional[Device]:
        if not device_id: return None
        for dev in self.devices:
            if dev.device_id == device_id:
                return dev
        return None

    def _get_random_device_behavior_params(self, num_selfish_rem, num_deceptive_rem, num_policy_violators_rem,
                                           num_faulty_rem, num_unresponsive_rem, is_composite=False) -> Dict:
        params = {
            'behavior_profile': "normal",
            'fault_probability': 0.0,
            'unresponsive_probability': 0.0,
            'deception_factor': 1.0,
            'unresponsive_duration_range': (5,15) 
        }
        profile_rand_factor = 0.8 if is_composite else 1.0 
        assigned_profile = False
        if num_selfish_rem > 0 and random.random() < 0.20 * profile_rand_factor: 
            params['behavior_profile'] = 'selfish'; assigned_profile=True
        elif not assigned_profile and num_deceptive_rem > 0 and random.random() < 0.20 * profile_rand_factor: 
            params['behavior_profile'] = 'deceptive'; assigned_profile=True
        elif not assigned_profile and num_policy_violators_rem > 0 and random.random() < 0.15 * profile_rand_factor: 
            params['behavior_profile'] = 'policy_violator'; assigned_profile=True
        
        if num_faulty_rem > 0 and random.random() < 0.25: 
            params['fault_probability'] = random.uniform(0.05, 0.20) 
        if num_unresponsive_rem > 0 and random.random() < 0.20: 
            params['unresponsive_probability'] = random.uniform(0.02, 0.10) 
            params['unresponsive_duration_range'] = (random.randint(3,8), random.randint(10,20))
        if params['behavior_profile'] == 'deceptive':
            params['deception_factor'] = random.uniform(0.4, 0.7) 
        return params

    def setup_devices(self):
        dev_id_counter = 0
        base_starting_balance = 1000
        min_income_per_period = self.metrics.get('min_income_check_interval', 60) * 0.5
        estimated_total_devices = self.num_devices_approx 
        s_rem = int(estimated_total_devices * 0.10) 
        d_rem = int(estimated_total_devices * 0.10) 
        pv_rem = int(estimated_total_devices * 0.05)
        f_rem = int(estimated_total_devices * 0.15) 
        u_rem = int(estimated_total_devices * 0.10) 

        bms_id = f"bldg_cplx2_bms_{dev_id_counter}"; dev_id_counter+=1
        bms_behavior_params = self._get_random_device_behavior_params(s_rem, d_rem, pv_rem, f_rem, u_rem, is_composite=True)
        if bms_behavior_params['behavior_profile']=='selfish': s_rem=max(0,s_rem-1)
        if bms_behavior_params['behavior_profile']=='deceptive': d_rem=max(0,d_rem-1)
        if bms_behavior_params['behavior_profile']=='policy_violator': pv_rem=max(0,pv_rem-1)
        if bms_behavior_params['fault_probability']>0: f_rem=max(0,f_rem-1)
        if bms_behavior_params['unresponsive_probability']>0: u_rem=max(0,u_rem-1)

        self.bms = CompositeDevice(bms_id, "CentralBMS_CplxV2", max_load=500,
                                   capabilities=["coordinate_zones", "set_global_policy", "emergency_response", "energy_management", "assign_global_jobs"],
                                   framework_variant=self.framework_variant, logger_instance=self.logger, current_minute_provider=lambda: self.current_minute,
                                   **bms_behavior_params)
        self.bms.balance = base_starting_balance * 2
        self.bms.min_acceptable_income_threshold = min_income_per_period * 2
        self.bms.sim_metrics_ref = self.metrics
        self.devices.append(self.bms)
        self.logger.log_info(self.run_context_name, f"Created {self.bms.nameShort()} with profile: {self.bms.behavior_profile}, fault_prob: {self.bms.fault_probability:.2f}, unresp_prob: {self.bms.unresponsive_probability:.2f}")

        for zone_idx, zone_name in enumerate(self.zones):
            zc_id = f"bldg_cplx2_zc{zone_idx+1}_{dev_id_counter}"; dev_id_counter+=1
            zc_behavior_params = self._get_random_device_behavior_params(s_rem, d_rem, pv_rem, f_rem, u_rem, is_composite=True)
            if zc_behavior_params['behavior_profile']=='selfish': s_rem=max(0,s_rem-1)
            if zc_behavior_params['behavior_profile']=='deceptive': d_rem=max(0,d_rem-1)
            if zc_behavior_params['behavior_profile']=='policy_violator': pv_rem=max(0,pv_rem-1)
            if zc_behavior_params['fault_probability']>0: f_rem=max(0,f_rem-1)
            if zc_behavior_params['unresponsive_probability']>0: u_rem=max(0,u_rem-1)
            
            zone_controller = CompositeDevice(zc_id, f"ZoneCtrl_CplxV2_{zone_name}", max_load=250, 
                                              capabilities=["manage_hvac", "manage_lighting", "zone_security_local", "delegate_zone_tasks", "access_control_zone"],
                                              framework_variant=self.framework_variant, logger_instance=self.logger, current_minute_provider=lambda: self.current_minute,
                                              **zc_behavior_params)
            setattr(zone_controller, 'zone', zone_name)
            zone_controller.balance = base_starting_balance * 1.5
            zone_controller.min_acceptable_income_threshold = min_income_per_period * 1.5
            zone_controller.sim_metrics_ref = self.metrics
            self.devices.append(zone_controller)
            self.zone_controllers[zone_name] = zone_controller
            self.logger.log_info(self.run_context_name, f"Created {zone_controller.nameShort()} with profile: {zone_controller.behavior_profile}, fault_prob: {zone_controller.fault_probability:.2f}, unresp_prob: {zone_controller.unresponsive_probability:.2f}")

            if self.framework_variant in ["social_basic", "full_siot"] and self.bms:
                self.bms.add_worker(zone_controller, constraints={'role': 'zone_management', 'zone': zone_name})

            num_primitives_this_zone = random.randint(max(1, self.devices_per_zone_avg -1), self.devices_per_zone_avg + 1)
            for i in range(num_primitives_this_zone):
                dev_id = f"bldg_cplx2_d{dev_id_counter}_{zone_name[:2].lower()}{i}"; dev_id_counter+=1
                primitive_behavior_params = self._get_random_device_behavior_params(s_rem, d_rem, pv_rem, f_rem, u_rem)
                if primitive_behavior_params['behavior_profile']=='selfish': s_rem=max(0,s_rem-1)
                if primitive_behavior_params['behavior_profile']=='deceptive': d_rem=max(0,d_rem-1)
                if primitive_behavior_params['behavior_profile']=='policy_violator': pv_rem=max(0,pv_rem-1)
                if primitive_behavior_params['fault_probability']>0: f_rem=max(0,f_rem-1)
                if primitive_behavior_params['unresponsive_probability']>0: u_rem=max(0,u_rem-1)
                
                dev_type_roll = random.random()
                primitive_device: Optional[Device] = None
                common_args_init = {'framework_variant': self.framework_variant, 
                                'logger_instance': self.logger, 
                                'current_minute_provider': lambda: self.current_minute,
                                **primitive_behavior_params}
                if dev_type_roll < 0.4:
                    sensor_kind = random.choice(["temperature", "occupancy", "light_level", "co2", "door_contact", "window_contact", "power_meter", "card_reader"])
                    if sensor_kind == "card_reader": primitive_device = CardReaderSensor(dev_id, f"CRSens_Cplx2_{zone_name}_{i+1}", **common_args_init)
                    elif sensor_kind == "power_meter": primitive_device = PowerMeterSensor(dev_id, f"PMSens_Cplx2_{zone_name}_{i+1}", zone_name=zone_name, **common_args_init)
                    else: primitive_device = SensingDevice(dev_id, f"{sensor_kind.capitalize()}Sens_Cplx2_{zone_name}_{i+1}", sensor_type=sensor_kind, **common_args_init)
                elif dev_type_roll < 0.8:
                    actuator_kind = random.choice(["hvac_control", "light_switch", "smart_blind", "door_lock", "smart_plug", "alarm_siren"])
                    if actuator_kind == "smart_plug": primitive_device = SmartPlugActuator(dev_id, f"SPlug_Cplx2_{zone_name}_{i+1}", **common_args_init)
                    else: primitive_device = ActuatingDevice(dev_id, f"{actuator_kind.capitalize()}Act_Cplx2_{zone_name}_{i+1}", actuator_type=actuator_kind, **common_args_init)
                else:
                    primitive_device = CommunicatingDevice(dev_id, f"Comm_Cplx2_{zone_name}_{i+1}", **common_args_init)
                if primitive_device:
                    setattr(primitive_device, 'zone', zone_name)
                    primitive_device.balance = base_starting_balance + random.randint(-200, 50)
                    primitive_device.min_acceptable_income_threshold = min_income_per_period
                    primitive_device.sim_metrics_ref = self.metrics
                    self.devices.append(primitive_device)
                    if self.framework_variant in ["social_basic", "full_siot"]:
                        zone_controller.add_worker(primitive_device, constraints={'role': f'{primitive_device.__class__.__name__}_in_{zone_name}'})
        actual_device_count = len(self.devices)
        self.metrics['device_cycles_working'] = {dev.device_id: 0 for dev in self.devices}
        self.metrics['device_cycles_idle'] = {dev.device_id: 0 for dev in self.devices}
        if self.framework_variant in ["social_basic", "full_siot"]:
            all_composites = ([self.bms] if self.bms else []) + list(self.zone_controllers.values())
            for i_comp in range(len(all_composites)):
                for j_comp in range(i_comp + 1, len(all_composites)):
                    if random.random() < 0.5:
                        all_composites[i_comp].add_relationship('work_with_me', all_composites[j_comp])
                        all_composites[j_comp].add_relationship('work_with_me', all_composites[i_comp])
            for dev in self.devices:
                if isinstance(dev, (SensingDevice, ActuatingDevice)) and random.random() < 0.4:
                    dev_zone = getattr(dev, 'zone', None)
                    if dev_zone:
                        potential_backups = [d for d in self.devices if d != dev and getattr(d, 'zone', None) == dev_zone and type(d) == type(dev) and d.device_id != dev.device_id]
                        if potential_backups:
                            backup_dev = random.choice(potential_backups)
                            dev.add_relationship('back_me', backup_dev)
        self.logger.log_info(self.run_context_name, f"Total devices for ComplexV2 Sim: {actual_device_count}. Framework: {self.framework_variant}")

    def _generate_jobs(self):
        # ... (Same as BuildingSimulationComplex) ...
        if self.current_minute % (self.scheduled_job_interval // 2) == 0:
            for zone in self.zones:
                if random.random() < 0.5: 
                    job_type = "HVAC_ADJUST"
                    target_temp = random.randint(19, 24)
                    current_temp_sim = target_temp + random.randint(-4, 4) 
                    params = {'target_temp': target_temp, 'current_temp_simulated': current_temp_sim, 'reason': "Scheduled Comfort/Occupancy"}
                    work = random.randint(8, 15) 
                    deadline = self.current_minute + random.randint(work + 5, work + 25) 
                    reward = work * 8 + (25 - abs(target_temp - 21)*3) 
                    priority = 2 
                    if random.random() < 0.25: params['priority_override'] = 1; priority = 1 
                    job = BuildingJob(self._get_next_job_id(), self.current_minute, job_type, zone, work, deadline, int(reward), params, priority=priority)
                    self.job_queue.append(job)
                    self.metrics['jobs_generated'] += 1

        if random.random() < self.event_trigger_chance : 
            num_access_attempts = random.randint(1, max(2, self.num_zones // 2 + 1)) 
            for _ in range(num_access_attempts):
                target_zone_for_access = random.choice(self.zones)
                job_type = "ACCESS_REQUEST"
                user_id = f"user{random.randint(101,150)}" 
                params = {'user_id': user_id, 'door_id': f"Door_{target_zone_for_access}_MainEntry", 'access_level_required': random.randint(1,3)}
                work = random.randint(3,6) 
                deadline = self.current_minute + random.randint(2, 4) 
                reward = work * 7
                priority = 1 
                job = BuildingJob(self._get_next_job_id(), self.current_minute, job_type, target_zone_for_access, work, deadline, reward, params, priority=priority)
                self.job_queue.append(job)
                self.metrics['jobs_generated'] += 1

        if self.current_minute > 0 and self.current_minute % (self.time_frame // 5) == 0 and random.random() < 0.75: 
            influx_zone = random.choice(self.zones)
            num_influx = random.randint(int(max(3,self.devices_per_zone_avg) * self.sudden_workload_multiplier),
                                        int(max(4,self.devices_per_zone_avg * 2) * self.sudden_workload_multiplier))
            self.logger.log_info(self.run_context_name, f"SUDDEN INFLUX of {num_influx} access requests for {influx_zone}")
            for i in range(num_influx):
                job = BuildingJob(self._get_next_job_id(), self.current_minute, "ACCESS_REQUEST", influx_zone,
                                  random.randint(2,4), self.current_minute + 1 + i//4, 
                                  10, {'user_id': f"influx_user{i}", 'door_id': f"Door_{influx_zone}_Entry{i%2+1}"}, priority=1)
                self.job_queue.append(job)
                self.metrics['jobs_generated'] += 1

        if self.current_minute > 0 and self.current_minute % self.scheduled_job_interval == 0: 
            if random.random() < 0.45: 
                target_zone_energy = random.choice(self.zones + [None]) 
                job_type = "OPTIMIZE_ZONE_ENERGY" if target_zone_energy else "BUILDING_ENERGY_STRATEGY"
                params = {'reason': "Scheduled Review/Optimization"}
                if target_zone_energy and random.random() < 0.6:
                    params['target_reduction_kwh_simulated'] = random.uniform(0.5, 2.0) 
                elif not target_zone_energy: 
                    params['mode'] = random.choice(["PEAK_DEMAND_AVOIDANCE", "NIGHT_SETBACK", "LOAD_BALANCING"])
                work = random.randint(10, 25) if target_zone_energy else random.randint(15,30) 
                deadline = self.current_minute + random.randint(work + 10, work + 45) 
                reward = work * 6
                priority = 3 
                job = BuildingJob(self._get_next_job_id(), self.current_minute, job_type, target_zone_energy, work, deadline, reward, params, priority=priority)
                self.job_queue.append(job)
                self.metrics['jobs_generated'] += 1
        self.job_queue = deque(sorted(list(self.job_queue), key=lambda j: (j.priority, j.deadline_time)))


    def _assign_jobs_to_devices(self):
        # ... (Same as BuildingSimulationComplex) ...
        jobs_assigned_this_round_ids = set()
        for job in list(self.job_queue):
            if job.id in jobs_assigned_this_round_ids or job.status != "PENDING":
                continue
            assigned_entity: Optional[Device] = None
            if self.framework_variant in ["social_basic", "full_siot"]:
                target_controller: Optional[Device] = None
                if job.target_zone is None and self.bms: 
                    target_controller = self.bms
                    if self.bms and not getattr(self.bms, 'current_job_id', None) and self.bms.current_load < self.bms.max_load * 0.75:
                        if job.job_type in self.bms.capabilities: 
                            assigned_entity = self.bms
                        else: pass 
                    target_controller = self.bms 
                elif job.target_zone in self.zone_controllers:
                    zc = self.zone_controllers[job.target_zone]
                    if not getattr(zc, 'current_job_id', None) and zc.current_load < zc.max_load * 0.85:
                        assigned_entity = zc
                    target_controller = zc
                if assigned_entity: pass
            else: 
                candidate_devices_in_zone = [
                    d for d in self.devices
                    if (job.target_zone is None or getattr(d,'zone', None) == job.target_zone) and
                       not getattr(d, 'current_job_id', None) and
                       d.current_load < d.max_load * 0.90 
                ]
                if not candidate_devices_in_zone and job.target_zone is not None:
                    candidate_devices_in_zone = [d for d in self.devices if not getattr(d, 'current_job_id', None) and d.current_load < d.max_load * 0.90]
                if candidate_devices_in_zone:
                    suitable_devices = []
                    if "HVAC" in job.job_type or "TEMP" in job.job_type: suitable_devices = [d for d in candidate_devices_in_zone if isinstance(d, (ActuatingDevice, SensingDevice, CompositeDevice)) and any(cap in d.capabilities for cap in ["hvac_control", "temperature", "manage_hvac"])]
                    elif "LIGHT" in job.job_type: suitable_devices = [d for d in candidate_devices_in_zone if isinstance(d, (ActuatingDevice, SensingDevice, CompositeDevice)) and any(cap in d.capabilities for cap in ["light_switch", "light_level", "manage_lighting"])]
                    elif "ACCESS" in job.job_type: suitable_devices = [d for d in candidate_devices_in_zone if isinstance(d, CardReaderSensor) or (isinstance(d, ActuatingDevice) and "door_lock" in d.actuator_type) or (isinstance(d, CompositeDevice) and "access" in d.capabilities)]
                    elif "ENERGY" in job.job_type: suitable_devices = [d for d in candidate_devices_in_zone if isinstance(d, PowerMeterSensor) or isinstance(d, SmartPlugActuator) or (isinstance(d, CompositeDevice) and "energy" in d.capabilities)]
                    if not suitable_devices: suitable_devices = candidate_devices_in_zone 
                    if suitable_devices: assigned_entity = min(suitable_devices, key=lambda d: d.current_load) 
            if assigned_entity:
                job.assigned_to_device_id = assigned_entity.device_id
                job.status = "ASSIGNED"
                setattr(assigned_entity, 'current_job_id', job.id)
                self.metrics['jobs_assigned'] += 1
                self.active_jobs[job.id] = job
                if job in self.job_queue: self.job_queue.remove(job)
                jobs_assigned_this_round_ids.add(job.id)
                self.logger.log_info(self.run_context_name, f"Job {job.id} ({job.job_type} P{job.priority} for {job.target_zone if job.target_zone else 'BUILDING'}) assigned to {assigned_entity.nameShort()}")
        self.job_queue = deque(sorted(list(self.job_queue), key=lambda j: (j.priority, j.deadline_time)))

    def _process_device_job(self, device: Device, job: BuildingJob):
        # ... (Same as BuildingSimulationComplex, including the fix for log_event calls) ...
        if device.current_load >= device.max_load * 0.95:
            self.logger.log_info(self.run_context_name, f"Device {device.nameShort()} on Job {job.id} is CRITICALLY OVERLOADED (load: {device.current_load}), no progress.")
            self.metrics['device_cycles_idle'][device.device_id] +=1
            return

        base_work_load = 15 if isinstance(device, CompositeDevice) else 8
        if not device.consume_load(base_work_load):
            self.logger.log_info(self.run_context_name, f"Device {device.nameShort()} on Job {job.id} FAILED to consume its base work load {base_work_load}.")
            self.metrics['device_cycles_idle'][device.device_id] +=1
            return

        work_units_completed_this_cycle = 0.0
        job_failed_internally_this_cycle = False
        task_details_for_subtask = {
            'original_job_id': job.id,
            'original_job_priority': job.priority,
            'iot_app_reward_for_subtask': job.base_reward / job.work_units_required if job.work_units_required > 0 else 0
        }

        if self.framework_variant == "baseline":
            if isinstance(device, CompositeDevice) and job.work_units_required > 5: 
                work_units_completed_this_cycle = random.uniform(0.3, 0.8) 
            elif not isinstance(device, CompositeDevice) and job.job_type not in device.capabilities:
                work_units_completed_this_cycle = random.uniform(0.1, 0.4) 
                device.log_debug(f"Baseline primitive {device.nameShort()} struggling with complex job {job.job_type}", context_override=self.run_context_name)
            else:
                work_units_completed_this_cycle = 1.0 
        elif self.framework_variant in ["social_basic", "full_siot"]:
            if isinstance(device, CompositeDevice): 
                if device == self.bms and job.target_zone is None: 
                    if job.job_type == "BUILDING_ENERGY_STRATEGY":
                        self.logger.log_info(self.run_context_name, f"BMS {device.nameShort()} processing {job.job_type} for job {job.id}")
                        successful_zc_coordination = 0
                        for zc_name, zc_device in self.zone_controllers.items():
                            self.metrics['delegation_to_zone_controller_count'] +=1 
                            zc_sub_task_details = {**task_details_for_subtask, 'bms_directive': job.parameters.get('mode', "OPTIMIZE"), 'target_zone_for_zc': zc_name}
                            outcome = zc_device.handle_request(device, "OPTIMIZE_ZONE_ENERGY", load_requested=job.work_units_required // len(self.zone_controllers), details=zc_sub_task_details)
                            device.update_trust_from_qoe(zc_device, "OPTIMIZE_ZONE_ENERGY", outcome.get('measured_qos_for_requestor', {}), "requester")
                            job.sub_task_results.append({f'zc_{zc_name}_outcome': outcome})
                            if outcome.get('success'):
                                successful_zc_coordination += 1
                        if successful_zc_coordination >= len(self.zone_controllers) * 0.5: 
                             work_units_completed_this_cycle = 1.0 * (successful_zc_coordination / len(self.zone_controllers)) 
                        else:
                            job_failed_internally_this_cycle = True
                            self.logger.log_warning(self.run_context_name, f"BMS Job {job.id} failed, insufficient ZC coordination.")
                    else: 
                        work_units_completed_this_cycle = random.uniform(0.6, 1.1) 
                elif hasattr(device, 'zone') and device == self.zone_controllers.get(job.target_zone): 
                    self.logger.log_info(self.run_context_name, f"ZC {device.nameShort()} processing {job.job_type} for job {job.id} in zone {job.target_zone}")
                    if job.job_type == "HVAC_ADJUST":
                        outcome_details = device._delegate_to_worker('sense', device, 5, {**task_details_for_subtask, 'sensor_type': 'temperature'}) 
                        job.sub_task_results.append({'hvac_sense': outcome_details})
                        if outcome_details.get('success'):
                            current_temp = outcome_details.get('value', job.parameters.get('current_temp_simulated', 25))
                            target_temp = job.parameters.get('target_temp', 22)
                            if isinstance(current_temp, (int,float)) and abs(current_temp - target_temp) > 0.5: 
                                act_details = {**task_details_for_subtask, 'command': {'mode': "HEAT" if current_temp < target_temp else "COOL", 'setpoint': target_temp}, 'actuator_type': 'hvac_control'}
                                act_outcome = device._delegate_to_worker('actuate', device, 10, act_details)
                                job.sub_task_results.append({'hvac_actuate': act_outcome})
                                if act_outcome.get('success'): work_units_completed_this_cycle = 1.0
                                else: job_failed_internally_this_cycle = True
                            elif not isinstance(current_temp, (int,float)):
                                self.logger.log_warning(self.run_context_name, f"HVAC Job {job.id} received non-numeric temp: {current_temp} from sensor.")
                                job_failed_internally_this_cycle = True
                            else: 
                                work_units_completed_this_cycle = 1.0 
                                job.sub_task_results.append({'hvac_already_optimal': True})
                        else: job_failed_internally_this_cycle = True
                    elif job.job_type == "ACCESS_REQUEST":
                        swipe_outcome = device._delegate_to_worker('sense', device, 5, {**task_details_for_subtask, 'sensor_type': 'card_swipe', 'simulated_card_user': job.parameters.get('user_id')})
                        job.sub_task_results.append({'access_swipe': swipe_outcome})
                        if swipe_outcome.get('success'):
                            card_data = swipe_outcome.get('value')
                            access_granted = (job.parameters.get('user_id') in str(card_data) and random.random() < 0.98)
                            if self.framework_variant == "full_siot":
                                if device.trust_score < 40 and job.parameters.get('access_level_required',1) > 2 :
                                    access_granted = False; self.metrics['failed_negotiations'] += 1
                                    self.logger.log_info(self.run_context_name, f"Job {job.id} access denied by ZC policy (low ZC trust, high level req).")
                            if access_granted:
                                unlock_outcome = device._delegate_to_worker('actuate', device, 5, {**task_details_for_subtask, 'command': "UNLOCK", 'actuator_type': 'door_lock'})
                                job.sub_task_results.append({'access_unlock': unlock_outcome})
                                if unlock_outcome.get('success'): work_units_completed_this_cycle = 1.0
                                else: job_failed_internally_this_cycle = True
                            else: 
                                job.sub_task_results.append({'access_denied_policy': True}); work_units_completed_this_cycle = 1.0
                        else: job_failed_internally_this_cycle = True
                    elif job.job_type == "OPTIMIZE_ZONE_ENERGY":
                        power_reading_outcome = device._delegate_to_worker('sense', device, 5, {**task_details_for_subtask, 'sensor_type': 'power_usage'})
                        job.sub_task_results.append({'energy_sense_power': power_reading_outcome})
                        if power_reading_outcome.get('success'):
                            if power_reading_outcome.get('value', 0) > 2.0 : 
                                plug_off_outcome = device._delegate_to_worker('actuate', device, 5, {**task_details_for_subtask, 'actuator_type': 'smart_plug', 'command': 'OFF'})
                                job.sub_task_results.append({'energy_actuate_plug': plug_off_outcome})
                                if plug_off_outcome.get('success'): work_units_completed_this_cycle = 1.0
                                else: work_units_completed_this_cycle = 0.5 
                            else: work_units_completed_this_cycle = 1.0 
                        else: job_failed_internally_this_cycle = True
                    else: 
                        work_units_completed_this_cycle = random.uniform(0.7, 1.2)
                elif not isinstance(device, CompositeDevice):
                    if job.job_type in device.capabilities or \
                       (job.job_type == 'sense' and isinstance(device, SensingDevice)) or \
                       (job.job_type == 'actuate' and isinstance(device, ActuatingDevice)):
                        outcome = device.handle_request(None, job.job_type, job.work_units_required, {**task_details_for_subtask, **job.parameters})
                        if outcome.get('success'):
                            work_units_completed_this_cycle = 1.0
                        else:
                            work_units_completed_this_cycle = 0.2 
                            job_failed_internally_this_cycle = True 
                    else:
                        work_units_completed_this_cycle = 0.1 
                        job_failed_internally_this_cycle = True
            else: 
                 work_units_completed_this_cycle = 0.5

        if not job_failed_internally_this_cycle:
            job.work_units_done += work_units_completed_this_cycle
            self.metrics['total_work_units_processed'] += work_units_completed_this_cycle
            self.metrics['device_cycles_working'][device.device_id] +=1
            if work_units_completed_this_cycle > 0:
                device.log_info(f"on Job {job.id} P{job.priority}: {job.work_units_done:.1f}/{job.work_units_required} WU. Load: {device.current_load}", context_override=self.run_context_name)
            elif not job_failed_internally_this_cycle: 
                device.log_debug(f"on Job {job.id} P{job.priority}: NO PROGRESS this cycle. Load: {device.current_load}", context_override=self.run_context_name)
        else: 
             self.metrics['device_cycles_idle'][device.device_id] +=1

        if job_failed_internally_this_cycle and job.status == "IN_PROGRESS":
            job.status = "FAILED_INTERNAL"
            job.completion_time = self.current_minute
            self.metrics['jobs_failed_internal'] += 1
            device.receive_penalty(job.penalty_for_failure * 0.75, "System", f"Job {job.id} failed due to internal sub-task failure.") 
            self.metrics['total_penalties_incurred'] += job.penalty_for_failure * 0.75
            self.logger.log_info(self.run_context_name, f"Job {job.id} ({job.job_type} P{job.priority}) FAILED INTERNALLY on {device.nameShort()}.")
            self.processed_jobs.append(job)
            if job.id in self.active_jobs: del self.active_jobs[job.id]
            setattr(device, 'current_job_id', None)
            return

        if job.work_units_done >= job.work_units_required:
            job.completion_time = self.current_minute
            status_log_prefix = f"Job {job.id} ({job.job_type} P{job.priority})"
            if self.current_minute <= job.deadline_time:
                job.status = "COMPLETED_ON_TIME"
                self.metrics['jobs_completed_on_time'] += 1
                device.receive_income(job.base_reward, f"{status_log_prefix} on time")
                self.metrics['total_rewards_earned'] += job.base_reward
                self.logger.log_info(self.run_context_name, f"{status_log_prefix} COMPLETED ON TIME by {device.nameShort()}. Reward: {job.base_reward}")
            else:
                job.status = "COMPLETED_LATE"
                self.metrics['jobs_completed_late'] += 1
                reduced_reward = int(job.base_reward * 0.6)
                device.receive_income(reduced_reward, f"{status_log_prefix} late")
                self.metrics['total_rewards_earned'] += reduced_reward
                self.logger.log_info(self.run_context_name, f"{status_log_prefix} COMPLETED LATE by {device.nameShort()}. Reward: {reduced_reward}")
            self.processed_jobs.append(job)
            if job.id in self.active_jobs: del self.active_jobs[job.id]
            setattr(device, 'current_job_id', None)
        elif self.current_minute > job.deadline_time and job.status == "IN_PROGRESS":
            job.status = "FAILED_DEADLINE"
            job.completion_time = self.current_minute
            self.metrics['jobs_failed_deadline'] += 1
            device.receive_penalty(job.penalty_for_failure, "System", f"Job {job.id} missed deadline")
            self.metrics['total_penalties_incurred'] += job.penalty_for_failure
            self.logger.log_info(self.run_context_name, f"Job {job.id} ({job.job_type} P{job.priority}) FAILED DEADLINE on {device.nameShort()}. Penalty: {job.penalty_for_failure}")
            self.processed_jobs.append(job)
            if job.id in self.active_jobs: del self.active_jobs[job.id]
            setattr(device, 'current_job_id', None)

    def simulate_cycle(self, minute: int):
        self.current_minute = minute
        self.logger.log_info(self.run_context_name, f"Minute: {self.current_minute} ({self.framework_variant})")
        self._generate_jobs() 
        self._assign_jobs_to_devices() 
        active_job_ids_processed_this_cycle = set()
        for device in self.devices:
            current_job_id_attr = getattr(device, 'current_job_id', None)
            if current_job_id_attr and current_job_id_attr in self.active_jobs:
                job = self.active_jobs[current_job_id_attr]
                if job.assigned_to_device_id == device.device_id and job.status in ["ASSIGNED", "IN_PROGRESS"]:
                    if job.status == "ASSIGNED":
                        job.status = "IN_PROGRESS"
                        self.logger.log_info(self.run_context_name, f"Device {device.nameShort()} starting Job {job.id} ({job.job_type} P{job.priority})")
                    if job.status == "IN_PROGRESS": 
                        self._process_device_job(device, job)
                        active_job_ids_processed_this_cycle.add(job.id) 
                elif job.assigned_to_device_id != device.device_id and current_job_id_attr == job.id:
                    self.logger.log_warning(self.run_context_name, f"Device {device.nameShort()} thought it had job {job.id}, but job is assigned to {job.assigned_to_device_id}. Clearing.")
                    setattr(device, 'current_job_id', None)
            else: 
                 if current_job_id_attr and current_job_id_attr not in self.active_jobs: 
                     setattr(device, 'current_job_id', None)
                 self.metrics['device_cycles_idle'][device.device_id] +=1
                 if self.framework_variant in ["social_basic", "full_siot"] and random.random() < 0.02 and len(self.devices) > 1: 
                    requestor = device
                    potential_targets = [rel['device'] for rel in requestor.relationships.get('work_with_me', []) if rel.get('status')=='active' and rel['device'] != requestor]
                    if not potential_targets:
                        potential_targets = [d for d in self.devices if d != requestor and not any(r.get('device')==requestor for r in d.relationships.get('avoid_me',[]))]
                    if potential_targets:
                        target_performer = random.choice(potential_targets)
                        requested_task = random.choice(target_performer.capabilities) if target_performer.capabilities else random.choice(['sense', 'actuate', 'transmit'])
                        load_for_task = random.randint(2,5)
                        details = {'iot_app_reward': 0, 'message': f"Bldg background ping from {requestor.nameShort()}", 'is_background_task': True, 'simulated_command': 'STATUS_CHECK'}
                        if requested_task == 'transmit' and isinstance(target_performer, CommunicatingDevice): details['target_comm_device'] = target_performer
                        outcome = target_performer.handle_request(requestor, requested_task, load_for_task, details)
                        if 'measured_qos_for_requestor' in outcome:
                            requestor.update_trust_from_qoe(target_performer, requested_task, outcome['measured_qos_for_requestor'], "requester")
            device.reduce_load(random.randint(5,10)) 
            if self.current_minute > 0 and self.current_minute % self.metrics['min_income_check_interval'] == 0:
                device.check_min_income_satisfied()
        for job in list(self.job_queue):
            if job.status == "PENDING" and self.current_minute > job.deadline_time and job.id not in active_job_ids_processed_this_cycle:
                job.status = "FAILED_DEADLINE_UNASSIGNED"
                self.metrics['jobs_failed_deadline'] += 1
                self.logger.log_info(self.run_context_name, f"Job {job.id} ({job.job_type} P{job.priority}) FAILED DEADLINE (unassigned from queue).")
                self.processed_jobs.append(job)
                if job in self.job_queue: self.job_queue.remove(job)
        self.logger.log_info(self.run_context_name, f"Minute: {self.current_minute} | Pending Jobs: {len(self.job_queue)} | Active Jobs: {len(self.active_jobs)}")

    def run(self):
        self.setup_devices()
        for minute_cycle in range(self.time_frame):
            self.simulate_cycle(minute_cycle)
            if minute_cycle > 0 and (minute_cycle % (self.time_frame // 20 if self.time_frame >=20 else 1) == 0 or minute_cycle == self.time_frame -1) :
                 failed_total = self.metrics['jobs_failed_deadline'] + self.metrics['jobs_failed_internal']
                 self.logger.log_info(self.run_context_name, f"Min {minute_cycle} | Jobs (Pend/Act/Fail): {len(self.job_queue)}/{len(self.active_jobs)}/{failed_total} | Comp(OK/Late):{self.metrics['jobs_completed_on_time']}/{self.metrics['jobs_completed_late']}")
        self.report()

    def report(self):
        report_context = f"BldgCplxV2Report_{self.framework_variant}"
        self.logger.log_info(report_context, "\n" + "="*25 + f" BUILDING SIMULATION COMPLEX V2 FINAL REPORT ({self.framework_variant}) " + "="*25)
        
        # Ensure total_policy_violations_blamed is calculated
        self.metrics['total_policy_violations_blamed'] = sum(d.blame_count for d in self.devices if hasattr(d, 'blame_count'))

        total_completed = self.metrics['jobs_completed_on_time'] + self.metrics['jobs_completed_late']
        if total_completed > 0:
            completion_times = [job.completion_time - job.creation_time for job in self.processed_jobs if job.status.startswith("COMPLETED") and job.completion_time != -1 and hasattr(job, 'creation_time') and job.creation_time != -1]
            self.metrics['avg_job_completion_time'] = sum(completion_times) / len(completion_times) if completion_times else 0.0
            late_jobs = [job for job in self.processed_jobs if job.status == "COMPLETED_LATE" and job.completion_time != -1 and hasattr(job, 'deadline_time') and job.deadline_time != -1]
            tardiness_values = [job.completion_time - job.deadline_time for job in late_jobs if job.completion_time > job.deadline_time] 
            self.metrics['avg_job_tardiness'] = sum(tardiness_values) / len(tardiness_values) if tardiness_values else 0.0
        else:
            self.metrics['avg_job_completion_time'] = 0.0
            self.metrics['avg_job_tardiness'] = 0.0
        self.metrics['final_total_balance_network'] = sum(d.balance for d in self.devices if hasattr(d, 'balance'))
        self.metrics['total_income_generated_network'] = sum(d.total_income_earned for d in self.devices if hasattr(d, 'total_income_earned'))
        avg_trust_val_report = "N/A"
        if self.framework_variant in ["social_basic", "full_siot"] and self.devices:
            trust_scores = [d.trust_score for d in self.devices if hasattr(d, 'trust_score')]
            if trust_scores:
                avg_trust_val_report = sum(trust_scores) / len(trust_scores)
                self.metrics['avg_trust_at_end'] = avg_trust_val_report
            else: self.metrics['avg_trust_at_end'] = "N/A (No scores)"
        else: self.metrics['avg_trust_at_end'] = "N/A (Baseline)"
        avg_trust_display = f"{self.metrics['avg_trust_at_end']:.2f}" if isinstance(self.metrics['avg_trust_at_end'], float) else str(self.metrics['avg_trust_at_end'])
        summary_report_lines = [
            f"Framework Variant: {self.framework_variant}",
            f"Duration: {self.time_frame}m | Devices: {len(self.devices)} | Zones: {self.num_zones}",
            "--- Job Statistics ---",
            f"Jobs Generated: {self.metrics['jobs_generated']}",
            f"Jobs Assigned: {self.metrics['jobs_assigned']}",
            f"Jobs Completed On Time: {self.metrics['jobs_completed_on_time']}",
            f"Jobs Completed Late: {self.metrics['jobs_completed_late']}",
            f"Jobs Failed (Deadline or Internal): {self.metrics['jobs_failed_deadline'] + self.metrics['jobs_failed_internal']}",
            f"Total Work Units Processed: {self.metrics['total_work_units_processed']:.1f}",
            f"Avg Job Completion Time (for completed): {self.metrics['avg_job_completion_time']:.2f} min",
            f"Avg Job Tardiness (for late): {self.metrics['avg_job_tardiness']:.2f} min",
            "--- Device & Network Monetary & Trust ---",
            f"Total Rewards Earned by Devices (from jobs): {self.metrics['total_rewards_earned']:.0f}",
            f"Total Penalties Incurred by Devices (from jobs): {self.metrics['total_penalties_incurred']:.0f}",
            f"Final Total Network Balance: {self.metrics['final_total_balance_network']:.0f}",
            f"Average Final Trust (Social Modes only): {avg_trust_display}",
            "--- SIoT & Behavior Metrics ---", 
            f"Delegations to Zone Controllers (by BMS): {self.metrics['delegation_to_zone_controller_count']}",
            f"Delegations to Primitives (by ZC/BMS): {self.metrics['delegation_to_primitive_count']}",
            f"Successful Back-me Invocations: {self.metrics['back_me_invocations_successful']}",
            f"Failed Back-me Invocations: {self.metrics.get('back_me_invocations_failed', 0)}",
            f"Successful Negotiations (Full SIoT): {self.metrics['successful_negotiations']}",
            f"Failed Negotiations (Full SIoT): {self.metrics['failed_negotiations']}",
            f"Misuse Incidents Detected (Full SIoT): {self.metrics['misuse_incidents_detected']}",
            f"Selfish Rejections: {self.metrics.get('selfish_rejections',0)}", 
            f"Faulty Device Actions Failed: {self.metrics.get('faulty_device_actions_failed',0)}",
            f"Unresponsive Device Rejections: {self.metrics.get('unresponsive_device_rejections',0)}",
            f"Total Policy Violations Blamed: {self.metrics.get('total_policy_violations_blamed',0)}"
        ]
        self.logger.log_info(report_context, "\n".join(summary_report_lines))
        self.logger.store_simulation_metrics(
            simulation_run_key=f"building_complex_v2_{self.framework_variant.lower()}", 
            metrics_dict=self.metrics
        )
        self.logger.log_info(report_context, "="*70)

