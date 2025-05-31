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
# Corrected import: Use ScenarioJob from scenario_loader
from .scenario_loader import ScenarioJob as BuildingJob 

# Specialized device classes (can be defined here or imported if they are generic enough)
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

# BuildingJob is now an alias for ScenarioJob from scenario_loader

class BuildingSimulationComplex_V3:
    def __init__(self,
                 framework_variant: str,
                 duration_minutes: int,
                 logger_instance: SimulationLogger,
                 run_context_name: str,
                 device_config: Dict[str, Any], 
                 pregenerated_job_list: List[BuildingJob] # This will be List[ScenarioJob]
                ):

        self.framework_variant = framework_variant
        self.num_zones = device_config["num_zones"]
        self.primitives_per_zone_dist = device_config["primitives_per_zone_dist"]
        self.behavioral_config = device_config["behavioral_config"]
        
        self.num_devices_approx = 1 + self.num_zones + sum(self.primitives_per_zone_dist)

        self.devices: List[Device] = []
        self.zone_controllers: Dict[str, CompositeDevice] = {}
        self.bms: Optional[CompositeDevice] = None
        self.zones: List[str] = [f"Zone{i+1}" for i in range(self.num_zones)]

        self.time_frame = duration_minutes
        self.run_context_name = run_context_name
        self.logger = logger_instance
        self.current_minute = 0

        self.job_master_list = deque(pregenerated_job_list) 
        self.job_queue: deque[BuildingJob] = deque() 
        self.active_jobs: Dict[str, BuildingJob] = {}
        self.processed_jobs: List[BuildingJob] = []
        
        self.metrics: Dict[str, Any] = {
            'framework_variant': framework_variant,
            'jobs_generated': len(pregenerated_job_list),
            'jobs_assigned':0, 'jobs_completed_on_time': 0,
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
        self.logger.log_info(self.run_context_name, f"BuildingSimulationComplex_V3 ({self.framework_variant}) | Devices: {self.num_devices_approx} | Zones: {self.num_zones} | Primitives/Zone: {self.primitives_per_zone_dist} | Total Pregen Jobs: {len(pregenerated_job_list)} | Duration: {self.time_frame}m")

    def _get_device_by_id(self, device_id: Optional[str]) -> Optional[Device]:
        if not device_id: return None
        for dev in self.devices:
            if dev.device_id == device_id:
                return dev
        return None

    def _assign_behavioral_params(self, target_counts: Dict[str, int], is_composite: bool = False) -> Dict:
        b_config = self.behavioral_config
        params = {
            'behavior_profile': "normal",
            'fault_probability': 0.0,
            'unresponsive_probability': 0.0,
            'deception_factor': 1.0,
            'unresponsive_duration_range': b_config.get('default_unresponsive_duration_range', (5,15))
        }
        profile_rand_factor = 0.8 if is_composite else 1.0 
        assigned_profile = False
        profile_roll = random.random()
        
        if target_counts['selfish'] > 0 and profile_roll < b_config['target_selfish_ratio'] * profile_rand_factor:
            params['behavior_profile'] = 'selfish'; assigned_profile=True
            target_counts['selfish'] -=1
        elif not assigned_profile and target_counts['deceptive'] > 0 and profile_roll < (b_config['target_selfish_ratio'] + b_config['target_deceptive_ratio']) * profile_rand_factor:
            params['behavior_profile'] = 'deceptive'; assigned_profile=True
            target_counts['deceptive'] -=1
        elif not assigned_profile and target_counts['policy_violator'] > 0 and profile_roll < (b_config['target_selfish_ratio'] + b_config['target_deceptive_ratio'] + b_config['target_policy_violator_ratio']) * profile_rand_factor:
            params['behavior_profile'] = 'policy_violator'; assigned_profile=True
            target_counts['policy_violator'] -=1
        
        # Use a different random roll for these independent characteristics
        if target_counts['faulty'] > 0 and random.random() < 0.25 : # Approx 25% of remaining devices targeted for faults get it
            params['fault_probability'] = random.uniform(*b_config['default_fault_probability_range'])
            target_counts['faulty'] -=1
        
        if target_counts['unresponsive'] > 0 and random.random() < 0.20: # Approx 20% of remaining devices targeted for unresponsiveness get it
            params['unresponsive_probability'] = random.uniform(*b_config['default_unresponsive_probability_range'])
            params['unresponsive_duration_range'] = (random.randint(3,8), random.randint(10,20))
            target_counts['unresponsive'] -=1

        if params['behavior_profile'] == 'deceptive':
            params['deception_factor'] = random.uniform(*b_config['default_deception_factor_range'])
        return params
        
    def setup_devices(self):
        dev_id_counter = 0
        base_starting_balance = 1000
        min_income_per_period = self.metrics.get('min_income_check_interval', 60) * 0.5
        b_config = self.behavioral_config
        behavior_target_counts = {
            'selfish': int(self.num_devices_approx * b_config['target_selfish_ratio']),
            'deceptive': int(self.num_devices_approx * b_config['target_deceptive_ratio']),
            'policy_violator': int(self.num_devices_approx * b_config['target_policy_violator_ratio']),
            'faulty': int(self.num_devices_approx * b_config['target_faulty_ratio']),
            'unresponsive': int(self.num_devices_approx * b_config['target_unresponsive_ratio'])
        }

        bms_id = f"bldg_cplx3_bms_{dev_id_counter}"; dev_id_counter+=1
        bms_behavior_params = self._assign_behavioral_params(behavior_target_counts, is_composite=True)
        
        self.bms = CompositeDevice(bms_id, "CentralBMS_CplxV3", max_load=500,
                                   capabilities=["coordinate_zones", "set_global_policy", "emergency_response", "energy_management", "assign_global_jobs"],
                                   framework_variant=self.framework_variant, logger_instance=self.logger, current_minute_provider=lambda: self.current_minute,
                                   **bms_behavior_params)
        self.bms.balance = base_starting_balance * 2
        self.bms.min_acceptable_income_threshold = min_income_per_period * 2
        self.bms.sim_metrics_ref = self.metrics
        self.devices.append(self.bms)
        self.logger.log_info(self.run_context_name, f"Created {self.bms.nameShort()} with profile: {self.bms.behavior_profile}, fault_prob: {self.bms.fault_probability:.2f}, unresp_prob: {self.bms.unresponsive_probability:.2f}")

        for zone_idx, zone_name in enumerate(self.zones):
            zc_id = f"bldg_cplx3_zc{zone_idx+1}_{dev_id_counter}"; dev_id_counter+=1
            zc_behavior_params = self._assign_behavioral_params(behavior_target_counts, is_composite=True)
            
            zone_controller = CompositeDevice(zc_id, f"ZoneCtrl_CplxV3_{zone_name}", max_load=250, 
                                              capabilities=["manage_hvac", "manage_lighting", "zone_security_local", "delegate_zone_tasks", "access_control_zone"],
                                              framework_variant=self.framework_variant, logger_instance=self.logger, current_minute_provider=lambda: self.current_minute,
                                              **zc_behavior_params)
            setattr(zone_controller, 'zone', zone_name)
            zone_controller.balance = base_starting_balance * 1.5
            zone_controller.min_acceptable_income_threshold = min_income_per_period * 1.5
            zone_controller.sim_metrics_ref = self.metrics
            self.devices.append(zone_controller)
            self.zone_controllers[zone_name] = zone_controller
            self.logger.log_info(self.run_context_name, f"Created {zone_controller.nameShort()} for {zone_name} with profile: {zone_controller.behavior_profile}, fault_prob: {zone_controller.fault_probability:.2f}, unresp_prob: {zone_controller.unresponsive_probability:.2f}")

            if self.framework_variant in ["social_basic", "full_siot"] and self.bms:
                self.bms.add_worker(zone_controller, constraints={'role': 'zone_management', 'zone': zone_name})

            num_primitives_this_zone = self.primitives_per_zone_dist[zone_idx]
            self.logger.log_info(self.run_context_name, f"Zone {zone_name} creating {num_primitives_this_zone} primitive devices.")

            for i in range(num_primitives_this_zone):
                dev_id = f"bldg_cplx3_d{dev_id_counter}_{zone_name[:2].lower()}{i}"; dev_id_counter+=1
                primitive_behavior_params = self._assign_behavioral_params(behavior_target_counts)
                
                dev_type_roll = random.random()
                primitive_device: Optional[Device] = None
                common_args_init = {'framework_variant': self.framework_variant, 
                                'logger_instance': self.logger, 
                                'current_minute_provider': lambda: self.current_minute,
                                **primitive_behavior_params}
                if dev_type_roll < 0.4:
                    sensor_kind = random.choice(["temperature", "occupancy", "light_level", "co2", "door_contact", "window_contact", "power_meter", "card_reader"])
                    if sensor_kind == "card_reader": primitive_device = CardReaderSensor(dev_id, f"CRSens_Cplx3_{zone_name}_{i+1}", **common_args_init)
                    elif sensor_kind == "power_meter": primitive_device = PowerMeterSensor(dev_id, f"PMSens_Cplx3_{zone_name}_{i+1}", zone_name=zone_name, **common_args_init)
                    else: primitive_device = SensingDevice(dev_id, f"{sensor_kind.capitalize()}Sens_Cplx3_{zone_name}_{i+1}", sensor_type=sensor_kind, **common_args_init)
                elif dev_type_roll < 0.8:
                    actuator_kind = random.choice(["hvac_control", "light_switch", "smart_blind", "door_lock", "smart_plug", "alarm_siren"])
                    if actuator_kind == "smart_plug": primitive_device = SmartPlugActuator(dev_id, f"SPlug_Cplx3_{zone_name}_{i+1}", **common_args_init)
                    else: primitive_device = ActuatingDevice(dev_id, f"{actuator_kind.capitalize()}Act_Cplx3_{zone_name}_{i+1}", actuator_type=actuator_kind, **common_args_init)
                else:
                    primitive_device = CommunicatingDevice(dev_id, f"Comm_Cplx3_{zone_name}_{i+1}", **common_args_init)
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
        self.logger.log_info(self.run_context_name, f"Total devices for ComplexV3 Sim: {actual_device_count}. Framework: {self.framework_variant}")

    def _generate_jobs_for_current_minute(self):
        while self.job_master_list and self.job_master_list[0].creation_time <= self.current_minute:
            job = self.job_master_list.popleft()
            job.status = "PENDING" 
            self.job_queue.append(job)
            self.logger.log_info(self.run_context_name, f"Job activated from pregen list: {job.id} ({job.job_type} P{job.priority} for {job.target_zone if job.target_zone else 'BUILDING'})")
        self.job_queue = deque(sorted(list(self.job_queue), key=lambda j: (j.priority, j.deadline_time)))

    def _assign_jobs_to_devices(self):
        # ... (Logic remains same as building_simulation_complex_v2) ...
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
                        # else: BMS must delegate, job remains PENDING for BMS to pick up in _process_device_job
                    # target_controller = self.bms # Redundant
                elif job.target_zone in self.zone_controllers:
                    zc = self.zone_controllers[job.target_zone]
                    if not getattr(zc, 'current_job_id', None) and zc.current_load < zc.max_load * 0.85:
                        assigned_entity = zc
                    # target_controller = zc # Redundant
                # if assigned_entity: pass # No explicit action needed here if assigned
            else: # Baseline
                candidate_devices_in_zone = [
                    d for d in self.devices
                    if (job.target_zone is None or getattr(d,'zone', None) == job.target_zone) and
                       not getattr(d, 'current_job_id', None) and
                       d.current_load < d.max_load * 0.90 
                ]
                if not candidate_devices_in_zone and job.target_zone is not None: # Fallback to any zone if no device in target zone
                    candidate_devices_in_zone = [d for d in self.devices if not getattr(d, 'current_job_id', None) and d.current_load < d.max_load * 0.90]
                
                if candidate_devices_in_zone:
                    suitable_devices = []
                    # Simplified capability matching for baseline
                    if "HVAC" in job.job_type or "TEMP" in job.job_type: suitable_devices = [d for d in candidate_devices_in_zone if isinstance(d, (ActuatingDevice, SensingDevice, CompositeDevice)) and any(cap in d.capabilities for cap in ["hvac_control", "temperature", "manage_hvac"])]
                    elif "LIGHT" in job.job_type: suitable_devices = [d for d in candidate_devices_in_zone if isinstance(d, (ActuatingDevice, SensingDevice, CompositeDevice)) and any(cap in d.capabilities for cap in ["light_switch", "light_level", "manage_lighting"])]
                    elif "ACCESS" in job.job_type: suitable_devices = [d for d in candidate_devices_in_zone if isinstance(d, CardReaderSensor) or (isinstance(d, ActuatingDevice) and "door_lock" in d.actuator_type) or (isinstance(d, CompositeDevice) and "access" in d.capabilities)]
                    elif "ENERGY" in job.job_type: suitable_devices = [d for d in candidate_devices_in_zone if isinstance(d, PowerMeterSensor) or isinstance(d, SmartPlugActuator) or (isinstance(d, CompositeDevice) and "energy" in d.capabilities)]
                    
                    if not suitable_devices: suitable_devices = candidate_devices_in_zone # Fallback to any if no specific capability match
                    if suitable_devices:
                        assigned_entity = min(suitable_devices, key=lambda d: d.current_load) # Least loaded

            if assigned_entity:
                job.assigned_to_device_id = assigned_entity.device_id
                job.status = "ASSIGNED"
                setattr(assigned_entity, 'current_job_id', job.id)
                self.metrics['jobs_assigned'] += 1
                self.active_jobs[job.id] = job
                if job in self.job_queue: self.job_queue.remove(job) # Remove from pending queue
                jobs_assigned_this_round_ids.add(job.id)
                self.logger.log_info(self.run_context_name, f"Job {job.id} ({job.job_type} P{job.priority} for {job.target_zone if job.target_zone else 'BUILDING'}) assigned to {assigned_entity.nameShort()}")
        
        self.job_queue = deque(sorted(list(self.job_queue), key=lambda j: (j.priority, j.deadline_time)))


    def _process_device_job(self, device: Device, job: BuildingJob):
        # ... (Logic is largely the same as BuildingSimulationComplex_V2's _process_device_job) ...
        if device.current_load >= device.max_load * 0.95:
            device.log_info(f"on Job {job.id} is CRITICALLY OVERLOADED, no progress.", context_override=self.run_context_name)
            self.metrics['device_cycles_idle'][device.device_id] +=1
            return

        base_work_load = 15 if isinstance(device, CompositeDevice) else 8
        if not device.consume_load(base_work_load):
            device.log_info(f"on Job {job.id} FAILED to consume its base work load {base_work_load}.", context_override=self.run_context_name)
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
        
        self._generate_jobs_for_current_minute() 
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
        
        # For pre-generated jobs, deadline failures for unassigned jobs are implicitly handled
        # by them not being completed by their deadline. The 'jobs_failed_deadline' metric
        # will capture jobs that were assigned but missed deadline.
        # To explicitly count jobs that were never even activated from master list by their deadline:
        # for job in list(self.job_master_list): # Check remaining master list
        #     if job.creation_time <= self.current_minute and self.current_minute > job.deadline_time:
        #         # This job should have been activated and processed but wasn't, and its deadline passed
        #         # This logic is complex as it depends on whether they *should* have been activated
        #         pass 

        self.logger.log_info(self.run_context_name, f"Minute: {self.current_minute} | Pending Jobs in Queue: {len(self.job_queue)} | Active Jobs on Devices: {len(self.active_jobs)} | Master List Remaining: {len(self.job_master_list)}")


    def run(self):
        self.setup_devices() 
        for minute_cycle in range(self.time_frame):
            self.simulate_cycle(minute_cycle)
            if minute_cycle > 0 and (minute_cycle % (self.time_frame // 20 if self.time_frame >=20 else 1) == 0 or minute_cycle == self.time_frame -1) :
                 failed_total = self.metrics['jobs_failed_deadline'] + self.metrics['jobs_failed_internal']
                 self.logger.log_info(self.run_context_name, f"Min {minute_cycle} | Jobs (Queue/Act/Fail): {len(self.job_queue)}/{len(self.active_jobs)}/{failed_total} | Comp(OK/Late):{self.metrics['jobs_completed_on_time']}/{self.metrics['jobs_completed_late']}")
        self.report()

    def report(self):
        report_context = f"BldgCplxV3Report_{self.framework_variant}" 
        self.logger.log_info(report_context, "\n" + "="*25 + f" BUILDING SIMULATION COMPLEX V3 FINAL REPORT ({self.framework_variant}) " + "="*25)
        
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
        if self.framework_variant == "full_siot" and self.devices:
            trust_scores = [d.trust_score for d in self.devices if hasattr(d, 'trust_score')]
            if trust_scores:
                avg_trust_val_report = sum(trust_scores) / len(trust_scores)
                self.metrics['avg_trust_at_end'] = avg_trust_val_report
            else: self.metrics['avg_trust_at_end'] = "N/A (No scores)"
        else: self.metrics['avg_trust_at_end'] = "N/A (Not Full SIoT)"
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
            f"Average Final Trust (Full SIoT only): {avg_trust_display}",
            "--- SIoT & Behavior Metrics ---",
            f"Delegations to Zone Controllers (by BMS): {self.metrics.get('delegation_to_zone_controller_count', 0)}",
            f"Delegations to Primitives (by ZC/BMS): {self.metrics.get('delegation_to_primitive_count', 0)}",
            f"Successful Back-me Invocations: {self.metrics.get('back_me_invocations_successful', 0)}",
            f"Failed Back-me Invocations: {self.metrics.get('back_me_invocations_failed', 0)}",
            f"Successful Negotiations (Full SIoT): {self.metrics.get('successful_negotiations', 0)}",
            f"Failed Negotiations (Full SIoT): {self.metrics.get('failed_negotiations', 0)}",
            f"Misuse Incidents Detected (Full SIoT): {self.metrics.get('misuse_incidents_detected', 0)}"
        ]
        self.logger.log_info("OVERALL_SIM_SUMMARY", "\n".join(summary_report_lines), context_override=report_context)
        self.logger.store_simulation_metrics(
            simulation_run_key=f"building_complex_v3_{self.framework_variant.lower()}", 
            metrics_dict=self.metrics
        )
        self.logger.log_info("FINAL_REPORT_END", "="*70, context_override=report_context)

