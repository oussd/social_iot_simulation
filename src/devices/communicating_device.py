from .device import Device, QoELevel
import random
import time

class CommunicatingDevice(Device):
    def __init__(self, device_id, name, max_load=100, protocol="WiFi"):
        super().__init__(device_id, name, max_load)
        self.protocol = protocol
        self.connected_devices = [] # List of device objects it's "connected" to
        self.base_transmit_reward = 8
        self.announced_qos['transmission_latency_ms'] = random.uniform(10,30) # Network latency component
        self.announced_qos['message_delivery_rate'] = random.uniform(0.95,1.0) # Chance message gets through (simplified)
        self.qoe_thresholds['transmission_latency_ms'] = {'sigma': 15.0, 'delta': 10.0}
        self.qoe_thresholds['message_delivery_rate'] = self.qoe_thresholds['task_success_rate'] # Reuse success rate thresholds

    def connect_device(self, device_to_connect):
        if device_to_connect not in self.connected_devices:
            self.connected_devices.append(device_to_connect)
            self.log_event(f"Connected to {device_to_connect.name}")
            return True
        return True # Already connected

    def _perform_transmit_action(self, message, target_device, expected_load_for_task):
        action_start_time = time.time()
        action_load_cost = int(expected_load_for_task * random.uniform(0.8, self.announced_qos.get('load_efficiency', 1.2)))

        if target_device not in self.connected_devices:
            processing_time_ms = (time.time() - action_start_time) * 1000
            return {'success': False, 'reason': 'target_not_connected', 'load_consumed': 0, 'processing_time_ms': processing_time_ms}

        if not self.consume_load(action_load_cost):
            processing_time_ms = (time.time() - action_start_time) * 1000
            return {'success': False, 'reason': 'overload_at_action', 'load_consumed': 0, 'processing_time_ms': processing_time_ms}

        # Simulate transmission latency and success
        time.sleep(self.announced_qos['transmission_latency_ms'] / 1000 * random.uniform(0.7, 1.5))
        delivered_successfully = random.random() < self.announced_qos['message_delivery_rate']
        
        processing_time_ms = (time.time() - action_start_time) * 1000 # Includes simulated latency

        if delivered_successfully:
            self.log_event(f"Transmitted '{message}' to {target_device.name} via {self.protocol} in {processing_time_ms:.0f}ms, Load: {action_load_cost}")
            # In a real scenario, target_device would process the message. Here we just log.
            if hasattr(target_device, 'log_event'): # Check if target is a simulation device
                 target_device.log_event(f"Received '{message}' from {self.name}")
        else:
            self.log_event(f"Transmission of '{message}' to {target_device.name} FAILED (simulated delivery failure).")

        return {
            'success': delivered_successfully, 'load_consumed': action_load_cost,
            'processing_time_ms': processing_time_ms, 'message_delivered_binary': 1 if delivered_successfully else 0
        }

    def handle_request(self, from_device, task_type, load_requested=10, details=None):
        details = details or {}
        base_acceptance = super().handle_request(from_device, task_type, load_requested, details)
        request_start_time = base_acceptance.get('request_start_time', time.time())

        if not base_acceptance['success']:
            return base_acceptance

        if task_type != 'transmit':
            self.log_event(f"Rejected: CommDevice cannot handle task type '{task_type}'.")
            response_time_ms = (time.time() - request_start_time) * 1000
            measured_qos = {'task_success_binary': 0, 'response_time_ms': response_time_ms}
            self.update_trust_from_qoe(from_device, task_type, measured_qos, interaction_role="performer")
            return {'success': False, 'reason': 'unsupported_task_type_by_specialization', 'measured_qos_for_requestor': measured_qos, 'request_start_time': request_start_time}

        message = details.get('message', "default_comm_message")
        target_comm_device = details.get('target_comm_device') # Expecting a device object

        if not target_comm_device or not hasattr(target_comm_device, 'device_id'): # Basic check
            self.log_event(f"Invalid or no target_comm_device provided for transmit.")
            response_time_ms = (time.time() - request_start_time) * 1000
            measured_qos = {'task_success_binary': 0, 'response_time_ms': response_time_ms, 'reason_code': 'invalid_target'}
            self.update_trust_from_qoe(from_device, task_type, measured_qos, interaction_role="performer")
            return {'success': False, 'reason': 'invalid_target_device', 'measured_qos_for_requestor': measured_qos, 'request_start_time': request_start_time}

        self.connect_device(target_comm_device) # Ensure connection
        action_result = self._perform_transmit_action(message, target_comm_device, load_requested)
        
        overall_response_time_ms = (time.time() - request_start_time) * 1000
        
        measured_qos_for_trust_and_requestor = {
            'task_success_binary': 1 if action_result['success'] else 0, # Based on delivery
            'response_time_ms': overall_response_time_ms,
            'load_consumed': action_result.get('load_consumed', 0),
            'expected_load_for_task': load_requested,
            'processing_time_ms': action_result.get('processing_time_ms', 0),
            'message_delivered_binary': action_result.get('message_delivered_binary', 0)
        }
        
        self.update_trust_from_qoe(from_device, task_type, measured_qos_for_trust_and_requestor, interaction_role="performer")

        if action_result['success']:
            self.log_event(f"EXECUTED 'transmit' for {from_device.name if from_device else 'autonomous task'} to {target_comm_device.name}")
            iot_app_reward = details.get('iot_app_reward', self.base_transmit_reward if not from_device else 0)
            if iot_app_reward > 0:
                self.receive_income(iot_app_reward, "Transmission Task Completion")
            
            return {'success': True, 'reason': 'transmit_successful',
                    'measured_qos_for_requestor': measured_qos_for_trust_and_requestor, 'request_start_time': request_start_time}
        else:
            self.log_event(f"Transmission execution FAILED for {from_device.name if from_device else 'autonomous task'} to {target_comm_device.name} due to {action_result.get('reason','unknown')}")
            return {'success': False, 'reason': f"transmit_execution_failed: {action_result.get('reason','unknown')}",
                    'measured_qos_for_requestor': measured_qos_for_trust_and_requestor, 'request_start_time': request_start_time}

    # report_status is inherited