from .device import Device, QoELevel
import random
import time

class SensingDevice(Device):
    def __init__(self, device_id, name, max_load=100, sensor_type="temperature"):
        super().__init__(device_id, name, max_load)
        self.sensor_type = sensor_type
        self.base_sense_reward = 10
        self.announced_qos['data_accuracy'] = random.uniform(0.9, 0.98) # Example specific QoS
        self.qoe_thresholds['data_accuracy'] = {'sigma': 0.05, 'delta': 0.03}

    def _perform_sense_action(self, expected_load_for_task):
        """Internal method to do the sensing and measure its direct QoS."""
        action_start_time = time.time()
        action_load_cost = int(expected_load_for_task * random.uniform(0.8, self.announced_qos.get('load_efficiency', 1.2))) # Simulate load variation
        
        if not self.consume_load(action_load_cost): # Try to consume load
            processing_time_ms = (time.time() - action_start_time) * 1000
            return {'success': False, 'reason': 'overload_at_action', 'load_consumed': 0, 'processing_time_ms': processing_time_ms}

        # Simulate sensing
        time.sleep(random.uniform(0.01, 0.05)) # Simulate processing time
        value = random.uniform(20.0, 30.0) if self.sensor_type == "temperature" else random.uniform(0.0, 100.0)
        
        # Simulate data accuracy
        actual_accuracy = self.announced_qos['data_accuracy'] * random.uniform(0.9, 1.05) # +/- 10% of its own announced accuracy
        actual_accuracy = min(1.0, max(0.0, actual_accuracy))

        processing_time_ms = (time.time() - action_start_time) * 1000
        self.log_event(f"Sensed {self.sensor_type}: {value:.2f} (Acc: {actual_accuracy:.2f}) in {processing_time_ms:.0f}ms, Load: {action_load_cost}")
        return {
            'success': True, 'value': value, 'load_consumed': action_load_cost,
            'processing_time_ms': processing_time_ms, 'data_accuracy_measured': actual_accuracy
        }

    def handle_request(self, from_device, task_type, load_requested=10, details=None):
        details = details or {}
        # Initial checks by base class (avoid, controller limits, base policy, initial load negotiation)
        base_acceptance = super().handle_request(from_device, task_type, load_requested, details)
        request_start_time = base_acceptance.get('request_start_time', time.time()) # Get precise start time

        if not base_acceptance['success']:
            # Base class already determined failure and reason.
            # The simulation loop will use base_acceptance['measured_qos_for_requestor']
            # for from_device to update its trust in this (self) device.
            return base_acceptance # Propagate the detailed failure dict

        if task_type != 'sense':
            self.log_event(f"Rejected: SensingDevice cannot handle task type '{task_type}'.")
            response_time_ms = (time.time() - request_start_time) * 1000
            measured_qos = {'task_success_binary': 0, 'response_time_ms': response_time_ms}
            self.update_trust_from_qoe(from_device, task_type, measured_qos, interaction_role="performer")
            return {'success': False, 'reason': 'unsupported_task_type_by_specialization', 'measured_qos_for_requestor': measured_qos, 'request_start_time': request_start_time}

        # Perform the actual sensing action
        action_result = self._perform_sense_action(load_requested)
        
        overall_response_time_ms = (time.time() - request_start_time) * 1000
        
        # Compile QoS metrics for trust update and for the requestor
        measured_qos_for_trust_and_requestor = {
            'task_success_binary': 1 if action_result['success'] else 0,
            'response_time_ms': overall_response_time_ms,
            'load_consumed': action_result.get('load_consumed', 0),
            'expected_load_for_task': load_requested, # For load efficiency calculation
            'processing_time_ms': action_result.get('processing_time_ms', 0),
            'data_accuracy_measured': action_result.get('data_accuracy_measured')
        }
        
        # This device (performer) updates its own general trust based on its performance
        self.update_trust_from_qoe(from_device, task_type, measured_qos_for_trust_and_requestor, interaction_role="performer")

        if action_result['success']:
            self.log_event(f"EXECUTED 'sense' for {from_device.name if from_device else 'autonomous task'}, val: {action_result['value']:.2f}")
            # Monetary reward
            iot_app_reward = details.get('iot_app_reward', self.base_sense_reward if not from_device else 0)
            if iot_app_reward > 0:
                self.receive_income(iot_app_reward, "Sensing Task Completion")
            
            return {'success': True, 'reason': 'sense_successful', 'value':action_result['value'],
                    'measured_qos_for_requestor': measured_qos_for_trust_and_requestor, 'request_start_time': request_start_time}
        else:
            self.log_event(f"Sensing execution FAILED for {from_device.name if from_device else 'autonomous task'} due to {action_result.get('reason','unknown')}")
            # Backup logic could be attempted here. If backup is used, its QoS also matters.
            # For now, just return failure.
            # The trust update for this failure is already done via update_trust_from_qoe.
            return {'success': False, 'reason': f"sense_execution_failed: {action_result.get('reason','unknown')}",
                    'measured_qos_for_requestor': measured_qos_for_trust_and_requestor, 'request_start_time': request_start_time}

    # report_status is inherited from Device