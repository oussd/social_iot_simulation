# src/devices/sensing_device.py
import random
import time
from typing import List, Dict, Any, Optional
from .device import Device, QoELevel # Base class

class SensingDevice(Device):
    def __init__(self, device_id: str, name: str, max_load: int = 100,
                 sensor_type: str = "temperature", # e.g., temperature, card_swipe, window_contact
                 framework_variant: str = "full_siot",
                 logger_instance=None,
                 current_minute_provider=None,
                 **kwargs): 
        
        specific_capabilities = ["sense", sensor_type]
        if "PERIODIC_HEALTH_CHECK" not in specific_capabilities: 
            specific_capabilities.append("PERIODIC_HEALTH_CHECK")
        
        if sensor_type == "temperature":
            specific_capabilities.append("SENSE_TEMPERATURE")
        elif sensor_type == "card_swipe":
            specific_capabilities.append("CARD_SWIPE")
        elif sensor_type == "window_contact":
            specific_capabilities.append("WINDOW_STATUS_CHANGE")
            
        super().__init__(device_id, name, max_load, framework_variant,
                         capabilities=specific_capabilities, 
                         logger_instance=logger_instance,
                         current_minute_provider=current_minute_provider,
                         **kwargs) 
        self.sensor_type = sensor_type
        self.base_sense_reward = 10 

        if self.behavior_profile != 'deceptive':
            if 'data_accuracy' not in self.announced_qos:
                 self.announced_qos['data_accuracy'] = random.uniform(0.9, 0.98)
                 if 'data_accuracy' not in self.qoe_thresholds: 
                    self.qoe_thresholds['data_accuracy'] = {'sigma': 0.05, 'delta': 0.03}
        elif 'data_accuracy' not in self.announced_qos: 
             self.announced_qos['data_accuracy'] = min(0.999, random.uniform(0.95, 0.99) / (self.deception_factor * 0.9) if self.deception_factor > 0 else 0.999)
             if 'data_accuracy' not in self.qoe_thresholds: 
                self.qoe_thresholds['data_accuracy'] = {'sigma': 0.05, 'delta': 0.03}


    def _perform_sense_action(self, task_type_being_handled: str, expected_load_for_task: int, details: Optional[Dict] = None) -> Dict[str, Any]:
        details = details or {}
        action_start_time = time.time()
        
        action_load_cost = int(expected_load_for_task * self.announced_qos.get('load_efficiency', 1.0) * random.uniform(0.9, 1.1))
        action_load_cost = max(1, action_load_cost)

        if random.random() < self.fault_probability:
            self.log_warning(f"Simulating internal fault during sense action for {task_type_being_handled}.")
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
            effective_response_time_ms /= self.deception_factor if self.deception_factor > 0 else 1.0

        simulated_action_processing_ms = effective_response_time_ms * random.uniform(0.7, 1.3)
        actual_processing_delay_sec = max(0.001, simulated_action_processing_ms / 1000.0)
        if actual_processing_delay_sec > 0.001 : time.sleep(actual_processing_delay_sec)

        value: Any = None
        current_sensor_operation = self.sensor_type
        if task_type_being_handled == "SENSE_TEMPERATURE" and self.sensor_type == "temperature":
            current_sensor_operation = "temperature"
            value = details.get("sensed_temperature_live", random.uniform(18.0, 28.0)) 
        elif task_type_being_handled == "CARD_SWIPE" and self.sensor_type == "card_swipe":
            current_sensor_operation = "card_swipe"
            user_id = details.get("user_id", f"user_{random.randint(1,100)}")
            direction = details.get("direction", "IN")
            value = f"card_swipe_data:user_{user_id}_dir_{direction}"
        elif task_type_being_handled == "WINDOW_STATUS_CHANGE" and self.sensor_type == "window_contact":
            current_sensor_operation = "window_contact"
            status = details.get("status", "CLOSED") 
            value = status 
        elif task_type_being_handled == "PERIODIC_HEALTH_CHECK":
            current_sensor_operation = "health_check"
            value = "OK" 
        elif self.sensor_type == "temperature": value = details.get("sensed_temperature_live", random.uniform(18.0, 28.0))
        elif self.sensor_type == "occupancy": value = random.choice([0, 1, random.randint(2,10)])
        elif self.sensor_type == "light_level": value = random.uniform(50, 1000)
        elif self.sensor_type == "co2": value = random.uniform(400, 1200)
        elif self.sensor_type == "door_contact" or self.sensor_type == "window_contact": value = random.choice(["OPEN", "CLOSED"])
        elif self.sensor_type == "card_swipe": value = f"card_data_{random.randint(1000,9999)}_user{random.randint(1,10)}"
        elif self.sensor_type == "power_usage":
            current_power_draw = getattr(self, 'current_power_draw_kw', random.uniform(0.5,5.0))
            current_power_draw += random.uniform(-0.2, 0.2)
            value = max(0.1, current_power_draw)
            setattr(self, 'current_power_draw_kw', value)
        else: value = random.random() 

        actual_accuracy = self.announced_qos.get('data_accuracy',0.95) * random.uniform(0.85, 1.03)
        if self.behavior_profile == 'deceptive':
            actual_accuracy *= self.deception_factor if self.deception_factor != 0 else 1.0
        actual_accuracy = min(1.0, max(0.0, actual_accuracy))
        if task_type_being_handled == "PERIODIC_HEALTH_CHECK": 
            actual_accuracy = 1.0

        action_duration_ms = (time.time() - action_start_time) * 1000
        val_log_str = f"{value:.2f}" if isinstance(value, float) else str(value) 
        self.log_debug(f"Sensed {current_sensor_operation} for task '{task_type_being_handled}': {val_log_str} (Acc: {actual_accuracy:.2f}) in {action_duration_ms:.0f}ms, Load Consumed: {action_load_cost}")
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

        can_handle_task = False
        if task_type == "sense": 
            can_handle_task = True
        elif task_type == self.sensor_type: 
            can_handle_task = True
        elif task_type == "SENSE_TEMPERATURE" and self.sensor_type == "temperature":
            can_handle_task = True
        elif task_type == "CARD_SWIPE" and self.sensor_type == "card_swipe":
            can_handle_task = True
        elif task_type == "WINDOW_STATUS_CHANGE" and self.sensor_type == "window_contact":
            can_handle_task = True
        elif task_type == "PERIODIC_HEALTH_CHECK": 
            can_handle_task = True
        
        if not can_handle_task:
            self.log_warning(f"Rejected: {self.nameShort()} (type: {self.sensor_type}) cannot handle task type '{task_type}'. Expected 'sense', '{self.sensor_type}', or a recognized specific task.")
            overall_response_time_ms = (time.time() - request_start_time) * 1000
            measured_qos = {'task_success_binary': 0, 'response_time_ms': overall_response_time_ms, 'expected_load_for_task': load_requested}
            return {'success': False, 'reason': 'unsupported_task_type_by_specialization',
                    'measured_qos_for_requestor': measured_qos, 'request_start_time': request_start_time}

        action_result = self._perform_sense_action(task_type, load_requested, details)

        overall_response_time_ms = (time.time() - request_start_time) * 1000
        measured_qos_for_trust_and_requestor = {
            'task_success_binary': 1 if action_result.get('success') else 0,
            'response_time_ms': overall_response_time_ms,
            'load_consumed': action_result.get('load_consumed', 0),
            'expected_load_for_task': load_requested, 
            'processing_time_ms': action_result.get('processing_time_ms', 0),
        }
        if task_type != "PERIODIC_HEALTH_CHECK":
            measured_qos_for_trust_and_requestor['data_accuracy_measured'] = action_result.get('data_accuracy_measured')
        
        self.update_trust_from_qoe(from_device, task_type, measured_qos_for_trust_and_requestor, interaction_role="performer")

        if action_result.get('success'):
            # Define val_report_str here based on action_result
            val_report_str = f"{action_result.get('value'):.2f}" if isinstance(action_result.get('value'), float) else str(action_result.get('value'))
            # Corrected line: use val_report_str
            self.log_info(f"EXECUTED '{task_type}' for {from_device.nameShort() if from_device else 'autonomous_task'}, val: {val_report_str}")
            
            iot_app_reward = details.get('iot_app_reward', 0) 
            if not from_device: 
                # Attempt to get base_reward from job details if available (passed by scenario runner)
                # This assumes 'details' might contain the original job dictionary or its 'base_reward'
                iot_app_reward = details.get("base_reward_from_script", self.base_sense_reward)


            if iot_app_reward > 0: self.receive_income(iot_app_reward, f"{task_type.capitalize()} Task Completion")
            
            return {'success': True, 'reason': f'{task_type}_successful', 'value':action_result.get('value'),
                    'measured_qos_for_requestor': measured_qos_for_trust_and_requestor, 'request_start_time': request_start_time}
        else: 
            self.log_warning(f"{task_type.capitalize()} execution FAILED for {from_device.nameShort() if from_device else 'autonomous_task'} due to {action_result.get('reason','unknown')}")
            if self.framework_variant in ["social_basic", "full_siot"] and not details.get('is_backup_attempt'):
                 if self.behavior_profile == 'selfish' and random.random() < self.policy.get('selfish_low_backup_priority_factor', 0.0):
                     self.log_debug(f"Selfish device {self.nameShort()} is reluctant to act as backup.")
                 else:
                    for rel in self.relationships.get('back_me', []):
                        backup_device = rel.get('device')
                        if not backup_device: continue
                        if backup_device == from_device or (details.get('is_backup_attempt') and details.get('original_backup_initiator') == backup_device.device_id):
                            continue
                        
                        self.log_info(f"Attempting backup {task_type} with {backup_device.nameShort()}")
                        backup_details = details.copy()
                        backup_details['is_backup_attempt'] = True
                        backup_details['original_backup_initiator'] = self.device_id
                        if self.behavior_profile == 'policy_violator' and 'iot_app_reward' in backup_details:
                            backup_details['iot_app_reward'] = backup_details.get('iot_app_reward',0) * random.uniform(0.3, 0.7)

                        backup_outcome = backup_device.handle_request(self, task_type, load_requested, backup_details)
                        self.update_trust_from_qoe(backup_device, task_type, backup_outcome.get('measured_qos_for_requestor',{}), "requester")
                        if backup_outcome.get('success'):
                            self.log_info(f"Backup {task_type} by {backup_device.nameShort()} SUCCEEDED.")
                            if self.sim_metrics_ref and 'back_me_invocations_successful' in self.sim_metrics_ref:
                                self.sim_metrics_ref['back_me_invocations_successful'] +=1
                            return {**backup_outcome, 'backed_up_by': backup_device.device_id}
                        else:
                            if self.sim_metrics_ref and 'back_me_invocations_failed' in self.sim_metrics_ref:
                                self.sim_metrics_ref['back_me_invocations_failed'] +=1
            return {'success': False, 'reason': f"{task_type}_execution_failed_no_successful_backup: {action_result.get('reason','unknown')}",
                    'measured_qos_for_requestor': measured_qos_for_trust_and_requestor, 'request_start_time': request_start_time}

