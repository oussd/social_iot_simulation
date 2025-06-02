# src/devices/communicating_device.py
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
                 # Add a flag or type to distinguish general comm devices from servers
                 is_server_type: bool = False, 
                 **kwargs): 
        
        specific_capabilities = ["transmit", "connect", protocol]
        if "PERIODIC_HEALTH_CHECK" not in specific_capabilities:
            specific_capabilities.append("PERIODIC_HEALTH_CHECK")
        
        self.is_server_type = is_server_type
        if self.is_server_type: # Servers have additional processing capabilities
            specific_capabilities.append("process_data") # Generic capability
            specific_capabilities.append("ZONE_SERVER_TASK") # Specific job type
            specific_capabilities.append("SERVER_COMM_TASK") # Specific job type
            
        super().__init__(device_id, name, max_load, framework_variant,
                         capabilities=specific_capabilities,
                         logger_instance=logger_instance,
                         current_minute_provider=current_minute_provider,
                         **kwargs) 
        self.protocol = protocol
        self.connected_devices: List[Device] = [] # Devices this communicator is connected to
        self.base_transmit_reward = 8
        self.base_server_task_reward = 15 # For ZONE_SERVER_TASK or SERVER_COMM_TASK

        # Announced QoS for communication specific parameters
        if self.behavior_profile != 'deceptive':
            if 'transmission_latency_ms' not in self.announced_qos:
                 self.announced_qos['transmission_latency_ms'] = random.uniform(5, 25)
                 if 'transmission_latency_ms' not in self.qoe_thresholds:
                    self.qoe_thresholds['transmission_latency_ms'] = {'sigma': 10.0, 'delta': 5.0}
            if 'message_delivery_rate' not in self.announced_qos: # Corresponds to task_success_rate for transmission
                self.announced_qos['message_delivery_rate'] = random.uniform(0.97, 1.0)
                if 'message_delivery_rate' not in self.qoe_thresholds:
                    self.qoe_thresholds['message_delivery_rate'] = self.qoe_thresholds.get('task_success_rate', {'sigma': 0.05, 'delta': 0.02})
            if self.is_server_type and 'processing_efficiency' not in self.announced_qos: # For server tasks
                self.announced_qos['processing_efficiency'] = random.uniform(0.9, 1.1) # Similar to load_efficiency
                if 'processing_efficiency' not in self.qoe_thresholds:
                    self.qoe_thresholds['processing_efficiency'] = {'sigma': 0.2, 'delta': 0.1}

        elif 'transmission_latency_ms' not in self.announced_qos: # Deceptive profile
            self.announced_qos['transmission_latency_ms'] = random.uniform(3, 15) 
            self.announced_qos['message_delivery_rate'] = random.uniform(0.99, 0.999) 
            if 'transmission_latency_ms' not in self.qoe_thresholds:
                self.qoe_thresholds['transmission_latency_ms'] = {'sigma': 10.0, 'delta': 5.0}
            if 'message_delivery_rate' not in self.qoe_thresholds:
                self.qoe_thresholds['message_delivery_rate'] = self.qoe_thresholds.get('task_success_rate', {'sigma': 0.05, 'delta': 0.02})
            if self.is_server_type and 'processing_efficiency' not in self.announced_qos:
                self.announced_qos['processing_efficiency'] = random.uniform(1.1, 1.3) # Announce better efficiency
                if 'processing_efficiency' not in self.qoe_thresholds:
                     self.qoe_thresholds['processing_efficiency'] = {'sigma': 0.2, 'delta': 0.1}


    def connect_device(self, device_to_connect: Device) -> bool:
        if device_to_connect not in self.connected_devices:
            self.connected_devices.append(device_to_connect)
            self.log_debug(f"Connected to {device_to_connect.nameShort()} via {self.protocol}")
            return True
        return True # Already connected is also a success in this context

    def _perform_transmit_action(self, message: str, target_device: Device, expected_load_for_task: int) -> Dict[str, Any]:
        action_start_time = time.time()
        load_factor = self.announced_qos.get('load_efficiency', 1.0) * random.uniform(0.9, 1.1)
        action_load_cost = int(expected_load_for_task * load_factor)
        action_load_cost = max(1, action_load_cost)

        if random.random() < self.fault_probability:
            self.log_warning(f"Simulating internal fault during transmit action.")
            processing_time_ms = (time.time() - action_start_time) * 1000
            if self.sim_metrics_ref: self.sim_metrics_ref['faulty_device_actions_failed'] = self.sim_metrics_ref.get('faulty_device_actions_failed',0) + 1
            return {'success': False, 'reason': 'internal_device_fault', 'load_consumed': 0,
                    'processing_time_ms': processing_time_ms, 'message_delivered_binary': 0}

        if target_device not in self.connected_devices:
            # Attempt to connect if not connected, for robustness, though scenario should ideally set this up
            # For now, we'll treat it as a failure if not pre-connected by a 'connect' task or initial setup.
            self.log_warning(f"Cannot transmit: {target_device.nameShort()} not in connected_devices list for {self.nameShort()}.")
            return {'success': False, 'reason': 'target_not_connected_internal', 'load_consumed': 0,
                    'processing_time_ms': (time.time() - action_start_time) * 1000, 'message_delivered_binary': 0}

        if not self.consume_load(action_load_cost):
            return {'success': False, 'reason': 'overload_at_action', 'load_consumed': 0,
                    'processing_time_ms': (time.time() - action_start_time) * 1000, 'message_delivered_binary': 0}

        announced_latency = self.announced_qos.get('transmission_latency_ms', 10)
        effective_latency = announced_latency
        if self.behavior_profile == 'deceptive':
            effective_latency /= self.deception_factor if self.deception_factor > 0 else 1.0
        
        simulated_latency_ms = effective_latency * random.uniform(0.7, 1.5)
        actual_processing_delay_sec = max(0.001, simulated_latency_ms / 1000.0)
        if actual_processing_delay_sec > 0.001: time.sleep(actual_processing_delay_sec)


        announced_delivery_rate = self.announced_qos.get('message_delivery_rate', 0.99)
        effective_delivery_rate = announced_delivery_rate
        if self.behavior_profile == 'deceptive':
            effective_delivery_rate *= self.deception_factor if self.deception_factor != 0 else 1.0

        delivered_successfully = random.random() < effective_delivery_rate
        action_duration_ms = (time.time() - action_start_time) * 1000

        if delivered_successfully:
            self.log_debug(f"Transmitted '{message[:30]}...' to {target_device.nameShort()} via {self.protocol} in {action_duration_ms:.0f}ms, Load: {action_load_cost}")
            # Simulate message reception at target if it has a logging method
            if hasattr(target_device, 'log_debug') and callable(getattr(target_device, 'log_debug')):
                 target_device.log_debug(f"Received '{message[:30]}...' from {self.nameShort()}")
            elif hasattr(target_device, 'log_event'): 
                 target_device.log_event(f"Received '{message[:30]}...' from {self.nameShort()}", level='debug', context_override=target_device.nameShort())

        else:
            self.log_warning(f"Transmission of '{message[:30]}...' to {target_device.nameShort()} FAILED (simulated delivery failure).")

        return {
            'success': delivered_successfully, 'load_consumed': action_load_cost,
            'processing_time_ms': action_duration_ms,
            'message_delivered_binary': 1 if delivered_successfully else 0
        }

    def _perform_server_processing_action(self, task_type: str, expected_load_for_task: int, details: Optional[Dict] = None) -> Dict[str, Any]:
        """Simulates a generic server processing task."""
        details = details or {}
        action_start_time = time.time()
        
        # Load cost is based on processing_efficiency and expected_load (which itself might be dynamic)
        load_factor = self.announced_qos.get('processing_efficiency', 1.0) * random.uniform(0.9, 1.1)
        action_load_cost = int(expected_load_for_task * load_factor)
        action_load_cost = max(1, action_load_cost)

        if task_type == "PERIODIC_HEALTH_CHECK":
            self.consume_load(1)
            self.log_debug(f"Performed {task_type}, status: OK.")
            return {'success': True, 'load_consumed': 1, 
                    'processing_time_ms': (time.time() - action_start_time) * 1000,
                    'result_data': "HEALTH_OK"}

        if random.random() < self.fault_probability:
            self.log_warning(f"Simulating internal fault during server task: {task_type}.")
            processing_time_ms = (time.time() - action_start_time) * 1000
            if self.sim_metrics_ref: self.sim_metrics_ref['faulty_device_actions_failed'] = self.sim_metrics_ref.get('faulty_device_actions_failed',0) + 1
            return {'success': False, 'reason': 'internal_server_fault', 'load_consumed': 0,
                    'processing_time_ms': processing_time_ms, 'result_data': None}

        if not self.consume_load(action_load_cost):
            return {'success': False, 'reason': 'overload_at_server_action', 'load_consumed': 0,
                    'processing_time_ms': (time.time() - action_start_time) * 1000, 'result_data': None}

        # Simulate processing time based on work units (expected_load_for_task)
        # Assume announced_qos['response_time_ms'] is per unit of work for servers
        time_per_work_unit_ms = self.announced_qos.get('response_time_ms', 20) # Default 20ms per WU
        effective_time_per_wu = time_per_work_unit_ms
        if self.behavior_profile == 'deceptive':
            effective_time_per_wu /= self.deception_factor if self.deception_factor > 0 else 1.0
        
        simulated_processing_ms = effective_time_per_wu * expected_load_for_task * random.uniform(0.8, 1.2)
        actual_processing_delay_sec = max(0.001, simulated_processing_ms / 1000.0)
        if actual_processing_delay_sec > 0.001: time.sleep(actual_processing_delay_sec)
        
        action_duration_ms = (time.time() - action_start_time) * 1000
        task_subtype = details.get("task_subtype", "generic_processing")
        result_data = f"{task_type}_completed_for_{task_subtype}"
        
        self.log_debug(f"Processed server task '{task_type}' (subtype: {task_subtype}) in {action_duration_ms:.0f}ms. Load: {action_load_cost}. Result: {result_data[:30]}")
        return {
            'success': True, 'load_consumed': action_load_cost,
            'processing_time_ms': action_duration_ms,
            'result_data': result_data
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

        action_result = None
        can_handle_task = False

        if task_type == "transmit":
            can_handle_task = True
            message = details.get('message', f"default_ping_from_{self.nameShort()}_to_target")
            target_comm_device = details.get('target_comm_device') # This should be a Device object
            if not target_comm_device or not isinstance(target_comm_device, Device):
                self.log_warning(f"Invalid or no target_comm_device provided for transmit task.")
                overall_response_time_ms = (time.time() - request_start_time) * 1000
                measured_qos = {'task_success_binary': 0, 'response_time_ms': overall_response_time_ms, 'reason_code': 'invalid_target', 'expected_load_for_task': load_requested}
                self.update_trust_from_qoe(from_device, task_type, measured_qos, interaction_role="performer")
                return {'success': False, 'reason': 'invalid_target_device_for_transmit',
                        'measured_qos_for_requestor': measured_qos, 'request_start_time': request_start_time}
            self.connect_device(target_comm_device) # Ensure connection
            action_result = self._perform_transmit_action(message, target_comm_device, load_requested)
        
        elif self.is_server_type and (task_type == "ZONE_SERVER_TASK" or task_type == "SERVER_COMM_TASK"):
            can_handle_task = True
            # Load for server tasks might be dynamic, scenario_generator already sets work_units_required
            action_result = self._perform_server_processing_action(task_type, load_requested, details)
        
        elif task_type == "PERIODIC_HEALTH_CHECK":
            can_handle_task = True
            action_result = self._perform_server_processing_action(task_type, 1, details) # Minimal load for health check
            
        elif task_type == "connect": # Handle direct connect requests
            can_handle_task = True
            device_to_connect = details.get("device_to_connect")
            if device_to_connect and isinstance(device_to_connect, Device):
                connect_success = self.connect_device(device_to_connect)
                action_result = {'success': connect_success, 'load_consumed': 1, 'processing_time_ms': 10} # Minimal impact
            else:
                action_result = {'success': False, 'reason': 'invalid_device_for_connect'}

        if not can_handle_task:
            self.log_warning(f"Rejected: {self.nameShort()} (protocol: {self.protocol}, server: {self.is_server_type}) cannot handle task type '{task_type}'. Expected 'transmit', 'connect', or specific server tasks if applicable.")
            overall_response_time_ms = (time.time() - request_start_time) * 1000
            measured_qos = {'task_success_binary': 0, 'response_time_ms': overall_response_time_ms, 'expected_load_for_task': load_requested}
            return {'success': False, 'reason': 'unsupported_task_type_by_specialization',
                    'measured_qos_for_requestor': measured_qos, 'request_start_time': request_start_time}

        # If action_result is None here, it means can_handle_task was true but no action was taken (should not happen with current logic)
        if action_result is None:
             action_result = {'success': False, 'reason': 'internal_logic_error_no_action_taken'}


        overall_response_time_ms = (time.time() - request_start_time) * 1000
        measured_qos_for_trust_and_requestor = {
            'task_success_binary': 1 if action_result.get('success') else 0,
            'response_time_ms': overall_response_time_ms,
            'load_consumed': action_result.get('load_consumed', 0),
            'expected_load_for_task': load_requested, 
            'processing_time_ms': action_result.get('processing_time_ms', 0),
        }
        if task_type == "transmit":
            measured_qos_for_trust_and_requestor['message_delivered_binary'] = action_result.get('message_delivered_binary', 0)
        elif self.is_server_type and (task_type == "ZONE_SERVER_TASK" or task_type == "SERVER_COMM_TASK"):
            # For server tasks, success might be measured by 'task_success_binary' itself
            # and 'processing_efficiency' could be derived if needed for QoE
            pass # No specific QoS beyond success/time/load for now for server processing

        self.update_trust_from_qoe(from_device, task_type, measured_qos_for_trust_and_requestor, interaction_role="performer")

        if action_result.get('success'):
            result_val_log = str(action_result.get('result_data', action_result.get('value', 'N/A')))[:30]
            self.log_info(f"EXECUTED '{task_type}' for {from_device.nameShort() if from_device else 'autonomous'}. Result/Target: {result_val_log}")
            
            iot_app_reward = details.get('iot_app_reward', 0)
            if not from_device:
                base_reward = self.base_transmit_reward
                if self.is_server_type and (task_type == "ZONE_SERVER_TASK" or task_type == "SERVER_COMM_TASK"):
                    base_reward = self.base_server_task_reward
                iot_app_reward = details.get("base_reward_from_script", base_reward)


            if iot_app_reward > 0: self.receive_income(iot_app_reward, f"{task_type.capitalize()} Task Completion")
            
            return_payload = {'success': True, 'reason': f'{task_type}_successful',
                              'measured_qos_for_requestor': measured_qos_for_trust_and_requestor, 
                              'request_start_time': request_start_time}
            if 'result_data' in action_result: return_payload['result_data'] = action_result['result_data']
            if 'value' in action_result: return_payload['value'] = action_result['value'] # For compatibility if used
            return return_payload
        else:
            self.log_warning(f"{task_type.capitalize()} execution FAILED for {from_device.nameShort() if from_device else 'autonomous'}. Reason: {action_result.get('reason','unknown')}")
            # Backup logic
            if self.framework_variant in ["social_basic", "full_siot"] and not details.get('is_backup_attempt'):
                 if self.behavior_profile == 'selfish' and random.random() < self.policy.get('selfish_low_backup_priority_factor', 0.0):
                     self.log_debug(f"Selfish device {self.nameShort()} is reluctant to seek backup after failure.")
                 else:
                    for rel in self.relationships.get('back_me', []):
                        backup_device = rel.get('device')
                        if not backup_device: continue
                        if backup_device == from_device or (details.get('is_backup_attempt') and details.get('original_backup_initiator') == backup_device.device_id):
                            continue
                        self.log_info(f"Attempting backup {task_type} with {backup_device.nameShort()}")
                        backup_details = details.copy(); backup_details['is_backup_attempt'] = True
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

