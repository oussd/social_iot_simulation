import random
import time
from typing import List, Dict, Any, Optional
from .device import Device, QoELevel # Base class
# Ensure there are NO lines here like: from .actuating_device import ActuatingDevice

class ActuatingDevice(Device):
    def __init__(self, device_id: str, name: str, max_load: int = 100,
                 actuator_type: str = "switch",
                 framework_variant: str = "full_siot",
                 logger_instance=None,
                 current_minute_provider=None,
                 **kwargs): 
        super().__init__(device_id, name, max_load, framework_variant,
                         capabilities=["actuate", actuator_type],
                         logger_instance=logger_instance,
                         current_minute_provider=current_minute_provider,
                         **kwargs) 
        self.actuator_type = actuator_type
        
        if self.actuator_type in ["light_switch", "smart_plug", "alarm_siren"]:
            self.current_state: Any = "OFF"
        elif self.actuator_type == "door_lock":
            self.current_state: Any = "LOCKED"
        elif self.actuator_type == "hvac_control":
            self.current_state: Any = {'mode': "OFF", 'setpoint': 22}
        else:
            self.current_state: Any = "IDLE"

        self.base_actuate_reward = 12

        if self.behavior_profile != 'deceptive':
            if 'state_change_latency_ms' not in self.announced_qos:
                 self.announced_qos['state_change_latency_ms'] = random.uniform(5, 50)
                 self.qoe_thresholds['state_change_latency_ms'] = {'sigma': 20.0, 'delta': 10.0}
            if 'command_reliability' not in self.announced_qos:
                self.announced_qos['command_reliability'] = random.uniform(0.95, 0.99)
                self.qoe_thresholds['command_reliability'] = self.qoe_thresholds.get('task_success_rate', {'sigma': 0.15, 'delta': 0.10})
        elif 'state_change_latency_ms' not in self.announced_qos: 
            self.announced_qos['state_change_latency_ms'] = random.uniform(5, 25) 
            self.announced_qos['command_reliability'] = random.uniform(0.98, 0.999) 
            self.qoe_thresholds['state_change_latency_ms'] = {'sigma': 20.0, 'delta': 10.0}
            self.qoe_thresholds['command_reliability'] = self.qoe_thresholds.get('task_success_rate', {'sigma': 0.15, 'delta': 0.10})


    def _perform_actuation_action(self, command: Any, expected_load_for_task: int) -> Dict[str, Any]:
        action_start_time = time.time()
        load_factor = self.announced_qos.get('load_efficiency', 1.0) * random.uniform(0.9, 1.1)
        action_load_cost = int(expected_load_for_task * load_factor)
        action_load_cost = max(1, action_load_cost)

        if random.random() < self.fault_probability:
            self.log_warning(f"Simulating internal fault during actuation action.") # CORRECTED
            processing_time_ms = (time.time() - action_start_time) * 1000
            if self.sim_metrics_ref: self.sim_metrics_ref['faulty_device_actions_failed'] = self.sim_metrics_ref.get('faulty_device_actions_failed',0) + 1
            return {'success': False, 'reason': 'internal_device_fault', 'load_consumed': 0,
                    'processing_time_ms': processing_time_ms, 'state_changed_correctly_binary': 0,
                    'new_state': self.current_state, 'previous_state': self.current_state, 'command_received': command}

        if not self.consume_load(action_load_cost):
            return {'success': False, 'reason': 'overload_at_action', 'load_consumed': 0,
                    'processing_time_ms': (time.time() - action_start_time) * 1000,
                    'state_changed_correctly_binary': 0, 'new_state': self.current_state, 'previous_state': self.current_state, 'command_received': command}

        announced_latency = self.announced_qos.get('state_change_latency_ms', 30)
        effective_latency = announced_latency
        if self.behavior_profile == 'deceptive':
            effective_latency /= self.deception_factor 

        simulated_state_change_latency_ms = effective_latency * random.uniform(0.7, 1.3)
        time.sleep(simulated_state_change_latency_ms / 1000.0)

        previous_state = self.current_state
        
        announced_reliability = self.announced_qos.get('command_reliability', 0.98)
        effective_reliability = announced_reliability
        if self.behavior_profile == 'deceptive':
            effective_reliability *= self.deception_factor 
            
        action_succeeded = random.random() < effective_reliability
        state_changed_as_commanded = False

        if action_succeeded:
            if self.actuator_type == "hvac_control" and isinstance(command, dict):
                new_hvac_state = self.current_state.copy() if isinstance(self.current_state, dict) else {}
                new_hvac_state.update(command)
                self.current_state = new_hvac_state
                state_changed_as_commanded = True
            else:
                self.current_state = command
                state_changed_as_commanded = (self.current_state == command)
            # This was the line causing the AttributeError in the traceback
            self.log_debug(f"Actuated {self.actuator_type} from '{str(previous_state)[:30]}' to '{str(self.current_state)[:30]}'") # CORRECTED
        else:
            self.log_warning(f"Actuation command '{str(command)[:50]}' for {self.actuator_type} FAILED to execute reliably (simulated). State remains '{str(self.current_state)[:30]}'") # CORRECTED
            state_changed_as_commanded = False
            
        action_duration_ms = (time.time() - action_start_time) * 1000
        return {
            'success': action_succeeded,
            'new_state': self.current_state,
            'previous_state': previous_state,
            'command_received': command,
            'load_consumed': action_load_cost,
            'processing_time_ms': action_duration_ms,
            'state_changed_correctly_binary': 1 if state_changed_as_commanded else 0
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

        if task_type != 'actuate' and task_type != self.actuator_type:
            self.log_warning(f"Rejected: {self.nameShort()} cannot handle task type '{task_type}'. Expected 'actuate' or '{self.actuator_type}'.") # CORRECTED
            overall_response_time_ms = (time.time() - request_start_time) * 1000
            measured_qos = {'task_success_binary': 0, 'response_time_ms': overall_response_time_ms, 'expected_load_for_task': load_requested}
            self.update_trust_from_qoe(from_device, task_type, measured_qos, interaction_role="performer")
            return {'success': False, 'reason': 'unsupported_task_type_by_specialization',
                    'measured_qos_for_requestor': measured_qos, 'request_start_time': request_start_time}

        command = details.get('command')
        if command is None:
            if self.actuator_type == "light_switch" or self.actuator_type == "smart_plug":
                command = "OFF" if self.current_state == "ON" else "ON"
            elif self.actuator_type == "door_lock":
                command = "UNLOCK" if self.current_state == "LOCKED" else "LOCKED"
            elif self.actuator_type == "hvac_control":
                command = {'mode': "AUTO"} if not isinstance(self.current_state, dict) or self.current_state.get('mode') == "OFF" else self.current_state
            else:
                command = "TRIGGER"

        action_result = self._perform_actuation_action(command, load_requested)
        
        overall_response_time_ms = (time.time() - request_start_time) * 1000
        measured_qos_for_trust_and_requestor = {
            'task_success_binary': 1 if action_result.get('success') else 0,
            'response_time_ms': overall_response_time_ms,
            'load_consumed': action_result.get('load_consumed', 0),
            'expected_load_for_task': load_requested, 
            'processing_time_ms': action_result.get('processing_time_ms', 0),
            'state_changed_correctly_binary': action_result.get('state_changed_correctly_binary', 0)
        }
        self.update_trust_from_qoe(from_device, task_type, measured_qos_for_trust_and_requestor, interaction_role="performer")

        if action_result.get('success'):
            self.log_info(f"EXECUTED '{task_type}' for {from_device.nameShort() if from_device else 'autonomous_task'}, cmd: '{str(command)[:30]}...', new_state: {str(action_result.get('new_state'))[:30]}") # CORRECTED
            iot_app_reward = details.get('iot_app_reward', self.base_actuate_reward if not from_device else 0)
            if iot_app_reward > 0: self.receive_income(iot_app_reward, f"{task_type.capitalize()} Task Completion")
            return {'success': True, 'reason': f'{task_type}_successful', 'new_state':action_result.get('new_state'),
                    'measured_qos_for_requestor': measured_qos_for_trust_and_requestor, 'request_start_time': request_start_time}
        else:
            self.log_warning(f"{task_type.capitalize()} execution FAILED for {from_device.nameShort() if from_device else 'autonomous_task'} with cmd '{str(command)[:30]}'. Reason: {action_result.get('reason','unknown')}") # CORRECTED
            if self.framework_variant in ["social_basic", "full_siot"]:
                 if self.behavior_profile == 'selfish' and random.random() < self.policy.get('selfish_low_backup_priority_factor', 0.0):
                     self.log_debug(f"Selfish device {self.nameShort()} is reluctant to seek backup after failure.") # CORRECTED
                 else:
                    for rel in self.relationships.get('back_me', []):
                        backup_device = rel.get('device')
                        if not backup_device: continue
                        if backup_device == from_device or (details.get('is_backup_attempt') and details.get('original_backup_initiator') == backup_device.device_id):
                            continue
                        
                        self.log_info(f"Attempting backup {task_type} with {backup_device.nameShort()}") # CORRECTED
                        backup_details = details.copy()
                        backup_details['is_backup_attempt'] = True
                        backup_details['original_backup_initiator'] = self.device_id
                        if self.behavior_profile == 'policy_violator' and 'iot_app_reward' in backup_details:
                            backup_details['iot_app_reward'] = backup_details.get('iot_app_reward',0) * random.uniform(0.3, 0.7)

                        backup_outcome = backup_device.handle_request(self, task_type, load_requested, backup_details)
                        self.update_trust_from_qoe(backup_device, task_type, backup_outcome.get('measured_qos_for_requestor',{}), "requester")
                        if backup_outcome.get('success'):
                            self.log_info(f"Backup {task_type} by {backup_device.nameShort()} SUCCEEDED.") # CORRECTED
                            if self.sim_metrics_ref and 'back_me_invocations_successful' in self.sim_metrics_ref:
                                self.sim_metrics_ref['back_me_invocations_successful'] +=1
                            return {**backup_outcome, 'backed_up_by': backup_device.device_id}
                        else:
                            if self.sim_metrics_ref and 'back_me_invocations_failed' in self.sim_metrics_ref:
                                self.sim_metrics_ref['back_me_invocations_failed'] +=1
            return {'success': False, 'reason': f"{task_type}_execution_failed_no_successful_backup: {action_result.get('reason','unknown')}",
                    'measured_qos_for_requestor': measured_qos_for_trust_and_requestor, 'request_start_time': request_start_time}
