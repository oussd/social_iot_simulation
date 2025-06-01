import random
import time
from typing import List, Dict, Any, Optional
from .device import Device, QoELevel # Base class
from .sensing_device import SensingDevice
from .actuating_device import ActuatingDevice
from .communicating_device import CommunicatingDevice

class CompositeDevice(Device):
    def __init__(self, device_id: str, name: str, max_load: int = 150,
                 capabilities: Optional[List[str]] = None,
                 framework_variant: str = "full_siot",
                 logger_instance=None,
                 current_minute_provider=None,
                 **kwargs): 

        default_capabilities = ["coordinate_tasks"]
        if capabilities:
            for cap in capabilities:
                if cap not in default_capabilities:
                    default_capabilities.append(cap)

        super().__init__(device_id, name, max_load, framework_variant,
                         default_capabilities, logger_instance, current_minute_provider,
                         **kwargs) 

        self.base_composite_task_reward_multiplier = 1.2
        self.worker_payment_ratio = 0.65

        if self.behavior_profile != 'deceptive':
            if 'coordination_overhead_ms' not in self.announced_qos:
                self.announced_qos['coordination_overhead_ms'] = random.uniform(10, 40)
                self.qoe_thresholds['coordination_overhead_ms'] = {'sigma': 15.0, 'delta':10.0}
            if 'delegate_success_rate' not in self.announced_qos:
                self.announced_qos['delegate_success_rate'] = random.uniform(0.85, 0.98)
                self.qoe_thresholds['delegate_success_rate'] = {'sigma': 0.15, 'delta': 0.1}
        elif 'coordination_overhead_ms' not in self.announced_qos: 
            self.announced_qos['coordination_overhead_ms'] = random.uniform(5, 20) 
            self.announced_qos['delegate_success_rate'] = random.uniform(0.95, 0.999) 
            self.qoe_thresholds['coordination_overhead_ms'] = {'sigma': 15.0, 'delta':10.0}
            self.qoe_thresholds['delegate_success_rate'] = {'sigma': 0.15, 'delta': 0.1}


    def _delegate_to_worker(self, task_type: str, original_requestor_device: Optional[Device],
                            load_for_sub_task: int, details_for_sub_task: Dict) -> Dict[str, Any]:
        coordination_start_time = time.time()
        default_failure_qos = {
            'task_success_binary':0,
            'response_time_ms': (time.time()-coordination_start_time)*1000,
            'expected_load_for_task': load_for_sub_task
        }

        effective_load_for_sub_task = load_for_sub_task
        if self.behavior_profile == 'policy_violator' and random.random() < 0.2:
            effective_load_for_sub_task = int(load_for_sub_task * random.uniform(1.2, 1.5))
            self.log_debug(f"Policy violator {self.nameShort()} attempting to delegate '{task_type}' with inflated load {effective_load_for_sub_task} (actual: {load_for_sub_task})")

        if self.framework_variant == "baseline":
            self.log_debug(f"Baseline mode: Composite {self.nameShort()} cannot effectively delegate '{task_type}' via social hierarchy.")
            return {'success': False, 'reason': 'baseline_no_delegation_framework',
                    'measured_qos_for_requestor': default_failure_qos}

        active_workers_rels = [rel for rel in self.relationships.get('controller_for', []) if rel.get('status') == 'active']
        
        capable_workers: List[Device] = []
        required_sub_sensor_type = details_for_sub_task.get('sensor_type') if task_type == 'sense' else None
        required_sub_actuator_type = details_for_sub_task.get('actuator_type') if task_type == 'actuate' else None

        for rel in active_workers_rels:
            worker = rel['device']
            worker_capabilities = getattr(worker, 'capabilities', [])
            is_suitable = False

            # Handle specific task types
            if task_type == 'sense':
                if isinstance(worker, SensingDevice):
                    if required_sub_sensor_type:
                        if getattr(worker, 'sensor_type', None) == required_sub_sensor_type:
                            is_suitable = True
                    else:
                        is_suitable = True  # Any sensor can handle generic sense tasks
            elif task_type == 'actuate':
                if isinstance(worker, ActuatingDevice):
                    if required_sub_actuator_type:
                        if getattr(worker, 'actuator_type', None) == required_sub_actuator_type:
                            is_suitable = True
                    else:
                        is_suitable = True  # Any actuator can handle generic actuate tasks
            elif task_type == 'transmit':
                if isinstance(worker, CommunicatingDevice):
                    is_suitable = True
            # Handle composite tasks
            elif task_type in ['manage_hvac', 'manage_lighting', 'zone_security_local', 'delegate_zone_tasks', 'access_control_zone']:
                if isinstance(worker, CompositeDevice):
                    if task_type in worker.capabilities:
                        is_suitable = True
            # Handle generic capabilities
            elif task_type in worker_capabilities:
                is_suitable = True

            if is_suitable:
                capable_workers.append(worker)

        if not capable_workers:
            self.log_warning(f"No capable workers found for task '{task_type}' (specific type: {required_sub_sensor_type or required_sub_actuator_type or 'N/A'}).")
            return {'success': False, 'reason': 'no_capable_workers_found', 'measured_qos_for_requestor': default_failure_qos}

        selected_worker = self.select_worker_for_task(capable_workers, f"delegate_{task_type}_for_{self.nameShort()}")

        if not selected_worker:
            self.log_warning(f"Could not select a worker for task '{task_type}' from {len(capable_workers)} capable ones.")
            return {'success': False, 'reason': 'worker_selection_failed', 'measured_qos_for_requestor': default_failure_qos}

        self.log_info(f"Delegating '{task_type}' (details: {details_for_sub_task}) to selected worker {selected_worker.nameShort()}. Requesting load: {effective_load_for_sub_task}")
        worker_outcome = selected_worker.handle_request(self, task_type, effective_load_for_sub_task, details_for_sub_task) 

        if 'measured_qos_for_requestor' in worker_outcome:
            self.update_trust_from_qoe(
                selected_worker, task_type,
                worker_outcome['measured_qos_for_requestor'],
                interaction_role="requester"
            )

        rel_entry = self.get_relationship_with(selected_worker, 'controller_for')
        if rel_entry:
            rel_entry['interaction_count'] = rel_entry.get('interaction_count',0) + 1
            if worker_outcome.get('success'):
                rel_entry['successful_interactions'] = rel_entry.get('successful_interactions',0) + 1
            else:
                rel_entry['failed_interactions'] = rel_entry.get('failed_interactions',0) + 1

        if worker_outcome.get('success'):
            self.log_info(f"Worker {selected_worker.nameShort()} SUCCESS for '{task_type}'.")
            main_job_reward_for_this_subtask = details_for_sub_task.get('iot_app_reward_for_subtask', 0)
            worker_payment = 0
            if main_job_reward_for_this_subtask > 0:
                 worker_payment = main_job_reward_for_this_subtask * self.worker_payment_ratio
            elif not original_requestor_device or original_requestor_device == self :
                 worker_payment = getattr(selected_worker, 'task_failure_penalty_value', 5.0) * 0.2
            
            if self.behavior_profile == 'selfish' and worker_payment > 0 and random.random() < 0.3: 
                underpayment_factor = random.uniform(0.2, 0.6)
                self.log_info(f"Selfish composite {self.nameShort()} attempting to underpay worker {selected_worker.nameShort()} by factor {underpayment_factor:.2f}")
                worker_payment *= underpayment_factor

            if worker_payment > 0:
                self.pay_expense(worker_payment, selected_worker, f"Payment for delegated {task_type}")

            coordination_plus_worker_time_ms = (time.time() - coordination_start_time) * 1000
            delegate_response_time = worker_outcome.get('measured_qos_for_requestor',{}).get('response_time_ms',0)
            return {
                **worker_outcome,
                'coordination_overhead_ms': max(0, coordination_plus_worker_time_ms - delegate_response_time),
                'overall_delegated_response_time_ms': coordination_plus_worker_time_ms,
                'delegated_to_worker_id': selected_worker.device_id,
                'delegated_to_worker_name': selected_worker.nameShort()
            }
        else: 
            self.log_warning(f"Worker {selected_worker.nameShort()} FAILED for '{task_type}': {worker_outcome.get('reason')}")
            if self.behavior_profile == 'policy_violator' and random.random() < 0.4:
                penalty_amount = selected_worker.task_failure_penalty_value * random.uniform(1.5, 2.5) 
                self.log_info(f"Policy violator {self.nameShort()} unfairly penalizing {selected_worker.nameShort()} with {penalty_amount:.2f} for failed task '{task_type}'.")
                self.apply_penalty_to_device(selected_worker, penalty_amount, f"Unfair penalty for failed delegated task {task_type} by policy violator {self.nameShort()}")
                if self.sim_metrics_ref: self.sim_metrics_ref['misuse_incidents_detected'] = self.sim_metrics_ref.get('misuse_incidents_detected',0) + 1
            elif self.framework_variant == "full_siot": 
                if rel_entry and rel_entry.get('consecutive_failures',0) >= self.policy.get('max_failed_interactions_before_avoid',3):
                     self.log_warning(f"Worker {selected_worker.nameShort()} has {rel_entry['consecutive_failures']} consec. failures. Composite applying penalty.", context_override=self.nameShort()) # Kept context_override for this specific log
                     self.apply_penalty_to_device(selected_worker, selected_worker.task_failure_penalty_value * 1.5, f"Persistent failure on delegated task {task_type}")

            coordination_plus_worker_time_ms = (time.time() - coordination_start_time) * 1000
            failure_qos = worker_outcome.get('measured_qos_for_requestor', default_failure_qos)
            return {**worker_outcome, 'success': False, 'measured_qos_for_requestor': failure_qos,
                    'coordination_overhead_ms': coordination_plus_worker_time_ms,
                    'delegated_to_worker_id': selected_worker.device_id}

    def handle_request(self, from_device: Optional[Device], task_type: str,
                       load_requested: int = 10, details: Optional[Dict] = None) -> Dict[str, Any]:
        details = details if details is not None else {}
        base_acceptance_outcome = super().handle_request(from_device, task_type, load_requested, details)
        request_start_time = base_acceptance_outcome.get('request_start_time', time.time())

        if not base_acceptance_outcome.get('success'):
            return base_acceptance_outcome

        final_success_of_composite_task = False
        reason_for_composite_outcome = "composite_coordination_failed"
        composite_coordination_load = int(self.announced_qos.get('coordination_overhead_ms', 20) / 10) 
        composite_coordination_load = max(5, min(self.max_load // 10, composite_coordination_load))

        if not self.consume_load(composite_coordination_load):
            self.log_warning(f"Composite {self.nameShort()} FAILED to consume its own coordination load {composite_coordination_load}.")
            overall_response_time_ms = (time.time() - request_start_time) * 1000
            measured_qos = {'task_success_binary': 0, 'response_time_ms': overall_response_time_ms,
                            'load_consumed': 0, 'expected_load_for_task': load_requested}
            self.update_trust_from_qoe(from_device, task_type, measured_qos, interaction_role="performer")
            return {'success': False, 'reason': 'composite_self_overload_for_coordination',
                    'measured_qos_for_requestor': measured_qos, 'request_start_time': request_start_time}

        action_outcome_details: Dict[str, Any] = {'success': False}

        if self.framework_variant == "baseline":
            if task_type in self.capabilities and random.random() < 0.1:
                self.log_info(f"Baseline Composite {self.nameShort()} attempting '{task_type}' directly (low chance).")
                time.sleep(random.uniform(0.05, 0.2))
                final_success_of_composite_task = random.random() < 0.3
                reason_for_composite_outcome = "baseline_direct_attempt_composite"
                action_outcome_details = {'success': final_success_of_composite_task,
                                          'processing_time_ms': (time.time()-request_start_time)*1000 - composite_coordination_load,
                                          'load_consumed': composite_coordination_load}
            else:
                reason_for_composite_outcome = "baseline_composite_cannot_delegate_effectively_or_perform"
                action_outcome_details = {'success': False, 'measured_qos_for_requestor': {'task_success_binary':0, 'expected_load_for_task': load_requested}}
        else: 
            is_direct_coordination_task = task_type in getattr(self, 'direct_coordination_tasks', []) or \
                                          (task_type in ["coordinate_zones", "set_global_policy", "emergency_response"] and "BMS" in self.name)

            if is_direct_coordination_task:
                self.log_info(f"Composite {self.nameShort()} handling '{task_type}' as direct coordination.")
                simulated_processing_time = self.announced_qos.get('coordination_overhead_ms', 30) * random.uniform(0.7, 1.3)
                if self.behavior_profile == 'deceptive':
                    simulated_processing_time /= self.deception_factor
                
                time.sleep(simulated_processing_time / 1000.0)
                
                if random.random() < self.fault_probability:
                    final_success_of_composite_task = False
                    reason_for_composite_outcome = "direct_coordination_fault_by_composite"
                    self.log_warning(f"Composite {self.nameShort()} experienced internal fault during direct coordination of '{task_type}'.")
                else:
                    final_success_of_composite_task = True
                    reason_for_composite_outcome = "direct_coordination_by_composite"

                action_outcome_details = {'success': final_success_of_composite_task, 'processing_time_ms': simulated_processing_time, 'load_consumed': composite_coordination_load}
            else:
                self.log_info(f"Composite {self.nameShort()} attempting to delegate '{task_type}'.")
                sub_task_load = max(5, load_requested - composite_coordination_load)
                delegation_outcome = self._delegate_to_worker(task_type, from_device, sub_task_load, details) 
                action_outcome_details = delegation_outcome
                if delegation_outcome and delegation_outcome.get('success'):
                    final_success_of_composite_task = True
                    reason_for_composite_outcome = f"delegated_to_{delegation_outcome.get('delegated_to_worker_name','unknown_delegate')}"
                else:
                    reason_for_composite_outcome = delegation_outcome.get('reason', "delegation_failed") if isinstance(delegation_outcome, dict) else "delegation_returned_None"
                    final_success_of_composite_task = False
                    action_outcome_details = delegation_outcome if isinstance(delegation_outcome, dict) else {'success': False, 'reason': reason_for_composite_outcome}

        overall_response_time_ms = (time.time() - request_start_time) * 1000
        delegated_load_consumed = 0
        if final_success_of_composite_task and "delegated_to" in reason_for_composite_outcome:
            worker_measured_qos = action_outcome_details.get('measured_qos_for_requestor', {})
            delegated_load_consumed = worker_measured_qos.get('load_consumed', 0)

        total_load_consumed_for_task = composite_coordination_load + delegated_load_consumed

        measured_qos_for_trust_and_requestor = {
            'task_success_binary': 1 if final_success_of_composite_task else 0,
            'response_time_ms': overall_response_time_ms,
            'load_consumed': total_load_consumed_for_task,
            'expected_load_for_task': load_requested,
            'coordination_overhead_ms_measured': action_outcome_details.get('coordination_overhead_ms', self.announced_qos.get('coordination_overhead_ms',30) if final_success_of_composite_task else overall_response_time_ms),
            'delegate_success_rate_measured': 1.0 if final_success_of_composite_task and "delegated_to" in reason_for_composite_outcome else 0.0,
        }
        if final_success_of_composite_task and "delegated_to" in reason_for_composite_outcome:
            worker_qos = action_outcome_details.get('measured_qos_for_requestor', {})
            measured_qos_for_trust_and_requestor['worker_processing_time_ms'] = worker_qos.get('processing_time_ms')
            if 'data_accuracy_measured' in worker_qos:
                 measured_qos_for_trust_and_requestor['data_accuracy_measured'] = worker_qos.get('data_accuracy_measured')
            if 'state_changed_correctly_binary' in worker_qos:
                 measured_qos_for_trust_and_requestor['state_changed_correctly_binary'] = worker_qos.get('state_changed_correctly_binary')

        self.update_trust_from_qoe(from_device, task_type, measured_qos_for_trust_and_requestor, interaction_role="performer")

        if final_success_of_composite_task:
            self.log_info(f"Composite {self.nameShort()} SUCCEEDED managing '{task_type}' for {from_device.nameShort() if from_device else 'autonomous_task'}. Reason: {reason_for_composite_outcome}")
            main_iot_reward = details.get('iot_app_reward', 0)
            if main_iot_reward > 0 :
                 final_composite_reward = main_iot_reward * (self.base_composite_task_reward_multiplier if (not from_device or from_device==self) else 1.0)
                 if from_device != self:
                    self.receive_income(final_composite_reward, f"Coordinated Task '{task_type}'")
            return_value = action_outcome_details.get('value')
            return {'success': True, 'reason': reason_for_composite_outcome, 'value': return_value, 'action_details': action_outcome_details,
                    'measured_qos_for_requestor': measured_qos_for_trust_and_requestor, 'request_start_time': request_start_time}
        else:
            self.log_warning(f"Composite {self.nameShort()} FAILED to manage '{task_type}' for {from_device.nameShort() if from_device else 'autonomous_task'}. Reason: {reason_for_composite_outcome}")
            if self.framework_variant in ["social_basic", "full_siot"]:
                active_backups = [rel['device'] for rel in self.relationships.get('back_me', []) if rel.get('status')=='active']
                if active_backups:
                    backup_composite_candidate = self.select_worker_for_task(active_backups, f"backup_for_composite_task_{task_type}")
                    if backup_composite_candidate and isinstance(backup_composite_candidate, CompositeDevice) and \
                       backup_composite_candidate != from_device and backup_composite_candidate != self:
                        self.log_info(f"Attempting backup for composite task '{task_type}' with {backup_composite_candidate.nameShort()}")
                        backup_details = details.copy(); backup_details['is_backup_attempt'] = True
                        backup_details['original_backup_initiator'] = self.device_id
                        backup_outcome = backup_composite_candidate.handle_request(from_device, task_type, load_requested, backup_details)
                        self.update_trust_from_qoe(backup_composite_candidate, task_type, backup_outcome.get('measured_qos_for_requestor',{}), "requester")
                        if backup_outcome.get('success'):
                            self.log_info(f"Backup by {backup_composite_candidate.nameShort()} for composite task SUCCEEDED.")
                            if self.sim_metrics_ref and 'back_me_invocations_successful' in self.sim_metrics_ref:
                                self.sim_metrics_ref['back_me_invocations_successful'] +=1
                            return {**backup_outcome, 'backed_up_by': backup_composite_candidate.device_id}
                        else:
                            if self.sim_metrics_ref and 'back_me_invocations_failed' in self.sim_metrics_ref:
                                self.sim_metrics_ref['back_me_invocations_failed'] +=1
                            self.log_warning(f"Backup by {backup_composite_candidate.nameShort()} for composite task FAILED.")
            return {'success': False, 'reason': reason_for_composite_outcome, 'action_details': action_outcome_details,
                    'measured_qos_for_requestor': measured_qos_for_trust_and_requestor, 'request_start_time': request_start_time}
