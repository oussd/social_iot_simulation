import random
import time
from typing import List, Dict, Any, Optional
from .device import Device, QoELevel # Base class from which methods are inherited

class ActuatingDevice(Device):
    def __init__(self, device_id: str, name: str, max_load: int = 100,
                 actuator_type: str = "switch",
                 framework_variant: str = "full_siot",
                 logger_instance=None,
                 current_minute_provider=None):
        super().__init__(device_id, name, max_load, framework_variant,
                         capabilities=["actuate", actuator_type], # Core capabilities
                         logger_instance=logger_instance,
                         current_minute_provider=current_minute_provider)
        self.actuator_type = actuator_type
        # Define initial state based on actuator type for more realism
        if self.actuator_type in ["light_switch", "smart_plug", "alarm_siren"]:
            self.current_state: Any = "OFF"
        elif self.actuator_type == "door_lock":
            self.current_state: Any = "LOCKED"
        elif self.actuator_type == "hvac_control":
            self.current_state: Any = {'mode': "OFF", 'setpoint': 22} # Example complex state
        else:
            self.current_state: Any = "IDLE" # Generic default

        self.base_actuate_reward = 12 # Base reward for completing an actuation task

        # QoS parameters specific to actuation
        if 'state_change_latency_ms' not in self.announced_qos:
             self.announced_qos['state_change_latency_ms'] = random.uniform(5, 50) # Time to change state
             self.qoe_thresholds['state_change_latency_ms'] = {'sigma': 20.0, 'delta': 10.0}
        if 'command_reliability' not in self.announced_qos: # How reliably commands are executed
            self.announced_qos['command_reliability'] = random.uniform(0.95, 0.99)
            # Use task_success_rate thresholds if specific ones aren't defined for command_reliability
            self.qoe_thresholds['command_reliability'] = self.qoe_thresholds.get('task_success_rate', {'sigma': 0.15, 'delta': 0.10})

    # Worker management methods like add_worker and remove_worker are inherited
    # from the base Device class. ActuatingDevice instances can use these methods
    # to act as controllers because the restriction in Device.add_worker()
    # (if self.__class__.__name__ == "SensingDevice") does not apply to ActuatingDevice.

    def _perform_actuation_action(self, command: Any, expected_load_for_task: int) -> Dict[str, Any]:
        """
        Simulates the actuation action, changes state, and returns QoS metrics.
        expected_load_for_task: The load anticipated for this specific actuation.
        """
        action_start_time = time.time()
        # Simulate load variation based on device's announced load_efficiency
        load_factor = self.announced_qos.get('load_efficiency', 1.0) * random.uniform(0.9, 1.1)
        action_load_cost = int(expected_load_for_task * load_factor)
        action_load_cost = max(1, action_load_cost) # Ensure at least 1 unit of load

        if not self.consume_load(action_load_cost): # Try to consume load for the action
            return {'success': False, 'reason': 'overload_at_action', 'load_consumed': 0,
                    'processing_time_ms': (time.time() - action_start_time) * 1000,
                    'state_changed_correctly_binary': 0} # Failed, so state change is 0

        # Simulate time taken for the state to change
        simulated_state_change_latency_ms = self.announced_qos.get('state_change_latency_ms', 30) * random.uniform(0.7, 1.3)
        time.sleep(simulated_state_change_latency_ms / 1000.0)

        previous_state = self.current_state
        action_succeeded = random.random() < self.announced_qos.get('command_reliability', 0.98)
        state_changed_as_commanded = False

        if action_succeeded:
            # More nuanced state change for complex actuators like HVAC
            if self.actuator_type == "hvac_control" and isinstance(command, dict):
                new_hvac_state = self.current_state.copy() if isinstance(self.current_state, dict) else {}
                new_hvac_state.update(command) # Update mode, setpoint etc. from command dict
                self.current_state = new_hvac_state
                state_changed_as_commanded = True # Assume complex command is applied if action_succeeded
            else: # Simple actuators
                self.current_state = command
                state_changed_as_commanded = (self.current_state == command)

            self.log_event(f"Actuated {self.actuator_type} from '{str(previous_state)[:30]}' to '{str(self.current_state)[:30]}'", level='debug')
        else:
            self.log_event(f"Actuation command '{str(command)[:50]}' for {self.actuator_type} FAILED to execute reliably (simulated). State remains '{str(self.current_state)[:30]}'", level='warning')
            state_changed_as_commanded = False # Explicitly false if action failed

        action_duration_ms = (time.time() - action_start_time) * 1000

        return {
            'success': action_succeeded,
            'new_state': self.current_state, # Current state after attempt
            'previous_state': previous_state,
            'command_received': command,
            'load_consumed': action_load_cost,
            'processing_time_ms': action_duration_ms, # Device's internal action time
            'state_changed_correctly_binary': 1 if state_changed_as_commanded else 0
        }

    def handle_request(self, from_device: Optional[Device], task_type: str,
                       load_requested: int = 10, details: Optional[Dict] = None) -> Dict[str, Any]:
        details = details if details is not None else {}
        # Call base class handler for common checks (avoidance, policy, load negotiation)
        base_acceptance_outcome = super().handle_request(from_device, task_type, load_requested, details)
        request_start_time = base_acceptance_outcome.get('request_start_time', time.time())

        if not base_acceptance_outcome.get('success'):
            return base_acceptance_outcome # Base class already handled rejection and QoS

        # This specific device only handles 'actuate' or its specific actuator_type as a task_type
        if task_type != 'actuate' and task_type != self.actuator_type:
            self.log_event(f"Rejected: {self.nameShort()} cannot handle task type '{task_type}'. Expected 'actuate' or '{self.actuator_type}'.", level='warning')
            overall_response_time_ms = (time.time() - request_start_time) * 1000
            measured_qos = {'task_success_binary': 0, 'response_time_ms': overall_response_time_ms, 'expected_load_for_task': load_requested}
            # This device (performer) failed to meet expectation of handling this task.
            self.update_trust_from_qoe(from_device, task_type, measured_qos, interaction_role="performer")
            return {'success': False, 'reason': 'unsupported_task_type_by_specialization',
                    'measured_qos_for_requestor': measured_qos, 'request_start_time': request_start_time}

        command = details.get('command')
        if command is None: # If no specific command, try a sensible default or toggle
            if self.actuator_type == "light_switch" or self.actuator_type == "smart_plug":
                command = "OFF" if self.current_state == "ON" else "ON"
            elif self.actuator_type == "door_lock":
                command = "UNLOCK" if self.current_state == "LOCKED" else "LOCKED"
            elif self.actuator_type == "hvac_control": # Needs more specific command
                 # Default to AUTO if no command for HVAC, or maintain current if complex
                command = {'mode': "AUTO"} if not isinstance(self.current_state, dict) or self.current_state.get('mode') == "OFF" else self.current_state
            else:
                command = "TRIGGER" # Generic command for other types

        # Perform the actual actuation
        action_result = self._perform_actuation_action(command, load_requested) # Pass the load this task is expected to take

        overall_response_time_ms = (time.time() - request_start_time) * 1000

        # Compile QoS metrics for trust update (self-assessment) and for the requestor
        measured_qos_for_trust_and_requestor = {
            'task_success_binary': 1 if action_result.get('success') else 0,
            'response_time_ms': overall_response_time_ms, # Total time from request to response
            'load_consumed': action_result.get('load_consumed', 0),
            'expected_load_for_task': load_requested, # For load efficiency calculation
            'processing_time_ms': action_result.get('processing_time_ms', 0), # Device's internal action time
            'state_changed_correctly_binary': action_result.get('state_changed_correctly_binary', 0)
            # Any other QoS params from action_result can be added here
        }

        # This device (performer) updates its own general trust based on its performance for this task
        self.update_trust_from_qoe(from_device, task_type, measured_qos_for_trust_and_requestor, interaction_role="performer")

        if action_result.get('success'):
            self.log_event(f"EXECUTED '{task_type}' for {from_device.nameShort() if from_device else 'autonomous_task'}, cmd: '{str(command)[:30]}...', new_state: {str(action_result.get('new_state'))[:30]}")
            # Monetary reward
            iot_app_reward = details.get('iot_app_reward', self.base_actuate_reward if not from_device else 0)
            if iot_app_reward > 0: self.receive_income(iot_app_reward, f"{task_type.capitalize()} Task Completion")

            return {'success': True, 'reason': f'{task_type}_successful', 'new_state':action_result.get('new_state'),
                    'measured_qos_for_requestor': measured_qos_for_trust_and_requestor, 'request_start_time': request_start_time}
        else: # Action failed
            self.log_event(f"{task_type.capitalize()} execution FAILED for {from_device.nameShort() if from_device else 'autonomous_task'} with cmd '{str(command)[:30]}'. Reason: {action_result.get('reason','unknown')}", level='warning')
            # Backup logic (framework-aware)
            if self.framework_variant in ["social_basic", "full_siot"]:
                 for rel in self.relationships.get('back_me', []): # Check 'back_me' relationships
                     backup_device = rel.get('device')
                     if not backup_device: continue

                     # Avoid circular backup or backup to original requester if it was a direct request
                     if backup_device == from_device or \
                        (details.get('is_backup_attempt') and details.get('original_backup_initiator') == backup_device.device_id):
                         continue

                     self.log_event(f"Attempting backup {task_type} with {backup_device.nameShort()}")
                     backup_details = details.copy()
                     backup_details['is_backup_attempt'] = True
                     backup_details['original_backup_initiator'] = self.device_id # Who started this backup chain segment

                     # This device (self) is now a requester to the backup_device
                     backup_outcome = backup_device.handle_request(self, task_type, load_requested, backup_details)

                     # This device (self) updates its trust in the backup_device based on its performance
                     self.update_trust_from_qoe(backup_device, task_type, backup_outcome.get('measured_qos_for_requestor',{}), "requester")

                     if backup_outcome.get('success'):
                         self.log_event(f"Backup {task_type} by {backup_device.nameShort()} SUCCEEDED.")
                         if self.sim_metrics_ref and 'back_me_invocations_successful' in self.sim_metrics_ref:
                             self.sim_metrics_ref['back_me_invocations_successful'] +=1
                         return {**backup_outcome, 'backed_up_by': backup_device.device_id} # Return the successful outcome from backup
                     else: # Backup also failed
                         if self.sim_metrics_ref and 'back_me_invocations_failed' in self.sim_metrics_ref:
                             self.sim_metrics_ref['back_me_invocations_failed'] +=1

            # If no backup or backup failed, return the original failure
            return {'success': False, 'reason': f"{task_type}_execution_failed_no_successful_backup: {action_result.get('reason','unknown')}",
                    'measured_qos_for_requestor': measured_qos_for_trust_and_requestor, 'request_start_time': request_start_time}

    # report_status is inherited from Device
