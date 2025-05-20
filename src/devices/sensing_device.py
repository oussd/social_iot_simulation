import random
import time
from typing import List, Dict, Any, Optional
from .device import Device, QoELevel # Base class from which methods are inherited

class SensingDevice(Device):
    def __init__(self, device_id: str, name: str, max_load: int = 100,
                 sensor_type: str = "temperature",
                 framework_variant: str = "full_siot",
                 logger_instance=None,
                 current_minute_provider=None):
        super().__init__(device_id, name, max_load, framework_variant,
                         capabilities=["sense", sensor_type], # Add sensor_type to capabilities
                         logger_instance=logger_instance,
                         current_minute_provider=current_minute_provider)
        self.sensor_type = sensor_type
        self.base_sense_reward = 10 # Example base reward for completing a sense task

        # Sensor-specific QoS can be added here if they differ from base Device
        if 'data_accuracy' not in self.announced_qos: # Example specific QoS for sensors
             self.announced_qos['data_accuracy'] = random.uniform(0.9, 0.98) # e.g. 90-98% accurate
             self.qoe_thresholds['data_accuracy'] = {'sigma': 0.05, 'delta': 0.03} # Thresholds for accuracy deviation

    # Worker management methods like add_worker and remove_worker are now
    # inherited from the base Device class. The restriction preventing
    # SensingDevice from using them has been removed from the base class.
    # Thus, SensingDevice instances can now, in principle, add and manage workers.

    def _perform_sense_action(self, expected_load_for_task: int) -> Dict[str, Any]:
        """
        Simulates the sensing action and returns detailed QoS metrics.
        expected_load_for_task: The load anticipated for this specific sense operation.
        """
        action_start_time = time.time()

        # Simulate load variation based on device's announced load_efficiency
        load_factor = self.announced_qos.get('load_efficiency', 1.0) * random.uniform(0.9, 1.1) # Actual use vs announced
        action_load_cost = int(expected_load_for_task * load_factor)
        action_load_cost = max(1, action_load_cost) # Ensure at least 1 unit of load

        if not self.consume_load(action_load_cost): # Try to consume load for the action
            return {'success': False, 'reason': 'overload_at_action', 'load_consumed': 0,
                    'processing_time_ms': (time.time() - action_start_time) * 1000,
                    'data_accuracy_measured': 0.0} # Failed, so accuracy is 0

        # Simulate processing time based on announced response time (which includes processing)
        # This is the device's internal processing/sensing time for this specific action.
        simulated_action_processing_ms = self.announced_qos.get('response_time_ms', 50) * random.uniform(0.7, 1.3)
        time.sleep(simulated_action_processing_ms / 1000.0)

        value: Any = None # To store the sensed value
        # Simulate different sensor readings based on sensor_type
        if self.sensor_type == "temperature": value = random.uniform(18.0, 28.0) # Celsius
        elif self.sensor_type == "occupancy": value = random.choice([0, 1, random.randint(2,10)]) # 0=no, 1=yes, >1 count
        elif self.sensor_type == "light_level": value = random.uniform(50, 1000) # lux
        elif self.sensor_type == "co2": value = random.uniform(400, 1200) # ppm
        elif self.sensor_type == "door_contact" or self.sensor_type == "window_contact": value = random.choice(["OPEN", "CLOSED"])
        elif self.sensor_type == "card_swipe": # For CardReaderSensor if it uses this
            value = f"card_data_{random.randint(1000,9999)}_user{random.randint(1,10)}"
        elif self.sensor_type == "power_usage": # For PowerMeterSensor if it uses this
            current_power_draw = getattr(self, 'current_power_draw_kw', random.uniform(0.5,5.0)) # Check if attr exists
            current_power_draw += random.uniform(-0.2, 0.2)
            value = max(0.1, current_power_draw)
            setattr(self, 'current_power_draw_kw', value) # Update if it's a stateful sensor
        else: value = random.random() # Generic value for other types

        # Simulate data accuracy
        actual_accuracy = self.announced_qos.get('data_accuracy',0.95) * random.uniform(0.85, 1.03) # How accurate the reading is
        actual_accuracy = min(1.0, max(0.0, actual_accuracy)) # Clamp between 0 and 1

        # Total time for this action (excluding potential queueing time before it started)
        action_duration_ms = (time.time() - action_start_time) * 1000

        # Prepare value string for logging to avoid formatting errors with non-float types
        val_log_str = f"{value:.2f}" if isinstance(value, float) else str(value)
        self.log_event(f"Sensed {self.sensor_type}: {val_log_str} (Acc: {actual_accuracy:.2f}) in {action_duration_ms:.0f}ms, Load Consumed: {action_load_cost}", level='debug')
        return {
            'success': True,
            'value': value,
            'load_consumed': action_load_cost,
            'processing_time_ms': action_duration_ms, # This is the device's internal processing time for the action
            'data_accuracy_measured': actual_accuracy
        }

    def handle_request(self, from_device: Optional[Device], task_type: str,
                       load_requested: int = 10, details: Optional[Dict] = None) -> Dict[str, Any]:
        details = details if details is not None else {}
        # Initial common checks by base class (avoid, controller limits, base policy, negotiation/load)
        base_acceptance_outcome = super().handle_request(from_device, task_type, load_requested, details)
        request_start_time = base_acceptance_outcome.get('request_start_time', time.time()) # Get precise start time from base

        if not base_acceptance_outcome.get('success'):
            return base_acceptance_outcome

        # This specific device only handles 'sense' or its specific sensor_type as a task_type
        if task_type != 'sense' and task_type != self.sensor_type:
            self.log_event(f"Rejected: {self.nameShort()} cannot handle task type '{task_type}'. Expected 'sense' or '{self.sensor_type}'.", level='warning')
            overall_response_time_ms = (time.time() - request_start_time) * 1000
            measured_qos = {'task_success_binary': 0, 'response_time_ms': overall_response_time_ms, 'expected_load_for_task': load_requested}
            self.update_trust_from_qoe(from_device, task_type, measured_qos, interaction_role="performer")
            return {'success': False, 'reason': 'unsupported_task_type_by_specialization',
                    'measured_qos_for_requestor': measured_qos, 'request_start_time': request_start_time}

        # Perform the actual sensing action
        action_result = self._perform_sense_action(load_requested) # Pass the load this task is expected to take

        overall_response_time_ms = (time.time() - request_start_time) * 1000

        # Compile QoS metrics for trust update (self-assessment) and for the requestor
        measured_qos_for_trust_and_requestor = {
            'task_success_binary': 1 if action_result.get('success') else 0,
            'response_time_ms': overall_response_time_ms, # Total time from request to response
            'load_consumed': action_result.get('load_consumed', 0),
            'expected_load_for_task': load_requested, # For load efficiency calculation
            'processing_time_ms': action_result.get('processing_time_ms', 0), # Device's internal action time
            'data_accuracy_measured': action_result.get('data_accuracy_measured')
        }

        self.update_trust_from_qoe(from_device, task_type, measured_qos_for_trust_and_requestor, interaction_role="performer")

        if action_result.get('success'):
            val_report_str = f"{action_result.get('value'):.2f}" if isinstance(action_result.get('value'), float) else str(action_result.get('value'))
            self.log_event(f"EXECUTED '{task_type}' for {from_device.nameShort() if from_device else 'autonomous_task'}, val: {val_report_str}")
            iot_app_reward = details.get('iot_app_reward', self.base_sense_reward if not from_device else 0)
            if iot_app_reward > 0: self.receive_income(iot_app_reward, f"{task_type.capitalize()} Task Completion")

            return {'success': True, 'reason': f'{task_type}_successful', 'value':action_result.get('value'),
                    'measured_qos_for_requestor': measured_qos_for_trust_and_requestor, 'request_start_time': request_start_time}
        else: # Action failed
            self.log_event(f"{task_type.capitalize()} execution FAILED for {from_device.nameShort() if from_device else 'autonomous_task'} due to {action_result.get('reason','unknown')}", level='warning')
            # Backup logic (framework-aware)
            if self.framework_variant in ["social_basic", "full_siot"]:
                 for rel in self.relationships.get('back_me', []):
                     backup_device = rel.get('device')
                     if not backup_device: continue

                     if backup_device == from_device or \
                        (details.get('is_backup_attempt') and details.get('original_backup_initiator') == backup_device.device_id):
                         continue

                     self.log_event(f"Attempting backup {task_type} with {backup_device.nameShort()}")
                     backup_details = details.copy()
                     backup_details['is_backup_attempt'] = True
                     backup_details['original_backup_initiator'] = self.device_id

                     backup_outcome = backup_device.handle_request(self, task_type, load_requested, backup_details)
                     self.update_trust_from_qoe(backup_device, task_type, backup_outcome.get('measured_qos_for_requestor',{}), "requester")

                     if backup_outcome.get('success'):
                         self.log_event(f"Backup {task_type} by {backup_device.nameShort()} SUCCEEDED.")
                         if self.sim_metrics_ref and 'back_me_invocations_successful' in self.sim_metrics_ref:
                             self.sim_metrics_ref['back_me_invocations_successful'] +=1
                         return {**backup_outcome, 'backed_up_by': backup_device.device_id}
                     else:
                         if self.sim_metrics_ref and 'back_me_invocations_failed' in self.sim_metrics_ref:
                             self.sim_metrics_ref['back_me_invocations_failed'] +=1

            return {'success': False, 'reason': f"{task_type}_execution_failed_no_successful_backup: {action_result.get('reason','unknown')}",
                    'measured_qos_for_requestor': measured_qos_for_trust_and_requestor, 'request_start_time': request_start_time}

    # report_status is inherited from Device
