# src/devices/actuating_device.py
import random
import time
from typing import List, Dict, Any, Optional
from .device import Device, QoELevel # Base class

class ActuatingDevice(Device):
    def __init__(self, device_id: str, name: str, max_load: int = 100,
                 actuator_type: str = "switch", # e.g., hvac_control, light_switch, door_lock
                 framework_variant: str = "full_siot",
                 logger_instance=None,
                 current_minute_provider=None,
                 **kwargs): 
        
        specific_capabilities = ["actuate", actuator_type]
        if "PERIODIC_HEALTH_CHECK" not in specific_capabilities: # All devices should handle this
            specific_capabilities.append("PERIODIC_HEALTH_CHECK")
        
        # Add descriptive job types to capabilities for clarity and potential future checks
        if actuator_type == "hvac_control":
            specific_capabilities.append("ADJUST_HVAC")
        elif actuator_type == "light_switch": 
            specific_capabilities.append("TOGGLE_LIGHT")
        # Add other mappings as needed for other actuator_types
            
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


    def _perform_actuation_action(self, task_type_being_handled: str, command: Any, expected_load_for_task: int, details: Optional[Dict] = None) -> Dict[str, Any]:
        details = details or {}
        action_start_time = time.time()
        load_factor = self.announced_qos.get('load_efficiency', 1.0) * random.uniform(0.9, 1.1)
        action_load_cost = int(expected_load_for_task * load_factor)
        action_load_cost = max(1, action_load_cost)

        if task_type_being_handled == "PERIODIC_HEALTH_CHECK":
            self.consume_load(1) 
            self.log_debug(f"Performed {task_type_being_handled}, status: OK.")
            return {'success': True, 'new_state': self.current_state, 'previous_state': self.current_state, 
                    'command_received': "HEALTH_CHECK", 'load_consumed': 1, 
                    'processing_time_ms': (time.time() - action_start_time) * 1000,
                    'state_changed_correctly_binary': 1} # Health check implies state is correct/verified

        if random.random() < self.fault_probability:
            self.log_warning(f"Simulating internal fault during actuation action for {task_type_being_handled}.")
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
            effective_latency /= self.deception_factor if self.deception_factor > 0 else 1.0

        simulated_state_change_latency_ms = effective_latency * random.uniform(0.7, 1.3)
        actual_processing_delay_sec = max(0.001, simulated_state_change_latency_ms / 1000.0)
        if actual_processing_delay_sec > 0.001 : time.sleep(actual_processing_delay_sec)

        previous_state = self.current_state
        
        announced_reliability = self.announced_qos.get('command_reliability', 0.98)
        effective_reliability = announced_reliability
        if self.behavior_profile == 'deceptive': 
            effective_reliability *= self.deception_factor if self.deception_factor != 0 else 1.0
            
        action_succeeded = random.random() < effective_reliability
        state_changed_as_commanded = False

        if action_succeeded:
            if self.actuator_type == "hvac_control" and isinstance(command, dict):
                # For ADJUST_HVAC, command is expected to be like {"target_mode": "HEAT", "setpoint": 20.0}
                new_hvac_state = self.current_state.copy() if isinstance(self.current_state, dict) else {}
                if 'target_mode' in command: new_hvac_state['mode'] = command['target_mode'] 
                if 'setpoint' in command: new_hvac_state['setpoint'] = command['setpoint']
                if 'current_temp_report' in command : new_hvac_state['current_temp_report'] = command['current_temp_report']
                self.current_state = new_hvac_state
                state_changed_as_commanded = True 
            elif self.actuator_type == "light_switch" and command in ["ON", "OFF"]: # Example for light
                self.current_state = command
                state_changed_as_commanded = True
            else: # For other simpler actuators or generic "actuate"
                self.current_state = command # Assumes command is the new state
                state_changed_as_commanded = (self.current_state == command) # Or more complex check if needed
            
            self.log_debug(f"Actuated {self.actuator_type} (task: {task_type_being_handled}) with command '{str(command)[:50]}'. Prev state: '{str(previous_state)[:30]}', New state: '{str(self.current_state)[:30]}'")
        else:
            self.log_warning(f"Actuation command '{str(command)[:50]}' for {self.actuator_type} (task: {task_type_being_handled}) FAILED to execute reliably (simulated). State remains '{str(self.current_state)[:30]}'")
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
        command_for_action = details.get('command') # Command might be in details

        # Check if this device can handle the specific task_type
        if task_type == "actuate": 
            can_handle_task = True
            # Infer command if not provided for generic "actuate"
            if command_for_action is None:
                if self.actuator_type == "light_switch" or self.actuator_type == "smart_plug" or self.actuator_type == "switch":
                    command_for_action = "ON" if self.current_state == "OFF" else "OFF"
                elif self.actuator_type == "door_lock":
                    command_for_action = "UNLOCK" if self.current_state == "LOCKED" else "LOCKED"
                elif self.actuator_type == "hvac_control":
                    command_for_action = {'mode': details.get("target_mode", "AUTO"), 'setpoint': details.get("set_point", 22.0)}
                else: 
                    command_for_action = "TRIGGER"
        elif task_type == self.actuator_type: 
            can_handle_task = True
            # Infer command if not provided for specific actuator_type match
            if command_for_action is None:
                if self.actuator_type == "hvac_control":
                     command_for_action = {'mode': details.get("target_mode", "AUTO"), 'setpoint': details.get("set_point", 22.0)}
                     if 'current_temp' in details: command_for_action['current_temp_report'] = details['current_temp']
                # Add other default command inferences if needed
        elif task_type == "ADJUST_HVAC" and self.actuator_type == "hvac_control":
            can_handle_task = True
            # Command for ADJUST_HVAC should come from details (target_mode, set_point)
            if command_for_action is None:
                command_for_action = {
                    "target_mode": details.get("target_mode", "AUTO"), 
                    "setpoint": details.get("set_point", 22.0)
                }
                if 'current_temp' in details: command_for_action['current_temp_report'] = details['current_temp']
                if 'reason' in details: command_for_action['reason'] = details['reason']
        elif task_type == "PERIODIC_HEALTH_CHECK":
            can_handle_task = True
            command_for_action = "HEALTH_CHECK" 
        # Example for another specific task type
        # elif task_type == "TOGGLE_LIGHT" and self.actuator_type == "light_switch":
        #     can_handle_task = True
        #     if command_for_action is None: command_for_action = "ON" if self.current_state == "OFF" else "OFF"


        if not can_handle_task:
            self.log_warning(f"Rejected: {self.nameShort()} (type: {self.actuator_type}) cannot handle task type '{task_type}'. Expected 'actuate', '{self.actuator_type}', or a recognized specific task like ADJUST_HVAC for hvac_control.")
            overall_response_time_ms = (time.time() - request_start_time) * 1000
            measured_qos = {'task_success_binary': 0, 'response_time_ms': overall_response_time_ms, 'expected_load_for_task': load_requested}
            return {'success': False, 'reason': 'unsupported_task_type_by_specialization',
                    'measured_qos_for_requestor': measured_qos, 'request_start_time': request_start_time}
        
        action_result = self._perform_actuation_action(task_type, command_for_action, load_requested, details)
        
        overall_response_time_ms = (time.time() - request_start_time) * 1000
        measured_qos_for_trust_and_requestor = {
            'task_success_binary': 1 if action_result.get('success') else 0,
            'response_time_ms': overall_response_time_ms,
            'load_consumed': action_result.get('load_consumed', 0),
            'expected_load_for_task': load_requested, 
            'processing_time_ms': action_result.get('processing_time_ms', 0),
        }
        if task_type != "PERIODIC_HEALTH_CHECK":
             measured_qos_for_trust_and_requestor['state_changed_correctly_binary'] = action_result.get('state_changed_correctly_binary', 0)
        
        self.update_trust_from_qoe(from_device, task_type, measured_qos_for_trust_and_requestor, interaction_role="performer")

        if action_result.get('success'):
            self.log_info(f"EXECUTED '{task_type}' for {from_device.nameShort() if from_device else 'autonomous_task'}, cmd: '{str(command_for_action)[:50]}...', new_state: {str(action_result.get('new_state'))[:50]}")
            
            iot_app_reward = details.get('iot_app_reward', 0)
            if not from_device: 
                # Access current_job_dict safely if this method is part of a larger simulation context
                # For now, using a placeholder or a direct attribute from details if passed by generator
                iot_app_reward = details.get("base_reward_from_script", self.base_actuate_reward)


            if iot_app_reward > 0: self.receive_income(iot_app_reward, f"{task_type.capitalize()} Task Completion")
            
            return {'success': True, 'reason': f'{task_type}_successful', 
                    'new_state':action_result.get('new_state'),
                    'previous_state':action_result.get('previous_state'),
                    'measured_qos_for_requestor': measured_qos_for_trust_and_requestor, 
                    'request_start_time': request_start_time}
        else:
            self.log_warning(f"{task_type.capitalize()} execution FAILED for {from_device.nameShort() if from_device else 'autonomous_task'} with cmd '{str(command_for_action)[:50]}'. Reason: {action_result.get('reason','unknown')}")
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

