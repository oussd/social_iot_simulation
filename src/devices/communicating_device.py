import random
import time
from typing import List, Dict, Any, Optional
from .device import Device, QoELevel # Base class

class CommunicatingDevice(Device):
    def __init__(self, device_id: str, name: str, max_load: int = 100,
                 protocol: str = "WiFi",
                 framework_variant: str = "full_siot",
                 logger_instance=None,
                 current_minute_provider=None,
                 **kwargs): 
        super().__init__(device_id, name, max_load, framework_variant,
                         capabilities=["transmit", "connect", protocol],
                         logger_instance=logger_instance,
                         current_minute_provider=current_minute_provider,
                         **kwargs) 
        self.protocol = protocol
        self.connected_devices: List[Device] = []
        self.base_transmit_reward = 8

        if self.behavior_profile != 'deceptive':
            if 'transmission_latency_ms' not in self.announced_qos:
                 self.announced_qos['transmission_latency_ms'] = random.uniform(5, 25)
                 self.qoe_thresholds['transmission_latency_ms'] = {'sigma': 10.0, 'delta': 5.0}
            if 'message_delivery_rate' not in self.announced_qos:
                self.announced_qos['message_delivery_rate'] = random.uniform(0.97, 1.0)
                self.qoe_thresholds['message_delivery_rate'] = self.qoe_thresholds.get('task_success_rate', {'sigma': 0.05, 'delta': 0.02})
        elif 'transmission_latency_ms' not in self.announced_qos: 
            self.announced_qos['transmission_latency_ms'] = random.uniform(3, 15) 
            self.announced_qos['message_delivery_rate'] = random.uniform(0.99, 0.999) 
            self.qoe_thresholds['transmission_latency_ms'] = {'sigma': 10.0, 'delta': 5.0}
            self.qoe_thresholds['message_delivery_rate'] = self.qoe_thresholds.get('task_success_rate', {'sigma': 0.05, 'delta': 0.02})


    def connect_device(self, device_to_connect: Device) -> bool:
        if device_to_connect not in self.connected_devices:
            self.connected_devices.append(device_to_connect)
            self.log_debug(f"Connected to {device_to_connect.nameShort()} via {self.protocol}") # Changed to log_debug
            return True
        return True

    def _perform_transmit_action(self, message: str, target_device: Device, expected_load_for_task: int) -> Dict[str, Any]:
        action_start_time = time.time()
        load_factor = self.announced_qos.get('load_efficiency', 1.0) * random.uniform(0.9, 1.1)
        action_load_cost = int(expected_load_for_task * load_factor)
        action_load_cost = max(1, action_load_cost)

        if random.random() < self.fault_probability:
            self.log_warning(f"Simulating internal fault during transmit action.") # Changed to log_warning
            processing_time_ms = (time.time() - action_start_time) * 1000
            if self.sim_metrics_ref: self.sim_metrics_ref['faulty_device_actions_failed'] = self.sim_metrics_ref.get('faulty_device_actions_failed',0) + 1
            return {'success': False, 'reason': 'internal_device_fault', 'load_consumed': 0,
                    'processing_time_ms': processing_time_ms, 'message_delivered_binary': 0}

        if target_device not in self.connected_devices:
            self.log_warning(f"Cannot transmit: {target_device.nameShort()} not in connected_devices list for {self.nameShort()}.") # Changed to log_warning
            return {'success': False, 'reason': 'target_not_connected_internal', 'load_consumed': 0,
                    'processing_time_ms': (time.time() - action_start_time) * 1000, 'message_delivered_binary': 0}

        if not self.consume_load(action_load_cost):
            return {'success': False, 'reason': 'overload_at_action', 'load_consumed': 0,
                    'processing_time_ms': (time.time() - action_start_time) * 1000, 'message_delivered_binary': 0}

        announced_latency = self.announced_qos.get('transmission_latency_ms', 10)
        effective_latency = announced_latency
        if self.behavior_profile == 'deceptive':
            effective_latency /= self.deception_factor 
        
        simulated_latency_ms = effective_latency * random.uniform(0.7, 1.5)
        time.sleep(simulated_latency_ms / 1000.0)

        announced_delivery_rate = self.announced_qos.get('message_delivery_rate', 0.99)
        effective_delivery_rate = announced_delivery_rate
        if self.behavior_profile == 'deceptive':
            effective_delivery_rate *= self.deception_factor 

        delivered_successfully = random.random() < effective_delivery_rate
        action_duration_ms = (time.time() - action_start_time) * 1000

        if delivered_successfully:
            self.log_debug(f"Transmitted '{message[:30]}...' to {target_device.nameShort()} via {self.protocol} in {action_duration_ms:.0f}ms, Load: {action_load_cost}") # Changed to log_debug
            if hasattr(target_device, 'log_debug') and callable(getattr(target_device, 'log_debug')): # Check if target has specific log_debug
                 target_device.log_debug(f"Received '{message[:30]}...' from {self.nameShort()}")
            elif hasattr(target_device, 'log_event'): # Fallback to log_event
                 target_device.log_event(f"Received '{message[:30]}...' from {self.nameShort()}", level='debug')

        else:
            self.log_warning(f"Transmission of '{message[:30]}...' to {target_device.nameShort()} FAILED (simulated delivery failure).") # Changed to log_warning

        return {
            'success': delivered_successfully, 'load_consumed': action_load_cost,
            'processing_time_ms': action_duration_ms,
            'message_delivered_binary': 1 if delivered_successfully else 0
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

        if task_type != 'transmit':
            self.log_warning(f"Rejected: {self.nameShort()} cannot handle task type '{task_type}'. Expected 'transmit'.") # Changed to log_warning
            overall_response_time_ms = (time.time() - request_start_time) * 1000
            measured_qos = {'task_success_binary': 0, 'response_time_ms': overall_response_time_ms, 'expected_load_for_task': load_requested}
            self.update_trust_from_qoe(from_device, task_type, measured_qos, interaction_role="performer")
            return {'success': False, 'reason': 'unsupported_task_type_by_specialization',
                    'measured_qos_for_requestor': measured_qos, 'request_start_time': request_start_time}

        message = details.get('message', f"default_ping_from_{self.nameShort()}_to_target")
        target_comm_device = details.get('target_comm_device')

        if not target_comm_device or not isinstance(target_comm_device, Device):
            self.log_warning(f"Invalid or no target_comm_device provided for transmit task.") # Changed to log_warning
            overall_response_time_ms = (time.time() - request_start_time) * 1000
            measured_qos = {'task_success_binary': 0, 'response_time_ms': overall_response_time_ms, 'reason_code': 'invalid_target', 'expected_load_for_task': load_requested}
            self.update_trust_from_qoe(from_device, task_type, measured_qos, interaction_role="performer")
            return {'success': False, 'reason': 'invalid_target_device_for_transmit',
                    'measured_qos_for_requestor': measured_qos, 'request_start_time': request_start_time}

        self.connect_device(target_comm_device)
        action_result = self._perform_transmit_action(message, target_comm_device, load_requested)
        
        overall_response_time_ms = (time.time() - request_start_time) * 1000
        measured_qos_for_trust_and_requestor = {
            'task_success_binary': 1 if action_result.get('success') else 0,
            'response_time_ms': overall_response_time_ms,
            'load_consumed': action_result.get('load_consumed', 0),
            'expected_load_for_task': load_requested, 
            'processing_time_ms': action_result.get('processing_time_ms', 0),
            'message_delivered_binary': action_result.get('message_delivered_binary', 0)
        }
        self.update_trust_from_qoe(from_device, task_type, measured_qos_for_trust_and_requestor, interaction_role="performer")

        if action_result.get('success'):
            self.log_info(f"EXECUTED '{task_type}' for {from_device.nameShort() if from_device else 'autonomous'} to {target_comm_device.nameShort()}") # Changed to log_info
            iot_app_reward = details.get('iot_app_reward', self.base_transmit_reward if not from_device else 0)
            if iot_app_reward > 0: self.receive_income(iot_app_reward, f"{task_type.capitalize()} Task Completion")
            return {'success': True, 'reason': f'{task_type}_successful',
                    'measured_qos_for_requestor': measured_qos_for_trust_and_requestor, 'request_start_time': request_start_time}
        else:
            self.log_warning(f"{task_type.capitalize()} execution FAILED for {from_device.nameShort() if from_device else 'autonomous'} to {target_comm_device.nameShort()}. Reason: {action_result.get('reason','unknown')}") # Changed to log_warning
            if self.framework_variant in ["social_basic", "full_siot"]:
                 if self.behavior_profile == 'selfish' and random.random() < self.policy.get('selfish_low_backup_priority_factor', 0.0):
                     self.log_debug(f"Selfish device {self.nameShort()} is reluctant to seek backup after failure.") # Changed to log_debug
                 else:
                    for rel in self.relationships.get('back_me', []):
                        backup_device = rel.get('device')
                        if not backup_device: continue
                        if backup_device == from_device or (details.get('is_backup_attempt') and details.get('original_backup_initiator') == backup_device.device_id):
                            continue
                        self.log_info(f"Attempting backup {task_type} with {backup_device.nameShort()}") # Changed to log_info
                        backup_details = details.copy(); backup_details['is_backup_attempt'] = True
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
