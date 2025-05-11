from .device import Device, QoELevel
from .sensing_device import SensingDevice
from .actuating_device import ActuatingDevice
from .communicating_device import CommunicatingDevice
import random
import time

class CompositeDevice(Device):
    def __init__(self, device_id, name, max_load=150, capabilities=None):
        super().__init__(device_id, name, max_load)
        self.capabilities = capabilities or ["sense", "actuate", "transmit", "coordinate"] # Added coordinate
        self.sub_devices = [] # Devices integral to the composite device's function
        self.base_composite_task_reward_multiplier = 1.3 # Earns a bit more for coordination
        self.worker_payment_ratio = 0.7 # Pays 70% of what it would earn for sub-task to worker

        # Announced QoS specific to composite device's coordination role
        self.announced_qos['coordination_overhead_ms'] = random.uniform(20,50) # Extra time for coordination
        self.qoe_thresholds['coordination_overhead_ms'] = {'sigma': 20.0, 'delta':10.0} # Thresholds for this overhead

    def add_sub_device(self, device): # Integral part, not a 'worker'
        if device not in self.sub_devices:
            self.sub_devices.append(device)
            self.log_event(f"Added sub-device {device.name}")

    def add_worker(self, worker_device, constraints=None): # For 'work-for-me' where Composite is controller
        if 'controller_for' not in self.relationships: self.relationships['controller_for'] = []
        if not any(r['device'] == worker_device for r in self.relationships['controller_for']):
            self.relationships['controller_for'].append({
                'device': worker_device, 'constraints': constraints or {}, 
                'start_time': time.time(), 'status': 'active'
            })
            # Worker device should also acknowledge this composite as its controller
            worker_device.add_controller(self, constraints) 
            self.log_event(f"Added {worker_device.name} as worker (I am controller for them)")
            return True
        return False

    def remove_worker(self, worker_device):
        if 'controller_for' in self.relationships:
            initial_len = len(self.relationships['controller_for'])
            self.relationships['controller_for'] = [r for r in self.relationships['controller_for'] if r['device'] != worker_device]
            if len(self.relationships['controller_for']) < initial_len:
                worker_device.remove_controller(self) # Worker removes this composite as its controller
                self.log_event(f"Removed {worker_device.name} as a worker")

    def _delegate_to_worker_or_sub(self, task_type, original_requestor_device, load_for_sub_task, details_for_sub_task):
        """ 
        Tries to delegate a task to an active worker or an internal sub-device.
        Returns the outcome dictionary from the delegate's handle_request, 
        augmented with coordination overhead, or None if no suitable delegate handles the task.
        """
        coordination_start_time = time.time() # Time taken by composite to decide and delegate
        
        # Prefer 'controller_for' workers (work-for-me relationship)
        active_workers = [rel['device'] for rel in self.relationships.get('controller_for', []) if rel.get('status') == 'active']
        
        for worker in active_workers:
            # Check if worker is capable of handling the task_type
            worker_can_handle = False
            if isinstance(worker, SensingDevice) and task_type == 'sense': worker_can_handle = True
            elif isinstance(worker, ActuatingDevice) and task_type == 'actuate': worker_can_handle = True
            elif isinstance(worker, CommunicatingDevice) and task_type == 'transmit': worker_can_handle = True
            elif hasattr(worker, 'capabilities') and task_type in worker.capabilities: worker_can_handle = True # For nested composite workers

            if worker_can_handle:
                self.log_event(f"Delegating '{task_type}' to worker {worker.nameShort()}.")
                # Composite (self) is the 'from_device' for the worker's perspective
                worker_outcome = worker.handle_request(self, task_type, load_for_sub_task, details_for_sub_task)
                
                # QoS Update: Composite (as requester) updates its trust IN THE WORKER based on worker's performance
                if 'measured_qos_for_requestor' in worker_outcome: # This QoS is from worker's perspective of its own performance
                    self.update_trust_from_qoe(
                        worker, # Partner is the worker
                        task_type, 
                        worker_outcome['measured_qos_for_requestor'], 
                        interaction_role="requester" # Composite is requester here
                    )

                if worker_outcome.get('success'):
                    self.log_event(f"Worker {worker.nameShort()} SUCCESS for '{task_type}'.")
                    # Monetary: Composite pays worker if this was a paid task.
                    # The 'iot_app_reward' in details_for_sub_task might be the worker's direct earning potential or share.
                    worker_share_of_reward = details_for_sub_task.get('iot_app_reward', 0) * self.worker_payment_ratio
                    if worker_share_of_reward > 0:
                         self.pay_expense(worker_share_of_reward, worker, f"Payment for delegated {task_type}")
                    
                    coordination_plus_worker_time_ms = (time.time() - coordination_start_time) * 1000
                    # Augment worker's outcome with composite's coordination time
                    # The 'response_time_ms' in worker_outcome is worker's own. The overall is longer.
                    final_outcome_for_composite = {
                        **worker_outcome, 
                        'coordination_overhead_ms': coordination_plus_worker_time_ms - worker_outcome.get('measured_qos_for_requestor',{}).get('response_time_ms',0),
                        'overall_delegated_response_time_ms': coordination_plus_worker_time_ms,
                        'delegated_to_worker': worker.nameShort()
                    }
                    return final_outcome_for_composite
                else:
                    self.log_event(f"Worker {worker.nameShort()} FAILED for '{task_type}': {worker_outcome.get('reason')}")
                    # Composite might penalize worker further, but trust update via QoE already happened.
                    # Continue to try other workers or sub_devices...

        # Try internal sub_devices if no worker succeeded or no workers available
        for sub_dev in self.sub_devices:
            sub_dev_can_handle = False
            # CORRECTED SYNTAX HERE:
            if (isinstance(sub_dev, SensingDevice) and task_type == 'sense') or \
               (isinstance(sub_dev, ActuatingDevice) and task_type == 'actuate') or \
               (isinstance(sub_dev, CommunicatingDevice) and task_type == 'transmit') or \
               (hasattr(sub_dev, 'capabilities') and task_type in sub_dev.capabilities): # For nested composite sub-devices
                sub_dev_can_handle = True

            if sub_dev_can_handle:
                self.log_event(f"Using internal sub-device {sub_dev.nameShort()} for '{task_type}'.")
                # Composite (self) is the 'from_device' for the sub_device
                sub_outcome = sub_dev.handle_request(self, task_type, load_for_sub_task, details_for_sub_task)
                # Trust for sub-devices might be handled differently (e.g., part of composite's overall reliability)
                # For simplicity, we can still use QoE if sub_outcome provides necessary QoS.
                if 'measured_qos_for_requestor' in sub_outcome:
                     self.update_trust_from_qoe(sub_dev, task_type, sub_outcome['measured_qos_for_requestor'], interaction_role="requester_internal")


                if sub_outcome.get('success'):
                    coordination_plus_sub_time_ms = (time.time() - coordination_start_time) * 1000
                    final_outcome_for_composite = {
                        **sub_outcome,
                        'coordination_overhead_ms': coordination_plus_sub_time_ms - sub_outcome.get('measured_qos_for_requestor',{}).get('response_time_ms',0),
                        'overall_delegated_response_time_ms': coordination_plus_sub_time_ms,
                        'used_sub_device': sub_dev.nameShort()
                    }
                    return final_outcome_for_composite
                else:
                    self.log_event(f"Sub-device {sub_dev.nameShort()} FAILED for '{task_type}'.")
        
        self.log_event(f"No suitable worker or sub-device found/succeeded for '{task_type}'.")
        coordination_failed_time_ms = (time.time() - coordination_start_time) * 1000
        return {'success': False, 'reason': 'no_delegate_success', 'coordination_overhead_ms': coordination_failed_time_ms, 'measured_qos_for_requestor': {'task_success_binary':0, 'response_time_ms': coordination_failed_time_ms}}


    def handle_request(self, from_device, task_type, load_requested=10, details=None):
        details = details or {}
        # Initial checks by base class (avoid, controller limits, base policy, initial load negotiation)
        base_acceptance = super().handle_request(from_device, task_type, load_requested, details)
        request_start_time = base_acceptance.get('request_start_time', time.time()) # Get precise start time

        if not base_acceptance.get('success'):
            # Base class determined failure. Propagate its detailed result.
            # The simulation loop will use base_acceptance['measured_qos_for_requestor']
            # for from_device to update its trust in this (self) CompositeDevice.
            return base_acceptance 

        # --- Composite Device's own logic for handling the task ---
        final_success_of_composite_task = False
        reason_for_composite_outcome = "coordination_failed_or_task_unsupported"
        # Composite's own load for coordination, distinct from delegate's load
        composite_coordination_load = int(load_requested * 0.15 * random.uniform(0.7, 1.3)) # Small load for composite's work
        if not self.consume_load(composite_coordination_load):
            self.log_event(f"Composite {self.nameShort()} failed to consume its own coordination load.")
            # This is a failure of the composite itself.
            overall_response_time_ms = (time.time() - request_start_time) * 1000
            measured_qos = {'task_success_binary': 0, 'response_time_ms': overall_response_time_ms, 'load_consumed': 0, 'expected_load_for_task': load_requested}
            self.update_trust_from_qoe(from_device, task_type, measured_qos, interaction_role="performer")
            return {'success': False, 'reason': 'composite_self_overload_for_coordination', 'measured_qos_for_requestor': measured_qos, 'request_start_time': request_start_time}

        action_outcome_details = {} # To store details from direct action or delegation

        # Option 1: Composite handles task directly (e.g., a 'coordinate' task type, or if it has the primitive capability)
        if task_type == "coordinate" or (task_type in self.capabilities and random.random() < 0.2): # Small chance to handle primitive directly
            self.log_event(f"Composite {self.nameShort()} handling '{task_type}' directly.")
            time.sleep(self.announced_qos.get('coordination_overhead_ms', 30) / 1000 * random.uniform(0.8, 1.2)) # Simulate work
            final_success_of_composite_task = True # Simplified: direct handling is successful
            reason_for_composite_outcome = "coordinated_directly_by_composite"
            action_outcome_details = {'success': True, 'processing_time_ms': self.announced_qos.get('coordination_overhead_ms',30)}
        
        # Option 2: Delegate the task
        else:
            self.log_event(f"Composite {self.nameShort()} attempting to delegate '{task_type}'.")
            # Prepare details for sub-task. If composite has a main reward, worker gets a portion.
            sub_task_details = details.copy() 
            # Example: if main reward for composite is X, worker's part could be Y.
            # sub_task_details['iot_app_reward'] = details.get('iot_app_reward', 0) * self.worker_payment_ratio 
            # This needs careful thought on how rewards flow. For now, assume sub_task_details are passed as is.
            
            delegation_outcome = self._delegate_to_worker_or_sub(task_type, from_device, load_requested, sub_task_details)
            
            if delegation_outcome and delegation_outcome.get('success'):
                final_success_of_composite_task = True
                reason_for_composite_outcome = f"delegated_to_{delegation_outcome.get('delegated_to_worker') or delegation_outcome.get('used_sub_device','unknown_delegate')}"
                action_outcome_details = delegation_outcome # This now contains QoS from delegate + coordination_overhead
            else:
                reason_for_composite_outcome = delegation_outcome.get('reason', "delegation_failed_no_suitable_handler") if delegation_outcome else "delegation_returned_None"
                action_outcome_details = delegation_outcome or {}

        overall_response_time_ms = (time.time() - request_start_time) * 1000
        
        # Compile final QoS metrics for the Composite's performance of this entire task
        measured_qos_for_trust_and_requestor = {
            'task_success_binary': 1 if final_success_of_composite_task else 0,
            'response_time_ms': overall_response_time_ms,
            'load_consumed': composite_coordination_load + action_outcome_details.get('load_consumed', 0), # Composite's load + delegate's load
            'expected_load_for_task': load_requested, # Original request's expected load
            'coordination_overhead_ms_measured': action_outcome_details.get('coordination_overhead_ms', self.announced_qos.get('coordination_overhead_ms',30) if final_success_of_composite_task else overall_response_time_ms),
            # Include key QoS from delegate if successful delegation occurred
            'delegate_processing_time_ms': action_outcome_details.get('processing_time_ms') if final_success_of_composite_task and "delegated_to_" in reason_for_composite_outcome else None,
            'delegate_success_binary': action_outcome_details.get('success') if "delegated_to_" in reason_for_composite_outcome else None,
        }
        
        # Composite device (performer of the overall task) updates its own general trust
        self.update_trust_from_qoe(from_device, task_type, measured_qos_for_trust_and_requestor, interaction_role="performer")

        if final_success_of_composite_task:
            self.log_event(f"Composite {self.nameShort()} SUCCEEDED managing '{task_type}' for {from_device.name if from_device else 'autonomous_task'}. Reason: {reason_for_composite_outcome}")
            # Monetary reward for the composite's successful coordination/execution
            main_iot_reward = details.get('iot_app_reward', 0) 
            if main_iot_reward > 0 :
                 final_composite_reward = main_iot_reward * (self.base_composite_task_reward_multiplier if not from_device or from_device==self else 1.0)
                 # Ensure not to pay self if from_device is self (can happen if composite calls its own handle_request via delegation)
                 if from_device != self:
                    self.receive_income(final_composite_reward, f"Coordinated Task '{task_type}'")
            
            return {'success': True, 'reason': reason_for_composite_outcome, 'action_details': action_outcome_details,
                    'measured_qos_for_requestor': measured_qos_for_trust_and_requestor, 'request_start_time': request_start_time}
        else:
            self.log_event(f"Composite {self.nameShort()} FAILED to manage '{task_type}' for {from_device.name if from_device else 'autonomous_task'}. Reason: {reason_for_composite_outcome}")
            # Backup logic for the composite itself could be attempted here
            # ...
            return {'success': False, 'reason': reason_for_composite_outcome, 'action_details': action_outcome_details,
                    'measured_qos_for_requestor': measured_qos_for_trust_and_requestor, 'request_start_time': request_start_time}

    # report_status is inherited