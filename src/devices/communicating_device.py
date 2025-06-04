# src/devices/communicating_device.py
import random
import time
from typing import List, Dict, Any, Optional, Callable, TYPE_CHECKING, Tuple 

if TYPE_CHECKING:
    from .device import Device 
    from ..utils.logger import SimulationLogger

from .device import Device, DEFAULT_POLICY_STORE

class CommunicatingDevice(Device):
    def __init__(self, device_id: str, name: str, max_load: int = 100,
                 protocol: str = "WiFi",
                 framework_variant: str = "full_siot",
                 logger_instance: Optional['SimulationLogger'] = None,
                 current_minute_provider: Optional[Callable[[], int]] = None,
                 is_server_type: bool = False, 
                 **kwargs): 
        
        specific_capabilities = ["transmit", "connect", protocol]
        if "PERIODIC_HEALTH_CHECK" not in specific_capabilities:
            specific_capabilities.append("PERIODIC_HEALTH_CHECK")
        
        self.is_server_type = is_server_type
        if self.is_server_type: 
            specific_capabilities.append("process_data") 
            specific_capabilities.append("ZONE_SERVER_TASK") 
            specific_capabilities.append("SERVER_COMM_TASK") 
            
        super().__init__(device_id, name, max_load, framework_variant,
                         capabilities=specific_capabilities,
                         logger_instance=logger_instance,
                         current_minute_provider=current_minute_provider,
                         **kwargs) 
        self.protocol = protocol
        self.connected_devices: List['Device'] = [] 
        self.base_transmit_reward = 8
        self.base_server_task_reward = 15

        if self.behavior_profile != 'deceptive':
            if 'transmission_latency_ms' not in self.announced_qos:
                 self.announced_qos['transmission_latency_ms'] = random.uniform(5, 25)
                 if 'transmission_latency_ms' not in self.qoe_thresholds:
                    self.qoe_thresholds['transmission_latency_ms'] = {'sigma': 10.0, 'delta': 5.0}
            if 'message_delivery_rate' not in self.announced_qos: 
                self.announced_qos['message_delivery_rate'] = random.uniform(0.97, 1.0)
                if 'message_delivery_rate' not in self.qoe_thresholds:
                    self.qoe_thresholds['message_delivery_rate'] = self.qoe_thresholds.get('task_success_rate', {'sigma': 0.05, 'delta': 0.02})
            if self.is_server_type and 'processing_efficiency' not in self.announced_qos: 
                self.announced_qos['processing_efficiency'] = random.uniform(0.9, 1.1) 
                if 'processing_efficiency' not in self.qoe_thresholds:
                    self.qoe_thresholds['processing_efficiency'] = {'sigma': 0.2, 'delta': 0.1}
        elif 'transmission_latency_ms' not in self.announced_qos: 
            self.announced_qos['transmission_latency_ms'] = random.uniform(3, 15) 
            self.announced_qos['message_delivery_rate'] = random.uniform(0.99, 0.999) 
            if 'transmission_latency_ms' not in self.qoe_thresholds:
                self.qoe_thresholds['transmission_latency_ms'] = {'sigma': 10.0, 'delta': 5.0}
            if 'message_delivery_rate' not in self.qoe_thresholds:
                self.qoe_thresholds['message_delivery_rate'] = self.qoe_thresholds.get('task_success_rate', {'sigma': 0.05, 'delta': 0.02})
            if self.is_server_type and 'processing_efficiency' not in self.announced_qos:
                self.announced_qos['processing_efficiency'] = random.uniform(1.1, 1.3) 
                if 'processing_efficiency' not in self.qoe_thresholds:
                     self.qoe_thresholds['processing_efficiency'] = {'sigma': 0.2, 'delta': 0.1}

    def connect_device(self, device_to_connect: 'Device') -> bool:
        if device_to_connect not in self.connected_devices:
            self.connected_devices.append(device_to_connect)
            self.log_debug(f"Connected to {device_to_connect.nameShort()} via {self.protocol}")
            return True
        return True 

    def _perform_transmit_action(self, message: str, target_device: 'Device', expected_load_for_task: int, details: Optional[Dict]=None) -> Dict[str, Any]:
        action_start_time = time.time()
        load_factor = self.announced_qos.get('load_efficiency', 1.0) * random.uniform(0.9, 1.1)
        action_load_cost = int(expected_load_for_task * load_factor)
        action_load_cost = max(1, action_load_cost)

        if random.random() < self.fault_probability:
            self.log_warning(f"Simulating internal fault during transmit action (Job: {self.current_job_id}).")
            processing_time_ms = (time.time() - action_start_time) * 1000
            if self.sim_metrics_ref: self.sim_metrics_ref['faulty_device_actions_failed'] = self.sim_metrics_ref.get('faulty_device_actions_failed',0) + 1
            return {'success': False, 'reason': 'internal_device_fault', 'load_consumed': 0,
                    'processing_time_ms': processing_time_ms, 'message_delivered_binary': 0}

        if target_device not in self.connected_devices:
            self.log_warning(f"Cannot transmit: {target_device.nameShort()} not in connected_devices list for {self.nameShort()} (Job: {self.current_job_id}).")
            return {'success': False, 'reason': 'target_not_connected_internal', 'load_consumed': 0,
                    'processing_time_ms': (time.time() - action_start_time) * 1000, 'message_delivered_binary': 0}

        if not self.consume_load(action_load_cost):
            return {'success': False, 'reason': 'overload_at_action', 'load_consumed': 0,
                    'processing_time_ms': (time.time() - action_start_time) * 1000, 'message_delivered_binary': 0}

        # time.sleep() for transmission latency was here - REMOVED

        announced_delivery_rate = self.announced_qos.get('message_delivery_rate', 0.99)
        effective_delivery_rate = announced_delivery_rate
        if self.behavior_profile == 'deceptive':
            effective_delivery_rate *= self.deception_factor if self.deception_factor != 0 else 1.0

        delivered_successfully = random.random() < effective_delivery_rate
        action_duration_ms = (time.time() - action_start_time) * 1000 

        if delivered_successfully:
            self.log_debug(f"Transmitted '{message[:30]}...' to {target_device.nameShort()} via {self.protocol} in {action_duration_ms:.0f}ms, Load: {action_load_cost} (Job: {self.current_job_id})")
            if hasattr(target_device, 'log_debug') and callable(getattr(target_device, 'log_debug')):
                 target_device.log_debug(f"Received '{message[:30]}...' from {self.nameShort()}")
            elif hasattr(target_device, 'log_event'): 
                 target_device.log_event(f"Received '{message[:30]}...' from {self.nameShort()}", level='debug', context_override=target_device.nameShort())
        else:
            self.log_warning(f"Transmission of '{message[:30]}...' to {target_device.nameShort()} FAILED (simulated delivery failure) (Job: {self.current_job_id}).")

        return {
            'success': delivered_successfully, 'load_consumed': action_load_cost,
            'processing_time_ms': action_duration_ms,
            'message_delivered_binary': 1 if delivered_successfully else 0
        }

    def _perform_server_processing_action(self, task_type: str, expected_load_for_task: int, details: Optional[Dict] = None) -> Dict[str, Any]:
        details = details or {}
        action_start_time = time.time()
        
        load_factor = self.announced_qos.get('processing_efficiency', 1.0) * random.uniform(0.9, 1.1)
        action_load_cost = int(expected_load_for_task * load_factor)
        action_load_cost = max(1, action_load_cost)

        if task_type == "PERIODIC_HEALTH_CHECK":
            if self.consume_load(1):
                self.log_debug(f"Performed {task_type}, status: OK.")
                return {'success': True, 'load_consumed': 1, 
                        'processing_time_ms': (time.time() - action_start_time) * 1000,
                        'result_data': "HEALTH_OK"}
            else:
                return {'success': False, 'reason': 'overload_at_health_check_server', 'load_consumed': 0, 'processing_time_ms': (time.time() - action_start_time) * 1000, 'result_data': None}


        if random.random() < self.fault_probability:
            self.log_warning(f"Simulating internal fault during server task: {task_type} (Job: {self.current_job_id}).")
            processing_time_ms = (time.time() - action_start_time) * 1000
            if self.sim_metrics_ref: self.sim_metrics_ref['faulty_device_actions_failed'] = self.sim_metrics_ref.get('faulty_device_actions_failed',0) + 1
            return {'success': False, 'reason': 'internal_server_fault', 'load_consumed': 0,
                    'processing_time_ms': processing_time_ms, 'result_data': None}

        if not self.consume_load(action_load_cost):
            return {'success': False, 'reason': 'overload_at_server_action', 'load_consumed': 0,
                    'processing_time_ms': (time.time() - action_start_time) * 1000, 'result_data': None}

        # time.sleep() for server processing was here - REMOVED
        
        action_duration_ms = (time.time() - action_start_time) * 1000 
        task_subtype = details.get("task_subtype", "generic_processing")
        result_data = f"{task_type}_completed_for_{task_subtype}"
        
        self.log_debug(f"Processed server task '{task_type}' (subtype: {task_subtype}, Job: {self.current_job_id}) in {action_duration_ms:.0f}ms. Load: {action_load_cost}. Result: {result_data[:30]}")
        return {
            'success': True, 'load_consumed': action_load_cost,
            'processing_time_ms': action_duration_ms,
            'result_data': result_data
        }

    def can_handle_task(self, task_type: str, details: Optional[Dict] = None) -> Tuple[bool, str]:
        if task_type == "PERIODIC_HEALTH_CHECK":
            return True, "Can handle health check."
        if task_type == "transmit" or task_type == "connect":
            return True, f"Can handle general communication task '{task_type}'."
        if self.is_server_type and (task_type == "ZONE_SERVER_TASK" or task_type == "SERVER_COMM_TASK"):
            return True, f"Server can handle '{task_type}'."
        if task_type == self.protocol: 
             return True, f"Can handle protocol-specific task '{self.protocol}'."
        
        return False, f"Communicating device (protocol: {self.protocol}, server: {self.is_server_type}) does not support task '{task_type}'."

    def _try_work_with_me_delegation(self, from_device_orig: Optional[Device], task_type_orig: str, 
                                     load_requested_orig: int, details_orig: Dict, 
                                     original_request_start_time: float) -> Optional[Dict[str, Any]]:
        if not self.is_server_type: 
            return None
        if not self.relationships.get("work-with-me"):
            self.log_debug(f"No 'work-with-me' partners for server task '{task_type_orig}' (Job: {self.current_job_id}).")
            return None

        delegation_details = details_orig.copy()
        delegation_details["delegator_device_id"] = self.device_id
        delegation_details["is_delegated_work_with_me"] = True # Flag that this is a delegated task

        partners_to_try = self.relationships["work-with-me"]
        if self.framework_variant == "full_siot":
            partners_to_try = sorted(
                partners_to_try,
                key=lambda rel: self.trust_scores.get(rel['device'].device_id, 0.0) if rel.get('device') else 0.0,
                reverse=True
            )

        for rel_entry in partners_to_try:
            partner_server = rel_entry.get('device')
            if not isinstance(partner_server, CommunicatingDevice) or not partner_server.is_server_type or partner_server.status != "active":
                continue 

            # Prevent delegating back to the original delegator in this specific attempt
            if "delegator_device_id" in details_orig and partner_server.device_id == details_orig["delegator_device_id"]:
                self.log_debug(f"Skipping 'work-with-me' to {partner_server.nameShort()}: it was the original delegator.")
                continue
            if partner_server.device_id == self.device_id: # Prevent delegating to self
                self.log_debug(f"Skipping 'work-with-me' to self for task '{task_type_orig}' (Job: {self.current_job_id}).")
                continue

            policy_id_str = rel_entry.get('policy_id', "server_collaboration_policy_v1")
            active_policy = DEFAULT_POLICY_STORE.get(policy_id_str, {})
            
            if self.framework_variant == "full_siot":
                trust_threshold = active_policy.get('rules', {}).get('min_trust_for_delegation', 0.5)
                current_trust_in_partner = self.trust_scores.get(partner_server.device_id, 0.0)
                if current_trust_in_partner < trust_threshold:
                    self.log_info(f"Skipping 'work-with-me' with {partner_server.nameShort()} for task '{task_type_orig}' (Job: {self.current_job_id}): Trust {current_trust_in_partner:.2f} < Threshold {trust_threshold:.2f}")
                    continue
            
            self.log_info(f"Attempting 'work-with-me' delegation of task '{task_type_orig}' (Job: {self.current_job_id}) to partner {partner_server.nameShort()}.")
            
            delegation_outcome = partner_server.handle_request(
                from_device=self,
                task_type=task_type_orig, 
                load_requested=load_requested_orig,
                details=delegation_details
            )
            
            if self.framework_variant == "full_siot" and delegation_outcome.get('measured_qos_for_requestor'):
                 self.update_trust_from_qoe(partner_server, f"delegate_wwm_{task_type_orig}", delegation_outcome['measured_qos_for_requestor'], "requester_of_delegation")

            if delegation_outcome.get("success"):
                self.log_event("WorkWithMeSuccess", f"'work-with-me' delegation to {partner_server.nameShort()} for task '{task_type_orig}' (Job: {self.current_job_id}) SUCCEEDED.")
                if self.sim_metrics_ref: 
                    self.sim_metrics_ref['work_with_me_delegations_successful'] = self.sim_metrics_ref.get('work_with_me_delegations_successful', 0) + 1
                
                final_outcome_for_original_requestor = {
                    'success': True,
                    'reason': f'task_completed_via_work_with_me_by_{partner_server.nameShort()}',
                    'result_data': delegation_outcome.get('result_data'), 
                    'measured_qos_for_requestor': delegation_outcome.get('measured_qos_for_requestor'),
                    'request_start_time': original_request_start_time
                }
                if from_device_orig and final_outcome_for_original_requestor.get('measured_qos_for_requestor'):
                     self.update_trust_from_qoe(from_device_orig, task_type_orig, final_outcome_for_original_requestor['measured_qos_for_requestor'], interaction_role="performer_via_delegation")
                return final_outcome_for_original_requestor
            else:
                self.log_warning(f"'work-with-me' delegation to {partner_server.nameShort()} for task '{task_type_orig}' (Job: {self.current_job_id}) FAILED. Reason: {delegation_outcome.get('reason')}")

        self.log_event("WorkWithMeFailure", f"All 'work-with-me' delegation attempts failed for task '{task_type_orig}' (Job: {self.current_job_id}).", level="warning")
        if self.sim_metrics_ref:
            self.sim_metrics_ref['work_with_me_delegations_failed'] = self.sim_metrics_ref.get('work_with_me_delegations_failed', 0) + 1
        return None


    def handle_request(self, from_device: Optional[Device], task_type: str,
                       load_requested: int = 10, details: Optional[Dict] = None) -> Dict[str, Any]:
        details = details if details is not None else {}
        self.current_job_id = details.get("id", details.get("job_id"))

        effective_load_requested = load_requested
        if self.behavior_profile == 'policy_violator' and self.is_server_type and random.random() < 0.2:
            effective_load_requested = max(1, int(load_requested * random.uniform(0.5, 0.8)))
            self.log_debug(f"Policy violator Server {self.nameShort()} considering task '{task_type}' (Job: {self.current_job_id}) with perceived load {effective_load_requested} (actual: {load_requested})")

        base_acceptance_outcome = super().handle_request(from_device, task_type, effective_load_requested, details)
        request_start_time = base_acceptance_outcome.get('request_start_time', time.time())

        if not base_acceptance_outcome.get('success'):
            # Check if this is already a delegated task before trying to delegate again
            if not details.get('is_delegated_work_with_me'): # <<<< ADDED GUARD
                if self.is_server_type and (task_type == "ZONE_SERVER_TASK" or task_type == "SERVER_COMM_TASK") and \
                   self.framework_variant in ["social_basic", "full_siot"] and \
                   base_acceptance_outcome.get('reason') == 'rejected_by_load_negotiation_or_pre_checks':
                    
                    self.log_info(f"Server task '{task_type}' (Job: {self.current_job_id}) rejected for self-execution: {base_acceptance_outcome.get('reason')}. Attempting 'work-with-me'.")
                    delegation_outcome = self._try_work_with_me_delegation(from_device, task_type, load_requested, details, request_start_time)
                    if delegation_outcome and delegation_outcome.get('success'):
                        self.current_job_id = None
                        return delegation_outcome
            
            self.current_job_id = None
            return base_acceptance_outcome

        can_handle_bool, reason_str = self.can_handle_task(task_type, details)
        if not can_handle_bool:
            self.log_warning(f"Cannot handle specialized task '{task_type}' (Job: {self.current_job_id}). Reason: {reason_str}")
            overall_response_time_ms = (time.time() - request_start_time) * 1000
            measured_qos = {'task_success_binary': 0, 'response_time_ms': overall_response_time_ms, 'expected_load_for_task': load_requested}
            if from_device: self.update_trust_from_qoe(from_device, task_type, measured_qos, interaction_role="performer_rejected_specialized")
            self.current_job_id = None
            return {'success': False, 'reason': f'unsupported_task_type_by_comm_device:_{reason_str}', 
                    'measured_qos_for_requestor': measured_qos, 'request_start_time': request_start_time }

        action_result = None
        if task_type == "transmit":
            message = details.get('message', f"default_ping_from_{self.nameShort()}_to_target")
            target_comm_device = details.get('target_comm_device')
            if not target_comm_device or not isinstance(target_comm_device, Device):
                self.log_warning(f"Invalid or no target_comm_device provided for transmit task (Job: {self.current_job_id}).")
                action_result = {'success': False, 'reason': 'invalid_target_device_for_transmit'}
            else:
                self.connect_device(target_comm_device) 
                action_result = self._perform_transmit_action(message, target_comm_device, load_requested, details)
        elif self.is_server_type and (task_type == "ZONE_SERVER_TASK" or task_type == "SERVER_COMM_TASK" or task_type == "PERIODIC_HEALTH_CHECK"):
            action_result = self._perform_server_processing_action(task_type, load_requested, details)
        elif task_type == "connect":
            device_to_connect = details.get("device_to_connect")
            if device_to_connect and isinstance(device_to_connect, Device):
                connect_success = self.connect_device(device_to_connect)
                action_result = {'success': connect_success, 'load_consumed': 1, 'processing_time_ms': 10, 'value': 'CONNECTED' if connect_success else 'CONNECT_FAILED'}
            else:
                action_result = {'success': False, 'reason': 'invalid_device_for_connect'}
        else: 
            action_result = {'success': False, 'reason': f'internal_unhandled_task_type:_{task_type}'}
        
        load_consumed_by_action = action_result.get("load_consumed", 0)

        if not action_result.get("success"):
            self.log_warning(f"Primary execution of task '{task_type}' (Job: {self.current_job_id}) FAILED. Reason: {action_result.get('reason', 'unknown_action_failure')}")
            if load_consumed_by_action > 0: self.reduce_load(load_consumed_by_action)

            # Check if this is already a delegated task before trying to delegate again
            if not details.get('is_delegated_work_with_me'): # <<<< ADDED GUARD
                if self.is_server_type and (task_type == "ZONE_SERVER_TASK" or task_type == "SERVER_COMM_TASK") and \
                   self.framework_variant in ["social_basic", "full_siot"] and \
                   action_result.get('reason') in ['overload_at_server_action', 'internal_server_fault']:
                    
                    self.log_info(f"Server task '{task_type}' (Job: {self.current_job_id}) failed on self. Attempting 'work-with-me'.")
                    delegation_outcome = self._try_work_with_me_delegation(from_device, task_type, load_requested, details, request_start_time)
                    if delegation_outcome and delegation_outcome.get('success'):
                        self.current_job_id = None
                        return delegation_outcome

            overall_response_time_ms_fail = (time.time() - request_start_time) * 1000
            measured_qos_failure = {'task_success_binary': 0, 'response_time_ms': overall_response_time_ms_fail, 'expected_load_for_task': load_requested, 'load_consumed':0, 'failure_reason': action_result.get('reason')}
            if from_device: self.update_trust_from_qoe(from_device, task_type, measured_qos_failure, interaction_role="performer_failed_action")
            self.current_job_id = None
            return {'success': False, 'reason': action_result.get('reason', 'comm_device_task_failed_no_delegation'), 
                    'measured_qos_for_requestor': measured_qos_failure, 'request_start_time': request_start_time}

        overall_response_time_ms_succ = (time.time() - request_start_time) * 1000
        processing_time_ms_succ = action_result.get('processing_time_ms', overall_response_time_ms_succ)
        
        measured_qos_success = {
            'task_success_binary': 1, 'response_time_ms': overall_response_time_ms_succ, 
            'load_consumed': load_consumed_by_action, 'expected_load_for_task': load_requested,
            'processing_time_ms': processing_time_ms_succ,
        }
        if task_type == "transmit":
            measured_qos_success['message_delivered_binary'] = action_result.get('message_delivered_binary', 0)
        elif self.is_server_type and (task_type == "ZONE_SERVER_TASK" or task_type == "SERVER_COMM_TASK"):
            measured_qos_success['result_data'] = action_result.get('result_data')
        elif task_type == "connect":
             measured_qos_success['value_returned'] = action_result.get('value')


        if from_device: self.update_trust_from_qoe(from_device, task_type, measured_qos_success, interaction_role="performer")
        
        if not details.get("delegator_device_id"): 
            reward_key = "iot_app_reward"
            base_reward_val = self.base_transmit_reward
            if self.is_server_type and (task_type == "ZONE_SERVER_TASK" or task_type == "SERVER_COMM_TASK"):
                base_reward_val = self.base_server_task_reward
            self.receive_income(details.get(reward_key, base_reward_val), f"{task_type} completion")
        
        result_val_log = str(action_result.get('result_data', action_result.get('value', 'N/A')))[:30]
        self.log_info(f"EXECUTED '{task_type}' (Job: {self.current_job_id}) for {from_device.nameShort() if from_device else 'autonomous'}. Result/Target: {result_val_log}")
        self.current_job_id = None
        
        return_payload = {'success': True, 'reason': f'{task_type}_successful', 
                          'measured_qos_for_requestor': measured_qos_success, 
                          'request_start_time': request_start_time}
        if 'result_data' in action_result: return_payload['result_data'] = action_result['result_data']
        if 'value' in action_result: return_payload['value'] = action_result['value']
        return return_payload
