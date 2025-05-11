from .device import Device, QoELevel
import random
import time

class ActuatingDevice(Device):
    def __init__(self, device_id, name, max_load=100, actuator_type="switch"):
        super().__init__(device_id, name, max_load)
        self.actuator_type = actuator_type
        self.current_state = "OFF" # Default state
        self.base_actuate_reward = 12
        self.announced_qos['command_acceptance_latency_ms'] = random.uniform(5, 20) # Time to process command before actuation
        self.qoe_thresholds['command_acceptance_latency_ms'] = {'sigma': 10.0, 'delta': 5.0}


    def _perform_actuation_action(self, command, expected_load_for_task):
        action_start_time = time.time()
        action_load_cost = int(expected_load_for_task * random.uniform(0.8, self.announced_qos.get('load_efficiency', 1.2)))

        if not self.consume_load(action_load_cost):
            processing_time_ms = (time.time() - action_start_time) * 1000
            return {'success': False, 'reason': 'overload_at_action', 'load_consumed': 0, 'processing_time_ms': processing_time_ms}

        # Simulate command processing latency
        time.sleep(self.announced_qos['command_acceptance_latency_ms'] / 1000 * random.uniform(0.8,1.2) )
        
        previous_state = self.current_state
        self.current_state = command
        
        # Simulate physical actuation time
        time.sleep(random.uniform(0.02, 0.06))
        actuation_duration_ms = (time.time() - action_start_time) * 1000 # This is total processing + actuation

        self.log_event(f"Actuated {self.actuator_type} from {previous_state} to {command} in {actuation_duration_ms:.0f}ms, Load: {action_load_cost}")
        return {
            'success': True, 'new_state': self.current_state, 'load_consumed': action_load_cost,
            'processing_time_ms': actuation_duration_ms # Represents combined processing and physical actuation time
        }

    def handle_request(self, from_device, task_type, load_requested=10, details=None):
        details = details or {}
        base_acceptance = super().handle_request(from_device, task_type, load_requested, details)
        request_start_time = base_acceptance.get('request_start_time', time.time())

        if not base_acceptance['success']:
            return base_acceptance

        if task_type != 'actuate':
            self.log_event(f"Rejected: ActuatingDevice cannot handle task type '{task_type}'.")
            response_time_ms = (time.time() - request_start_time) * 1000
            measured_qos = {'task_success_binary': 0, 'response_time_ms': response_time_ms}
            self.update_trust_from_qoe(from_device, task_type, measured_qos, interaction_role="performer")
            return {'success': False, 'reason': 'unsupported_task_type_by_specialization', 'measured_qos_for_requestor': measured_qos, 'request_start_time': request_start_time}

        command = details.get('command', "ON" if self.current_state == "OFF" else "OFF") # Simple toggle if no command
        action_result = self._perform_actuation_action(command, load_requested)
        
        overall_response_time_ms = (time.time() - request_start_time) * 1000
        
        measured_qos_for_trust_and_requestor = {
            'task_success_binary': 1 if action_result['success'] else 0,
            'response_time_ms': overall_response_time_ms,
            'load_consumed': action_result.get('load_consumed', 0),
            'expected_load_for_task': load_requested,
            'processing_time_ms': action_result.get('processing_time_ms', 0),
            # Could add 'state_changed_correctly_binary' if verifiable
        }
        
        self.update_trust_from_qoe(from_device, task_type, measured_qos_for_trust_and_requestor, interaction_role="performer")

        if action_result['success']:
            self.log_event(f"EXECUTED 'actuate' for {from_device.name if from_device else 'autonomous task'} to {action_result['new_state']}")
            iot_app_reward = details.get('iot_app_reward', self.base_actuate_reward if not from_device else 0)
            if iot_app_reward > 0:
                self.receive_income(iot_app_reward, "Actuation Task Completion")
            
            return {'success': True, 'reason': 'actuation_successful', 'new_state': action_result['new_state'],
                    'measured_qos_for_requestor': measured_qos_for_trust_and_requestor, 'request_start_time': request_start_time}
        else:
            self.log_event(f"Actuation execution FAILED for {from_device.name if from_device else 'autonomous task'} due to {action_result.get('reason','unknown')}")
            # Backup logic...
            return {'success': False, 'reason': f"actuation_execution_failed: {action_result.get('reason','unknown')}",
                    'measured_qos_for_requestor': measured_qos_for_trust_and_requestor, 'request_start_time': request_start_time}

    # report_status is inherited from Device