# src/devices/actuating_device.py
import random
import time
from typing import List, Dict, Any, Optional, Tuple, TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from .device import Device # For type hinting
    from ..utils.logger import SimulationLogger


# Import Device and DEFAULT_POLICY_STORE from the correct location
from .device import Device, DEFAULT_POLICY_STORE 


class ActuatingDevice(Device):
    def __init__(self, device_id: str, name: str, max_load: int = 100,
                 actuator_type: str = "switch", # e.g., hvac_control, light_switch, door_lock
                 framework_variant: str = "full_siot",
                 logger_instance: Optional['SimulationLogger'] = None,
                 current_minute_provider: Optional[Callable[[], int]] = None,
                 **kwargs): 
        
        specific_capabilities = ["actuate", actuator_type]
        if "PERIODIC_HEALTH_CHECK" not in specific_capabilities: 
            specific_capabilities.append("PERIODIC_HEALTH_CHECK")
        
        if actuator_type == "hvac_control":
            specific_capabilities.append("ADJUST_HVAC")
        elif actuator_type == "light_switch": 
            specific_capabilities.append("TOGGLE_LIGHT")
            
        super().__init__(device_id, name, max_load, framework_variant,
                         capabilities=specific_capabilities,
                         logger_instance=logger_instance,
                         current_minute_provider=current_minute_provider,
                         **kwargs) 
        self.actuator_type = actuator_type
        
        if self.actuator_type in ["light_switch", "smart_plug", "alarm_siren", "switch"]:
            self.current_state: Any = "OFF"
        elif self.actuator_type == "door_lock":
            self.current_state: Any = "LOCKED"
        elif self.actuator_type == "hvac_control":
            self.current_state: Any = {'mode': "OFF", 'setpoint': 22.0, 'current_temp_report': 22.0}
        else:
            self.current_state: Any = "IDLE" 

        self.base_actuate_reward = 12 

        if self.behavior_profile != 'deceptive':
            if 'state_change_latency_ms' not in self.announced_qos:
                 self.announced_qos['state_change_latency_ms'] = random.uniform(5, 50)
                 if 'state_change_latency_ms' not in self.qoe_thresholds: 
                    self.qoe_thresholds['state_change_latency_ms'] = {'sigma': 20.0, 'delta': 10.0}
            if 'command_reliability' not in self.announced_qos: 
                self.announced_qos['command_reliability'] = random.uniform(0.95, 0.99)
                if 'command_reliability' not in self.qoe_thresholds: 
                    self.qoe_thresholds['command_reliability'] = self.qoe_thresholds.get('task_success_rate', {'sigma': 0.15, 'delta': 0.10}) 
        elif 'state_change_latency_ms' not in self.announced_qos: 
            self.announced_qos['state_change_latency_ms'] = random.uniform(3, 15) 
            self.announced_qos['command_reliability'] = random.uniform(0.99, 0.999) 
            if 'state_change_latency_ms' not in self.qoe_thresholds:
                 self.qoe_thresholds['state_change_latency_ms'] = {'sigma': 20.0, 'delta': 10.0}
            if 'command_reliability' not in self.qoe_thresholds:
                 self.qoe_thresholds['command_reliability'] = self.qoe_thresholds.get('task_success_rate', {'sigma': 0.15, 'delta': 0.10})


    def _perform_actuation_action(self, task_type_being_handled: str, load_requested: int, details: Optional[Dict] = None) -> Dict[str, Any]:
        details = details or {}
        command = details.get('command') 
        action_start_time = time.time()
        
        load_factor = self.announced_qos.get('load_efficiency', 1.0) * random.uniform(0.9, 1.1)
        action_load_cost = int(load_requested * load_factor)
        action_load_cost = max(1, action_load_cost) 

        if task_type_being_handled == "PERIODIC_HEALTH_CHECK":
            if self.consume_load(1): 
                self.log_debug(f"Performed {task_type_being_handled}, status: OK.")
                return {'success': True, 'new_state': self.current_state, 'previous_state': self.current_state, 
                        'command_received': "HEALTH_CHECK", 'load_consumed': 1, 
                        'processing_time_ms': (time.time() - action_start_time) * 1000,
                        'state_changed_correctly_binary': 1} 
            else:
                return {'success': False, 'reason': 'overload_at_health_check', 'load_consumed': 0, 'processing_time_ms': (time.time() - action_start_time) * 1000, 'state_changed_correctly_binary': 0}

        if random.random() < self.fault_probability:
            self.log_warning(f"Simulating internal fault during actuation action for {task_type_being_handled} (Job: {self.current_job_id}).")
            processing_time_ms = (time.time() - action_start_time) * 1000
            if self.sim_metrics_ref: self.sim_metrics_ref['faulty_device_actions_failed'] = self.sim_metrics_ref.get('faulty_device_actions_failed',0) + 1
            return {'success': False, 'reason': 'internal_device_fault', 'load_consumed': 0,
                    'processing_time_ms': processing_time_ms, 'state_changed_correctly_binary': 0,
                    'new_state': self.current_state, 'previous_state': self.current_state, 'command_received': command}

        if not self.consume_load(action_load_cost):
            return {'success': False, 'reason': 'overload_at_action', 'load_consumed': 0,
                    'processing_time_ms': (time.time() - action_start_time) * 1000,
                    'state_changed_correctly_binary': 0, 'new_state': self.current_state, 'previous_state': self.current_state, 'command_received': command}

        # Simulating state change latency was here, now removed/commented out
        # announced_latency = self.announced_qos.get('state_change_latency_ms', 30)
        # ...
        # if actual_processing_delay_sec > 0.001 : time.sleep(actual_processing_delay_sec) # COMMENTED OUT

        previous_state = self.current_state
        
        announced_reliability = self.announced_qos.get('command_reliability', 0.98)
        effective_reliability = announced_reliability
        if self.behavior_profile == 'deceptive': 
            effective_reliability *= self.deception_factor if self.deception_factor != 0 else 1.0
            
        action_succeeded = random.random() < effective_reliability
        state_changed_as_commanded = False

        if action_succeeded:
            if self.actuator_type == "hvac_control" and isinstance(command, dict):
                new_hvac_state = self.current_state.copy() if isinstance(self.current_state, dict) else {'mode': "OFF", 'setpoint': 22.0}
                if 'target_mode' in command: new_hvac_state['mode'] = command['target_mode'] 
                if 'setpoint' in command: new_hvac_state['setpoint'] = float(command['setpoint'])
                if 'current_temp_report' in command : new_hvac_state['current_temp_report'] = float(command['current_temp_report'])
                self.current_state = new_hvac_state
                state_changed_as_commanded = True 
            elif self.actuator_type == "light_switch" and command in ["ON", "OFF"]:
                self.current_state = command
                state_changed_as_commanded = True
            elif self.actuator_type == "door_lock" and command in ["LOCK", "UNLOCK"]:
                self.current_state = command.upper() 
                state_changed_as_commanded = True
            else: 
                self.current_state = command 
                state_changed_as_commanded = (self.current_state == command) 
            
            self.log_debug(f"Actuated {self.actuator_type} (task: {task_type_being_handled}, Job: {self.current_job_id}) with command '{str(command)[:50]}'. Prev state: '{str(previous_state)[:30]}', New state: '{str(self.current_state)[:30]}'")
        else:
            self.log_warning(f"Actuation command '{str(command)[:50]}' for {self.actuator_type} (task: {task_type_being_handled}, Job: {self.current_job_id}) FAILED to execute reliably (simulated). State remains '{str(self.current_state)[:30]}'")
            state_changed_as_commanded = False 
            
        action_duration_ms = (time.time() - action_start_time) * 1000
        return {
            'success': action_succeeded,
            'new_state': self.current_state,
            'previous_state': previous_state,
            'command_received': command,
            'load_consumed': action_load_cost,
            'processing_time_ms': action_duration_ms,
            'state_changed_correctly_binary': 1 if state_changed_as_commanded and action_succeeded else 0
        }

    def can_handle_task(self, task_type: str, details: Optional[Dict] = None) -> Tuple[bool, str]:
        if task_type == "PERIODIC_HEALTH_CHECK":
            return True, "Can handle health check."
        if task_type == "actuate": 
            return True, "Can handle generic 'actuate'."
        if task_type == self.actuator_type: 
            return True, f"Can handle specific type '{self.actuator_type}'."
        
        if task_type == "ADJUST_HVAC" and self.actuator_type == "hvac_control":
            return True, "Can handle 'ADJUST_HVAC'."
        if task_type == "TOGGLE_LIGHT" and self.actuator_type == "light_switch":
            return True, "Can handle 'TOGGLE_LIGHT'."
        
        return False, f"Actuator type '{self.actuator_type}' does not support task '{task_type}'."

    def _try_back_me_relationship(self, from_device_orig: Optional[Device], task_type_orig: str, 
                                  load_requested_orig: int, details_orig: Dict, 
                                  original_request_start_time: float) -> Optional[Dict[str, Any]]:
        if not self.relationships.get("back-me"):
            self.log_debug(f"No 'back-me' partners configured for task '{task_type_orig}' (Job: {self.current_job_id}).")
            return None

        delegation_details = details_orig.copy()
        delegation_details["delegator_device_id"] = self.device_id 
        delegation_details["is_backup_attempt"] = True 

        partners_to_try = self.relationships["back-me"]
        if self.framework_variant == "full_siot":
            partners_to_try = sorted(
                partners_to_try,
                key=lambda rel: self.trust_scores.get(rel['device'].device_id, 0.0) if rel.get('device') else 0.0,
                reverse=True
            )
        
        for rel_entry in partners_to_try:
            backup_partner = rel_entry.get('device')
            if not isinstance(backup_partner, Device) or backup_partner.status != "active":
                self.log_debug(f"Skipping 'back-me' partner {backup_partner.nameShort() if backup_partner else 'Unknown'}: not active or invalid.")
                continue
            
            # Prevent delegating back to the original delegator in a direct loop for this specific attempt
            if "delegator_device_id" in details_orig and backup_partner.device_id == details_orig["delegator_device_id"]:
                 self.log_debug(f"Skipping 'back-me' to {backup_partner.nameShort()}: it was the original delegator of this backup chain.")
                 continue


            policy_id_str = rel_entry.get('policy_id', "default_task_policy") 
            active_policy = DEFAULT_POLICY_STORE.get(policy_id_str, {}) 
            
            if self.framework_variant == "full_siot":
                trust_threshold = active_policy.get('rules', {}).get('backup_priority_threshold', 0.5) 
                current_trust_in_partner = self.trust_scores.get(backup_partner.device_id, 0.0)
                if current_trust_in_partner < trust_threshold:
                    self.log_info(f"Skipping 'back-me' with {backup_partner.nameShort()} for task '{task_type_orig}' (Job: {self.current_job_id}): Trust {current_trust_in_partner:.2f} < Threshold {trust_threshold:.2f}")
                    continue
            
            self.log_info(f"Attempting to delegate task '{task_type_orig}' (Job: {self.current_job_id}) to 'back-me' partner {backup_partner.nameShort()}.")
            
            delegation_outcome = backup_partner.handle_request(
                from_device=self, 
                task_type=task_type_orig, 
                load_requested=load_requested_orig, 
                details=delegation_details 
            )

            if self.framework_variant == "full_siot" and delegation_outcome.get('measured_qos_for_requestor'):
                self.update_trust_from_qoe(backup_partner, f"backup_delegate_{task_type_orig}", delegation_outcome['measured_qos_for_requestor'], "requester_of_backup")

            if delegation_outcome.get("success"):
                self.log_event("BackMeSuccess", f"'back-me' successful with {backup_partner.nameShort()} for task '{task_type_orig}' (Job: {self.current_job_id}).")
                if self.sim_metrics_ref:
                    self.sim_metrics_ref['back_me_invocations_successful'] = self.sim_metrics_ref.get('back_me_invocations_successful', 0) + 1
                
                final_outcome_for_original_requestor = {
                    'success': True,
                    'reason': f'task_completed_via_back_me_by_{backup_partner.nameShort()}',
                    'value': delegation_outcome.get('value'),
                    'new_state': delegation_outcome.get('new_state'), 
                    'previous_state': delegation_outcome.get('previous_state'), 
                    'measured_qos_for_requestor': delegation_outcome.get('measured_qos_for_requestor'), 
                    'request_start_time': original_request_start_time 
                }
                if from_device_orig and final_outcome_for_original_requestor.get('measured_qos_for_requestor'):
                     self.update_trust_from_qoe(from_device_orig, task_type_orig, final_outcome_for_original_requestor['measured_qos_for_requestor'], interaction_role="performer_via_backup")
                return final_outcome_for_original_requestor
            else:
                self.log_warning(f"'back-me' attempt FAILED with {backup_partner.nameShort()} for task '{task_type_orig}' (Job: {self.current_job_id}). Reason: {delegation_outcome.get('reason')}")
        
        self.log_event("BackMeFailure", f"All 'back-me' attempts failed for task '{task_type_orig}' (Job: {self.current_job_id}).", level="warning")
        if self.sim_metrics_ref:
            self.sim_metrics_ref['back_me_invocations_failed'] = self.sim_metrics_ref.get('back_me_invocations_failed', 0) + 1
        return None 

    def handle_request(self, from_device: Optional[Device], task_type: str,
                       load_requested: int = 10, details: Optional[Dict] = None) -> Dict[str, Any]:
        details = details if details is not None else {}
        self.current_job_id = details.get("id", details.get("job_id"))
        
        effective_load_requested = load_requested
        if self.behavior_profile == 'policy_violator' and "ADJUST_HVAC" in task_type and random.random() < 0.3:
            effective_load_requested = max(1, int(load_requested * random.uniform(0.4, 0.7)))
            self.log_debug(f"Policy violator {self.nameShort()} considering task '{task_type}' (Job: {self.current_job_id}) with perceived load {effective_load_requested} (actual: {load_requested})")
        
        base_acceptance_outcome = super().handle_request(from_device, task_type, effective_load_requested, details)
        request_start_time = base_acceptance_outcome.get('request_start_time', time.time())

        if not base_acceptance_outcome.get('success'):
            # Check if this is already a backup attempt to prevent loops
            if not details.get('is_backup_attempt'): # <<<< CORRECTED CHECK
                if self.framework_variant in ["social_basic", "full_siot"] and \
                   base_acceptance_outcome.get('reason') == 'rejected_by_load_negotiation_or_pre_checks':
                    
                    self.log_info(f"Task '{task_type}' (Job: {self.current_job_id}) rejected for self-execution due to: {base_acceptance_outcome.get('reason')}. Attempting 'back-me'.")
                    backup_outcome = self._try_back_me_relationship(from_device, task_type, load_requested, details, request_start_time) 
                    if backup_outcome and backup_outcome.get('success'):
                        self.current_job_id = None
                        return backup_outcome 
            
            self.current_job_id = None
            return base_acceptance_outcome 

        can_handle_bool, reason_str = self.can_handle_task(task_type, details)
        if not can_handle_bool:
            self.log_warning(f"Cannot handle specialized task '{task_type}' (Job: {self.current_job_id}). Reason: {reason_str}")
            overall_response_time_ms = (time.time() - request_start_time) * 1000
            measured_qos = {'task_success_binary': 0, 'response_time_ms': overall_response_time_ms, 'expected_load_for_task': load_requested}
            if from_device: self.update_trust_from_qoe(from_device, task_type, measured_qos, interaction_role="performer_rejected_specialized")
            self.current_job_id = None
            return {'success': False, 'reason': f'unsupported_task_type_by_actuator_specialization:_{reason_str}', 
                    'measured_qos_for_requestor': measured_qos, 'request_start_time': request_start_time }

        action_result = self._perform_actuation_action(task_type, load_requested, details)
        load_consumed_by_action = action_result.get("load_consumed", 0)

        if not action_result.get("success"):
            self.log_warning(f"Primary execution of task '{task_type}' (Job: {self.current_job_id}) FAILED. Reason: {action_result.get('reason', 'unknown_action_failure')}")
            if load_consumed_by_action > 0: self.reduce_load(load_consumed_by_action) 

            # Check if this is already a backup attempt to prevent loops
            if self.framework_variant in ["social_basic", "full_siot"] and not details.get('is_backup_attempt'): 
                self.log_info(f"Primary execution of task '{task_type}' (Job: {self.current_job_id}) failed. Attempting 'back-me'.")
                backup_outcome = self._try_back_me_relationship(from_device, task_type, load_requested, details, request_start_time)
                if backup_outcome and backup_outcome.get('success'):
                    self.current_job_id = None
                    return backup_outcome
            
            overall_response_time_ms_fail = (time.time() - request_start_time) * 1000
            measured_qos_failure = {'task_success_binary': 0, 'response_time_ms': overall_response_time_ms_fail, 'expected_load_for_task': load_requested, 'load_consumed':0, 'failure_reason': action_result.get('reason')}
            if from_device: self.update_trust_from_qoe(from_device, task_type, measured_qos_failure, interaction_role="performer_failed_action")
            self.current_job_id = None
            return {'success': False, 'reason': action_result.get('reason', 'actuation_failed_no_backup'), 
                    'measured_qos_for_requestor': measured_qos_failure, 'request_start_time': request_start_time}

        overall_response_time_ms_succ = (time.time() - request_start_time) * 1000
        processing_time_ms_succ = action_result.get('processing_time_ms', overall_response_time_ms_succ)
        
        measured_qos_success = {
            'task_success_binary': 1, 'response_time_ms': overall_response_time_ms_succ, 
            'load_consumed': load_consumed_by_action, 'expected_load_for_task': load_requested,
            'processing_time_ms': processing_time_ms_succ,
            'new_state': action_result.get("new_state"), 
            'state_changed_correctly_binary': action_result.get('state_changed_correctly_binary', 0)
        }
        if from_device: 
            self.update_trust_from_qoe(from_device, task_type, measured_qos_success, interaction_role="performer")
        
        if not details.get("delegator_device_id"): 
            self.receive_income(details.get('iot_app_reward', self.base_actuate_reward), f"{task_type} completion")
        
        self.log_info(f"EXECUTED '{task_type}' (Job: {self.current_job_id}) for {from_device.nameShort() if from_device else 'autonomous_task'}, cmd: '{str(details.get('command'))[:30]}...', new_state: {str(action_result.get('new_state'))[:30]}")
        self.current_job_id = None
        return {'success': True, 'reason': f'{task_type}_successful', 
                'new_state':action_result.get('new_state'),
                'previous_state':action_result.get('previous_state'),
                'measured_qos_for_requestor': measured_qos_success, 
                'request_start_time': request_start_time}

