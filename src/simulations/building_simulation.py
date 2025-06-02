import random
import time
import uuid # For unique job IDs
from collections import deque # For job queue
from typing import List, Dict, Any, Optional

from src.devices.device import Device
from src.devices.sensing_device import SensingDevice
from src.devices.actuating_device import ActuatingDevice
from src.devices.communicating_device import CommunicatingDevice
from src.devices.composite_device import CompositeDevice
from src.utils.logger import SimulationLogger
from src.simulations.scenario_loader import ScenarioJob as BuildingJob
from src.simulations.building_scenario_config import BuildingScenario, DeviceConfig

# Specialized device classes (can be defined here or imported if they are generic enough)
class CardReaderSensor(SensingDevice):
    def __init__(
        self,
        device_id,
        name,
        max_load=50,
        framework_variant="full_siot",
        logger_instance=None,
        current_minute_provider=None,
        **kwargs
    ):
        super().__init__(
            device_id,
            name,
            max_load,
            sensor_type="card_swipe",
            framework_variant=framework_variant,
            logger_instance=logger_instance,
            current_minute_provider=current_minute_provider,
            **kwargs
        )
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

class BuildingSimulation:
    def __init__(self,
                 framework_variant: str,
                 scenario: BuildingScenario,
                 logger_instance: SimulationLogger,
                 run_context_name: str):

        self.framework_variant = framework_variant
        self.scenario = scenario
        self.time_frame = scenario.time_parameters.simulation_duration_minutes
        self.run_context_name = run_context_name
        self.logger = logger_instance
        self.current_minute = 0

        self.devices: List[Device] = []
        self.bms: Optional[CompositeDevice] = None
        self.zones: List[str] = [zone.zone_id for zone in scenario.zones]
        self.active_jobs: Dict[str, BuildingJob] = {}
        self.processed_jobs: List[BuildingJob] = []
        self.job_queue: List[BuildingJob] = []  # Initialize job queue
        
        # Initialize metrics
        self.metrics: Dict[str, Any] = {
            'framework_variant': framework_variant,
            'total_jobs_created': 0,
            'total_jobs_done': 0,
            'jobs_assigned': 0,
            'jobs_completed_on_time': 0,
            'jobs_completed_late': 0,
            'jobs_failed_deadline': 0,
            'jobs_failed_internal': 0,
            'total_work_units_processed': 0,
            'avg_job_completion_time': 0.0,
            'avg_job_tardiness': 0.0,
            'device_cycles_working': {},
            'device_cycles_idle': {},
            'total_rewards_earned': 0,
            'total_penalties_incurred': 0,
            'qoe_interaction_samples': [],
            'avg_trust_at_end': "N/A",
            'final_total_balance_network': 0,
            'total_income_generated_network': 0,
            'min_income_check_interval': self.time_frame // 4 if self.time_frame >= 40 else 10
        }

    def setup_devices(self):
        """Set up devices based on the scenario configuration."""
        for device_config in self.scenario.devices:
            device = self._create_device(device_config)
            if device:
                self.devices.append(device)
                self.metrics['device_cycles_working'][device.device_id] = 0
                self.metrics['device_cycles_idle'][device.device_id] = 0

    def _create_device(self, config: DeviceConfig) -> Optional[Device]:
        """Create a device based on its configuration."""
        if config.device_type == "temperature_sensor":
            device = SensingDevice(
                device_id=config.device_id,
                name=f"TempSens_{config.zone_id}",
                max_load=50,
                sensor_type="temperature",
                framework_variant=self.framework_variant,
                logger_instance=self.logger,
                current_minute_provider=lambda: self.current_minute
            )
            device.zone = config.zone_id  # Set the zone attribute
            return device
        elif config.device_type == "hvac_control":
            device = ActuatingDevice(
                device_id=config.device_id,
                name=f"HVAC_{config.zone_id}",
                max_load=100,
                actuator_type="hvac_control",
                framework_variant=self.framework_variant,
                logger_instance=self.logger,
                current_minute_provider=lambda: self.current_minute
            )
            device.zone = config.zone_id  # Set the zone attribute
            return device
        # Add more device types as needed
        return None

    def simulate_cycle(self, minute: int):
        """Simulate one minute of building operation."""
        self.current_minute = minute
        self.logger.log_info(self.run_context_name, f"Minute: {self.current_minute} ({self.framework_variant})")
        
        # Process events for this minute
        current_events = [e for e in self.scenario.generated_events if e["timestamp"] == minute]
        for event in current_events:
            self._process_event(event)
        
        # Generate dynamic jobs based on current conditions
        self._generate_dynamic_jobs()
        
        # Process active jobs
        self._process_active_jobs()
        
        # Update device states
        for device in self.devices:
            device.reduce_load(random.randint(5, 10))
            if self.current_minute > 0 and self.current_minute % self.metrics['min_income_check_interval'] == 0:
                device.check_min_income_satisfied()

    def _generate_dynamic_jobs(self):
        """Generate jobs based on current building conditions."""
        # Check temperature conditions
        self._check_temperature_conditions()
        
        # Check occupancy conditions
        self._check_occupancy_conditions()
        
        # Check energy conditions
        self._check_energy_conditions()
        
        # Check security conditions
        self._check_security_conditions()

    def _check_temperature_conditions(self):
        """Generate jobs based on temperature readings and conditions."""
        for device in self.devices:
            if isinstance(device, SensingDevice) and device.sensor_type == "temperature":
                # Get current temperature reading using handle_request
                result = device.handle_request(None, "sense", 5, {"sensor_type": "temperature"})
                if not result.get('success'):
                    continue
                
                current_temp = result.get('value')
                if current_temp is None:
                    continue
                
                # Check if temperature is outside comfort range
                zone = next((z for z in self.scenario.zones if z.zone_id == device.zone), None)
                if zone and abs(current_temp - zone.base_temperature) > 2.0:
                    # Create HVAC adjustment job
                    job = BuildingJob(
                        id=f"temp_adjust_{self.current_minute}_{device.zone}",
                        job_type="HVAC_ADJUST",
                        priority=2,
                        work_units_required=3,
                        deadline_time=self.current_minute + 10,
                        creation_time=self.current_minute,
                        target_zone=device.zone,
                        base_reward=5,
                        penalty_for_failure=50,
                        parameters={
                            "current_temp": current_temp,
                            "target_temp": zone.base_temperature,
                            "adjustment_needed": current_temp - zone.base_temperature
                        }
                    )
                    self._assign_job_to_device(job, device)

    def _check_occupancy_conditions(self):
        """Generate jobs based on occupancy changes."""
        current_hour = (self.current_minute // 60) % 24
        for zone in self.scenario.zones:
            # Get expected occupancy for current hour
            expected_occupancy = zone.occupancy_pattern.get(str(current_hour), 0.0)
            
            # Simulate actual occupancy with some variation
            actual_occupancy = random.uniform(
                max(0.0, expected_occupancy - 0.2),
                min(1.0, expected_occupancy + 0.2)
            )
            
            # If occupancy is significantly different from expected
            if abs(actual_occupancy - expected_occupancy) > 0.3:
                # Create occupancy adjustment job
                job = BuildingJob(
                    id=f"occupancy_adjust_{self.current_minute}_{zone.zone_id}",
                    job_type="OCCUPANCY_ADJUST",
                    priority=1,
                    work_units_required=2,
                    deadline_time=self.current_minute + 5,
                    creation_time=self.current_minute,
                    target_zone=zone.zone_id,
                    base_reward=4,
                    penalty_for_failure=40,
                    parameters={
                        "expected_occupancy": expected_occupancy,
                        "actual_occupancy": actual_occupancy,
                        "adjustment_needed": actual_occupancy - expected_occupancy
                    }
                )
                # Find appropriate device to handle occupancy
                occupancy_devices = [d for d in self.devices 
                                  if isinstance(d, (SensingDevice, ActuatingDevice))
                                  and getattr(d, 'zone', None) == zone.zone_id]
                if occupancy_devices:
                    self._assign_job_to_device(job, occupancy_devices[0])

    def _check_energy_conditions(self):
        """Generate jobs based on energy usage patterns."""
        for device in self.devices:
            if isinstance(device, SensingDevice) and device.sensor_type == "power_usage":
                # Get current power reading
                current_power = device.get_last_reading()
                if current_power is None:
                    continue
                
                # Check if power usage is above threshold
                if current_power > 2.0:  # kW threshold
                    # Create energy optimization job
                    job = BuildingJob(
                        id=f"energy_optimize_{self.current_minute}_{device.zone}",
                        job_type="ENERGY_OPTIMIZE",
                        priority=2,
                        work_units_required=3,
                        deadline_time=self.current_minute + 15,
                        creation_time=self.current_minute,
                        target_zone=device.zone,
                        base_reward=6,
                        penalty_for_failure=60,
                        parameters={
                            "current_power": current_power,
                            "target_power": 1.5,  # Target power usage
                            "optimization_needed": current_power - 1.5
                        }
                    )
                    self._assign_job_to_device(job, device)

    def _check_security_conditions(self):
        """Generate jobs based on security events and conditions."""
        for device in self.devices:
            if isinstance(device, (CardReaderSensor, ActuatingDevice)):
                # Simulate security check probability
                if random.random() < 0.01:  # 1% chance per minute
                    job = BuildingJob(
                        id=f"security_check_{self.current_minute}_{device.zone}",
                        job_type="SECURITY_CHECK",
                        priority=3,
                        work_units_required=4,
                        deadline_time=self.current_minute + 2,
                        creation_time=self.current_minute,
                        target_zone=device.zone,
                        base_reward=6,
                        penalty_for_failure=60,
                        parameters={
                            "check_type": "routine",
                            "device_id": device.device_id
                        }
                    )
                    self._assign_job_to_device(job, device)

    def _process_event(self, event: Dict):
        """Process a single event from the scenario."""
        if event["type"] == "temperature_reading":
            self._handle_temperature_reading(event)
        elif event["type"] == "window_opened":
            self._handle_window_opened(event)
        elif event["type"] == "access_entry":
            self._handle_access_entry(event)

    def _handle_temperature_reading(self, event: Dict):
        """Handle a temperature reading event."""
        device = self._get_device_by_id(event["device_id"])
        if device and isinstance(device, SensingDevice):
            # Create a job for temperature reading
            job = BuildingJob(
                id=f"temp_reading_{event['timestamp']}_{event['device_id']}",
                job_type="TEMPERATURE_READ",
                priority=1,
                work_units_required=2,
                deadline_time=event["timestamp"] + 5,
                creation_time=event["timestamp"],
                target_zone=event["zone_id"],
                base_reward=4,
                penalty_for_failure=40,
                parameters={"temperature": event["value"]}
            )
            self._assign_job_to_device(job, device)

    def _handle_window_opened(self, event: Dict):
        """Handle a window opened event."""
        # Find HVAC devices in the zone
        hvac_devices = [d for d in self.devices 
                       if isinstance(d, ActuatingDevice) 
                       and d.actuator_type == "hvac_control"
                       and getattr(d, 'zone', None) == event["zone_id"]]
        
        for device in hvac_devices:
            job = BuildingJob(
                id=f"window_opened_{event['timestamp']}_{event['zone_id']}",
                job_type="HVAC_ADJUST",
                priority=2,
                work_units_required=3,
                deadline_time=event["timestamp"] + 10,
                creation_time=event["timestamp"],
                target_zone=event["zone_id"],
                base_reward=5,
                penalty_for_failure=50,
                parameters={"window_open": True, "duration": event["duration_minutes"]}
            )
            self._assign_job_to_device(job, device)

    def _handle_access_entry(self, event: Dict):
        """Handle an access entry event."""
        # Find access control devices in the zone
        access_devices = [d for d in self.devices 
                         if isinstance(d, (CardReaderSensor, ActuatingDevice))
                         and getattr(d, 'zone', None) == event["zone_id"]]
        
        for device in access_devices:
            job = BuildingJob(
                id=f"access_{event['timestamp']}_{event['zone_id']}",
                job_type="ACCESS_REQUEST",
                priority=1,
                work_units_required=2,
                deadline_time=event["timestamp"] + 2,
                creation_time=event["timestamp"],
                target_zone=event["zone_id"],
                base_reward=3,
                penalty_for_failure=30,
                parameters={"user_id": event["user_id"]}
            )
            self._assign_job_to_device(job, device)

    def _assign_job_to_device(self, job: BuildingJob, device: Device):
        """Assign a job to a device."""
        if not getattr(device, 'current_job_id', None) and device.current_load < device.max_load * 0.90:
            job.assigned_to_device_id = device.device_id
            job.status = "ASSIGNED"
            setattr(device, 'current_job_id', job.id)
            self.metrics['jobs_assigned'] += 1
            self.metrics['total_jobs_created'] += 1
            self.active_jobs[job.id] = job
            self.logger.log_info(self.run_context_name, 
                               f"Job {job.id} ({job.job_type} P{job.priority}) assigned to {device.nameShort()}")

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
            self.metrics['total_jobs_done'] += 1
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
                self.metrics['total_jobs_done'] += 1
                device.receive_income(job.base_reward, f"{status_log_prefix} on time")
                self.metrics['total_rewards_earned'] += job.base_reward
                self.logger.log_info(self.run_context_name, f"{status_log_prefix} COMPLETED ON TIME by {device.nameShort()}. Reward: {job.base_reward}")
            else:
                job.status = "COMPLETED_LATE"
                self.metrics['jobs_completed_late'] += 1
                self.metrics['total_jobs_done'] += 1
                device.receive_income(job.base_reward * 0.5, f"{status_log_prefix} late")
                self.metrics['total_rewards_earned'] += job.base_reward * 0.5
                self.logger.log_info(self.run_context_name, f"{status_log_prefix} COMPLETED LATE by {device.nameShort()}. Reward: {job.base_reward * 0.5}")
            self.processed_jobs.append(job)
            if job.id in self.active_jobs: del self.active_jobs[job.id]
            setattr(device, 'current_job_id', None)
        elif self.current_minute > job.deadline_time and job.status == "IN_PROGRESS":
            job.status = "FAILED_DEADLINE"
            job.completion_time = self.current_minute
            self.metrics['jobs_failed_deadline'] += 1
            self.metrics['total_jobs_done'] += 1
            device.receive_penalty(job.penalty_for_failure, "System", f"Job {job.id} missed deadline")
            self.metrics['total_penalties_incurred'] += job.penalty_for_failure
            self.logger.log_info(self.run_context_name, f"Job {job.id} ({job.job_type} P{job.priority}) FAILED DEADLINE on {device.nameShort()}. Penalty: {job.penalty_for_failure}")
            self.processed_jobs.append(job)
            if job.id in self.active_jobs: del self.active_jobs[job.id]
            setattr(device, 'current_job_id', None)

    def _process_active_jobs(self):
        """Process all active jobs in the simulation."""
        # Create a copy of active jobs to avoid modification during iteration
        active_jobs = list(self.active_jobs.values())
        
        for job in active_jobs:
            device = self._get_device_by_id(job.assigned_to_device_id)
            if device:
                        self._process_device_job(device, job)
            else: 
                self.logger.log_warning(self.run_context_name, f"Job {job.id} assigned to non-existent device {job.assigned_to_device_id}")
                job.status = "FAILED_INTERNAL"
                self.metrics['jobs_failed_internal'] += 1
                self.metrics['total_jobs_done'] += 1
                if job.id in self.active_jobs:
                    del self.active_jobs[job.id]

    def run(self):
        self.logger.log_info(
            "BldgCplxV3Run",
            f"Starting {self.framework_variant} simulation with {len(self.devices)} devices across {len(self.zones)} zones",
            context_override=f"BldgCplxV3Run_{self.framework_variant}"
        )
        
        self.setup_devices()
        for minute_cycle in range(self.time_frame):
            self.simulate_cycle(minute_cycle)
            if minute_cycle > 0 and (minute_cycle % (self.time_frame // 20 if self.time_frame >=20 else 1) == 0 or minute_cycle == self.time_frame -1) :
                 failed_total = self.metrics['jobs_failed_deadline'] + self.metrics['jobs_failed_internal']
                 self.logger.log_info(self.run_context_name, f"Min {minute_cycle} | Active/Failed Jobs: {len(self.active_jobs)}/{failed_total} | Completed(OK/Late):{self.metrics['jobs_completed_on_time']}/{self.metrics['jobs_completed_late']}")
        
        self.report()

    def report(self):
        """Generate a final report of the simulation."""
        print("\n" + "=" * 80)
        print(f"========================= BUILDING SIMULATION COMPLEX V3 FINAL REPORT ({self.framework_variant}) ==========================")
        print("=" * 80)
        
        # Basic stats
        print(f"Duration: {self.time_frame}m | Devices: {len(self.devices)} | Zones: {len(self.zones)}")
        print(f"Total Jobs Created: {self.metrics['total_jobs_created']}")
        print(f"Total Jobs Completed: {self.metrics['total_jobs_done']}")
        print(f"Jobs Completed On Time: {self.metrics['jobs_completed_on_time']}")
        print(f"Jobs Completed Late: {self.metrics['jobs_completed_late']}")
        print(f"Jobs Failed (Deadline): {self.metrics['jobs_failed_deadline']}")
        print(f"Jobs Failed (Internal): {self.metrics['jobs_failed_internal']}")
        
        # Performance metrics
        print("\nPerformance Metrics:")
        print(f"Total Work Units Processed: {self.metrics['total_work_units_processed']}")
        print(f"Average Job Completion Time: {self.metrics['avg_job_completion_time']:.2f} minutes")
        print(f"Average Job Tardiness: {self.metrics['avg_job_tardiness']:.2f} minutes")
        
        # Device stats
        print("\nDevice Statistics:")
        for device_id, working_cycles in self.metrics['device_cycles_working'].items():
            idle_cycles = self.metrics['device_cycles_idle'][device_id]
            total_cycles = working_cycles + idle_cycles
            utilization = (working_cycles / total_cycles * 100) if total_cycles > 0 else 0
            print(f"Device {device_id}: {utilization:.1f}% utilization ({working_cycles}/{total_cycles} cycles)")
        
        # Economic metrics
        print("\nEconomic Metrics:")
        print(f"Total Rewards Earned: {self.metrics['total_rewards_earned']}")
        print(f"Total Penalties Incurred: {self.metrics['total_penalties_incurred']}")
        print(f"Net Balance: {self.metrics['total_rewards_earned'] - self.metrics['total_penalties_incurred']}")
        
        # Trust and QoE metrics
        print("\nTrust and QoE Metrics:")
        print(f"Average Trust at End: {self.metrics['avg_trust_at_end']}")
        if self.metrics['qoe_interaction_samples']:
            avg_qoe = sum(self.metrics['qoe_interaction_samples']) / len(self.metrics['qoe_interaction_samples'])
            print(f"Average QoE: {avg_qoe:.2f}")
        
        print("=" * 80)
        
        # Store metrics with the correct run key format
        self.logger.store_simulation_metrics(
            metrics_dict=self.metrics,
            simulation_run_key=self.run_context_name
        )
        self.logger.log_info("FINAL_REPORT_END", "="*70, context_override=f"BldgCplxV3Report_{self.framework_variant}")

