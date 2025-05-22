import random
import time
from typing import List, Dict, Any, Optional
from .device import Device, QoELevel # Base class

class SensingDevice(Device):
    def __init__(self, device_id: str, name: str, max_load: int = 100,
                 sensor_type: str = "temperature",
                 framework_variant: str = "full_siot",
                 logger_instance=None,
                 current_minute_provider=None,
                 **kwargs): 
        super().__init__(device_id, name, max_load, framework_variant,
                         capabilities=["sense", sensor_type],
                         logger_instance=logger_instance,
                         current_minute_provider=current_minute_provider,
                         **kwargs) 
        self.sensor_type = sensor_type
        self.base_sense_reward = 10

        if self.behavior_profile != 'deceptive':
            if 'data_accuracy' not in self.announced_qos:
                 self.announced_qos['data_accuracy'] = random.uniform(0.9, 0.98)
                 self.qoe_thresholds['data_accuracy'] = {'sigma': 0.05, 'delta': 0.03}
        elif 'data_accuracy' not in self.announced_qos: 
             self.announced_qos['data_accuracy'] = min(0.999, random.uniform(0.95, 0.99) / (self.deception_factor * 0.9) if self.deception_factor > 0 else 0.999)
             self.qoe_thresholds['data_accuracy'] = {'sigma': 0.05, 'delta': 0.03}


    def _perform_sense_action(self, expected_load_for_task: int) -> Dict[str, Any]:
        action_start_time = time.time()
        action_load_cost = int(expected_load_for_task * self.announced_qos.get('load_efficiency', 1.0) * random.uniform(0.9, 1.1))
        action_load_cost = max(1, action_load_cost)

        if random.random() < self.fault_probability:
            self.log_warning(f"Simulating internal fault during sense action.") # Changed to log_warning
            processing_time_ms = (time.time() - action_start_time) * 1000
            if self.sim_metrics_ref: self.sim_metrics_ref['faulty_device_actions_failed'] = self.sim_metrics_ref.get('faulty_device_actions_failed',0) + 1
            return {'success': False, 'reason': 'internal_device_fault', 'load_consumed': 0,
                    'processing_time_ms': processing_time_ms, 'data_accuracy_measured': 0.0, 'value': None}

        if not self.consume_load(action_load_cost):
            return {'success': False, 'reason': 'overload_at_action', 'load_consumed': 0,
                    'processing_time_ms': (time.time() - action_start_time) * 1000,
                    'data_accuracy_measured': 0.0, 'value': None}

        effective_response_time_ms = self.announced_qos.get('response_time_ms', 50)
        if self.behavior_profile == 'deceptive':
            effective_response_time_ms /= self.deception_factor 

        simulated_action_processing_ms = effective_response_time_ms * random.uniform(0.7, 1.3)
        time.sleep(simulated_action_processing_ms / 1000.0)

        value: Any = None
        if self.sensor_type == "temperature": value = random.uniform(18.0, 28.0)
        elif self.sensor_type == "occupancy": value = random.choice([0, 1, random.randint(2,10)])
        elif self.sensor_type == "light_level": value = random.uniform(50, 1000)
        elif self.sensor_type == "co2": value = random.uniform(400, 1200)
        elif self.sensor_type == "door_contact" or self.sensor_type == "window_contact": value = random.choice(["OPEN", "CLOSED"])
        elif self.sensor_type == "card_swipe":
            value = f"card_data_{random.randint(1000,9999)}_user{random.randint(1,10)}"
        elif self.sensor_type == "power_usage":
            current_power_draw = getattr(self, 'current_power_draw_kw', random.uniform(0.5,5.0))
            current_power_draw += random.uniform(-0.2, 0.2)
            value = max(0.1, current_power_draw)
            setattr(self, 'current_power_draw_kw', value)
        else: value = random.random()

        actual_accuracy = self.announced_qos.get('data_accuracy',0.95) * random.uniform(0.85, 1.03)
        if self.behavior_profile == 'deceptive':
            actual_accuracy *= self.deception_factor 
        actual_accuracy = min(1.0, max(0.0, actual_accuracy))

        action_duration_ms = (time.time() - action_start_time) * 1000
        val_log_str = f"{value:.2f}" if isinstance(value, float) else str(value)
        self.log_debug(f"Sensed {self.sensor_type}: {val_log_str} (Acc: {actual_accuracy:.2f}) in {action_duration_ms:.0f}ms, Load Consumed: {action_load_cost}") # Changed to log_debug
        return {
            'success': True,
            'value': value,
            'load_consumed': action_load_cost,
            'processing_time_ms': action_duration_ms,
            'data_accuracy_measured': actual_accuracy
        }

    def handle_request(self, from_device: Optional[Device], task_type: str,
                       load_requested: int = 10, details: Optional[Dict] = None) -> Dict[str, Any]:
        details = details if details is not None else {}
        
        effective_load_requested = load_requested
        if self.behavior_profile == 'policy_violator' and from_device:
            if random.random() < 0.15: 
                effective_load_requested = max(1, int(load_requested * random.uniform(0.4, 0.7)))
                self.log_debug(f"Policy violator {self.nameShort()} considering task '{task_type}' with perceived load {effective_load_requested} (actual: {load_requested})")
        
        base_acceptance_outcome = super().handle_request(from_device, task_type, effective_load_requested, details) 
        request_start_time = base_acceptance_outcome.get('request_start_time', time.time())

        if not base_acceptance_outcome.get('success'):
            return base_acceptance_outcome

        if task_type != 'sense' and task_type != self.sensor_type:
            self.log_warning(f"Rejected: {self.nameShort()} cannot handle task type '{task_type}'. Expected 'sense' or '{self.sensor_type}'.") # Changed to log_warning
            overall_response_time_ms = (time.time() - request_start_time) * 1000
            measured_qos = {'task_success_binary': 0, 'response_time_ms': overall_response_time_ms, 'expected_load_for_task': load_requested}
            self.update_trust_from_qoe(from_device, task_type, measured_qos, interaction_role="performer")
            return {'success': False, 'reason': 'unsupported_task_type_by_specialization',
                    'measured_qos_for_requestor': measured_qos, 'request_start_time': request_start_time}

        action_result = self._perform_sense_action(load_requested)

        overall_response_time_ms = (time.time() - request_start_time) * 1000
        measured_qos_for_trust_and_requestor = {
            'task_success_binary': 1 if action_result.get('success') else 0,
            'response_time_ms': overall_response_time_ms,
            'load_consumed': action_result.get('load_consumed', 0),
            'expected_load_for_task': load_requested, 
            'processing_time_ms': action_result.get('processing_time_ms', 0),
            'data_accuracy_measured': action_result.get('data_accuracy_measured')
        }
        self.update_trust_from_qoe(from_device, task_type, measured_qos_for_trust_and_requestor, interaction_role="performer")

        if action_result.get('success'):
            val_report_str = f"{action_result.get('value'):.2f}" if isinstance(action_result.get('value'), float) else str(action_result.get('value'))
            self.log_info(f"EXECUTED '{task_type}' for {from_device.nameShort() if from_device else 'autonomous_task'}, val: {val_report_str}") # Changed to log_info
            iot_app_reward = details.get('iot_app_reward', self.base_sense_reward if not from_device else 0)
            if iot_app_reward > 0: self.receive_income(iot_app_reward, f"{task_type.capitalize()} Task Completion")
            return {'success': True, 'reason': f'{task_type}_successful', 'value':action_result.get('value'),
                    'measured_qos_for_requestor': measured_qos_for_trust_and_requestor, 'request_start_time': request_start_time}
        else: 
            self.log_warning(f"{task_type.capitalize()} execution FAILED for {from_device.nameShort() if from_device else 'autonomous_task'} due to {action_result.get('reason','unknown')}") # Changed to log_warning
            if self.framework_variant in ["social_basic", "full_siot"]:
                 if self.behavior_profile == 'selfish' and random.random() < self.policy.get('selfish_low_backup_priority_factor', 0.0):
                     self.log_debug(f"Selfish device {self.nameShort()} is reluctant to act as backup.") # Changed to log_debug
                 else:
                    for rel in self.relationships.get('back_me', []):
                        backup_device = rel.get('device')
                        if not backup_device: continue
                        if backup_device == from_device or (details.get('is_backup_attempt') and details.get('original_backup_initiator') == backup_device.device_id):
                            continue
                        
                        self.log_info(f"Attempting backup {task_type} with {backup_device.nameShort()}") # Changed to log_info
                        backup_details = details.copy()
                        backup_details['is_backup_attempt'] = True
                        backup_details['original_backup_initiator'] = self.device_id
                        if self.behavior_profile == 'policy_violator' and 'iot_app_reward' in backup_details:
                            backup_details['iot_app_reward'] = backup_details.get('iot_app_reward',0) * random.uniform(0.3, 0.7)

                        backup_outcome = backup_device.handle_request(self, task_type, load_requested, backup_details)
                        self.update_trust_from_qoe(backup_device, task_type, backup_outcome.get('measured_qos_for_requestor',{}), "requester")
                        if backup_outcome.get('success'):
                            self.log_info(f"Backup {task_type} by {backup_device.nameShort()} SUCCEEDED.") # Changed to log_info
                            if self.sim_metrics_ref and 'back_me_invocations_successful' in self.sim_metrics_ref:
                                self.sim_metrics_ref['back_me_invocations_successful'] +=1
                            return {**backup_outcome, 'backed_up_by': backup_device.device_id}
                        else:
                            if self.sim_metrics_ref and 'back_me_invocations_failed' in self.sim_metrics_ref:
                                self.sim_metrics_ref['back_me_invocations_failed'] +=1
            return {'success': False, 'reason': f"{task_type}_execution_failed_no_successful_backup: {action_result.get('reason','unknown')}",
                    'measured_qos_for_requestor': measured_qos_for_trust_and_requestor, 'request_start_time': request_start_time}

