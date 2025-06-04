# src/devices/composite_device.py

import random
import time
from typing import List, Dict, Any, Optional, Callable, TYPE_CHECKING, Tuple

if TYPE_CHECKING:
    from .device import Device # For type hinting
    from ..utils.logger import SimulationLogger

from .device import Device, DEFAULT_POLICY_STORE 
# Import JOB_PROPERTIES from its correct location
from ..simulations.scenario_generator import JOB_PROPERTIES 
from .sensing_device import SensingDevice
from .actuating_device import ActuatingDevice
from .communicating_device import CommunicatingDevice


class CompositeDevice(Device):
    def __init__(self, device_id: str, name: str, max_load: int = 150, # Composite might have slightly higher base load
                 capabilities: Optional[List[str]] = None,
                 framework_variant: str = "full_siot",
                 logger_instance: Optional['SimulationLogger'] = None, # Corrected type hint
                 current_minute_provider: Optional[Callable[[], int]] = None, # Corrected type hint
                 worker_devices_initial: Optional[List['Device']] = None, # Renamed for clarity
                 **kwargs): 

        default_capabilities = ["coordinate_tasks", "delegate_work"] # Added delegate_work
        if "PERIODIC_HEALTH_CHECK" not in default_capabilities:
            default_capabilities.append("PERIODIC_HEALTH_CHECK")
        
        if capabilities: # Merge provided capabilities with defaults
            for cap in capabilities:
                if cap not in default_capabilities:
                    default_capabilities.append(cap)

        super().__init__(device_id, name, max_load, framework_variant,
                         default_capabilities, logger_instance, current_minute_provider,
                         **kwargs) 

        self.workers: List[Device] = [] # Initialize as empty, add via add_worker
        if worker_devices_initial:
            for worker in worker_devices_initial:
                self.add_worker(worker) # Use method to establish relationships

        self.active_coordinated_tasks: Dict[str, Dict[str, Any]] = {} 
        self.base_coordination_reward = 20
        self.worker_payment_ratio = 0.65 # Ratio of task reward paid to worker

        # Announced QoS for coordination
        if self.behavior_profile != 'deceptive':
            if 'coordination_overhead_ms' not in self.announced_qos:
                self.announced_qos['coordination_overhead_ms'] = random.uniform(10, 40) # Time it takes to decide and delegate
                if 'coordination_overhead_ms' not in self.qoe_thresholds:
                    self.qoe_thresholds['coordination_overhead_ms'] = {'sigma': 15.0, 'delta':10.0}
            if 'task_planning_success_rate' not in self.announced_qos: # Ability to successfully plan and see a multi-step task through
                self.announced_qos['task_planning_success_rate'] = random.uniform(0.85, 0.98)
                if 'task_planning_success_rate' not in self.qoe_thresholds:
                     self.qoe_thresholds['task_planning_success_rate'] = self.qoe_thresholds.get('task_success_rate', {'sigma': 0.1, 'delta': 0.05})
        elif 'coordination_overhead_ms' not in self.announced_qos: 
            self.announced_qos['coordination_overhead_ms'] = random.uniform(5, 20) 
            self.announced_qos['task_planning_success_rate'] = random.uniform(0.95, 0.999)
            if 'coordination_overhead_ms' not in self.qoe_thresholds:
                self.qoe_thresholds['coordination_overhead_ms'] = {'sigma': 15.0, 'delta':10.0}
            if 'task_planning_success_rate' not in self.qoe_thresholds:
                self.qoe_thresholds['task_planning_success_rate'] = self.qoe_thresholds.get('task_success_rate', {'sigma': 0.1, 'delta': 0.05})


    def add_worker(self, worker: 'Device'):
        if worker not in self.workers:
            self.workers.append(worker)
            self.log_info(f"Added worker {worker.nameShort()} to {self.nameShort()}'s pool.")
            self.add_relationship(worker, "controller_for", initial_trust=0.7, policy_id="default_task_policy") 
            if hasattr(worker, 'add_relationship'): 
                worker.add_relationship(self, "work_for_me", initial_trust=0.7, policy_id="default_task_policy") 

    def _delegate_to_worker(self, sub_task_type: str, original_job_details: Dict, 
                              required_capability: str,
                              original_request_start_time: float,
                              attempt_number: int = 1,
                              tried_workers_ids: Optional[List[str]] = None) -> Dict[str, Any]:
        self.log_debug(f"Attempting to delegate sub-task '{sub_task_type}' (Attempt: {attempt_number}, Job: {self.current_job_id}). Required cap: {required_capability}")
        tried_workers_ids = tried_workers_ids if tried_workers_ids is not None else []
        coordination_start_time_for_this_delegation = time.time() 

        capable_workers = [
            w for w in self.workers 
            if required_capability in w.capabilities and w.device_id not in tried_workers_ids and w.status == "active"
        ]

        if not capable_workers:
            self.log_warning(f"No capable and untried workers found for sub-task '{sub_task_type}' (capability: {required_capability}, Job: {self.current_job_id}).")
            return {'success': False, 'reason': f'no_capable_untried_worker_for_{required_capability}', 
                    'measured_qos_for_requestor': {'task_success_binary':0, 'response_time_ms': (time.time()-coordination_start_time_for_this_delegation)*1000}}

        selected_worker = self.select_worker_for_task(capable_workers, task_description=f"sub-task '{sub_task_type}' for {self.nameShort()}")

        if not selected_worker:
            self.log_warning(f"Worker selection failed for sub-task '{sub_task_type}' (Job: {self.current_job_id}). No available worker chosen from {len(capable_workers)} capable ones.")
            return {'success': False, 'reason': 'worker_selection_failed_among_capable', 
                    'measured_qos_for_requestor': {'task_success_binary':0, 'response_time_ms': (time.time()-coordination_start_time_for_this_delegation)*1000}}

        self.log_info(f"Delegating sub-task '{sub_task_type}' (Job: {self.current_job_id}, Attempt: {attempt_number}) to worker {selected_worker.nameShort()}.")
        tried_workers_ids.append(selected_worker.device_id)

        delegation_details = original_job_details.copy() 
        delegation_details["delegator_device_id"] = self.device_id
        delegation_details["original_job_id"] = self.current_job_id 
        delegation_details["iot_app_reward"] = original_job_details.get(f"sub_task_{sub_task_type}_reward", 
                                                                         original_job_details.get("iot_app_reward", self.base_task_reward) * self.worker_payment_ratio)
        sub_task_props = JOB_PROPERTIES.get(sub_task_type, {})
        default_load_range = sub_task_props.get("work_units_base", (5,10))
        sub_task_load = original_job_details.get(f"sub_task_{sub_task_type}_load", random.randint(*default_load_range) if sub_task_props else 10)


        # time.sleep(self.announced_qos.get('coordination_overhead_ms', 20) / 1000.0) # Simulate delegation overhead - COMMENTED OUT
        
        worker_outcome = selected_worker.handle_request(
            from_device=self,
            task_type=sub_task_type, 
            load_requested=int(sub_task_load), 
            details=delegation_details
        )
        
        if worker_outcome.get("success"):
            self.log_info(f"Worker {selected_worker.nameShort()} SUCCEEDED sub-task '{sub_task_type}' (Job: {self.current_job_id}, Attempt: {attempt_number}).")
            return worker_outcome 
        else:
            self.log_warning(f"Worker {selected_worker.nameShort()} FAILED sub-task '{sub_task_type}' (Job: {self.current_job_id}, Attempt: {attempt_number}). Reason: {worker_outcome.get('reason')}")
            
            max_retries = self.policy.get("rules",{}).get("max_redelegation_attempts", 1) 
            if self.framework_variant in ["social_basic", "full_siot"] and attempt_number <= max_retries:
                self.log_info(f"Attempting re-delegation for failed sub-task '{sub_task_type}' (Job: {self.current_job_id}). Next attempt: {attempt_number + 1}.")
                if self.sim_metrics_ref:
                    self.sim_metrics_ref['redelegation_attempts'] = self.sim_metrics_ref.get('redelegation_attempts', 0) + 1
                
                retry_outcome = self._delegate_to_worker(sub_task_type, original_job_details, required_capability, original_request_start_time, attempt_number + 1, tried_workers_ids)
                
                if retry_outcome and retry_outcome.get("success"):
                    if self.sim_metrics_ref:
                        self.sim_metrics_ref['redelegation_successes_after_failure'] = self.sim_metrics_ref.get('redelegation_successes_after_failure', 0) + 1
                    return retry_outcome
                else: 
                    if self.sim_metrics_ref:
                        self.sim_metrics_ref['redelegation_failures_after_failure'] = self.sim_metrics_ref.get('redelegation_failures_after_failure', 0) + 1
                    return worker_outcome 
            else: 
                return worker_outcome 

    def can_handle_task(self, task_type: str, details: Optional[Dict] = None) -> Tuple[bool, str]:
        if task_type == "PERIODIC_HEALTH_CHECK":
            return True, "Can handle health check."
        if task_type == "COORDINATE_TASKS": 
            sub_tasks = details.get("sub_tasks_sequence", []) if details else []
            if not sub_tasks:
                return False, "No sub_tasks_sequence defined in details for COORDINATE_TASKS."
            return True, "Can attempt to coordinate sub-tasks."
        if task_type in self.capabilities and task_type not in ["coordinate_tasks", "delegate_work"]:
            return True, f"Composite device has direct capability '{task_type}'."

        return False, f"Composite device does not directly handle task '{task_type}' beyond coordination or its direct capabilities."

    def handle_request(self, from_device: Optional[Device], task_type: str,
                       load_requested: int = 10, details: Optional[Dict] = None) -> Dict[str, Any]:
        details = details if details is not None else {}
        self.current_job_id = details.get("id", details.get("job_id", f"comp_job_{random.randint(1000,9999)}"))
        
        base_acceptance_outcome = super().handle_request(from_device, task_type, load_requested, details)
        request_start_time = base_acceptance_outcome.get('request_start_time', time.time())

        if not base_acceptance_outcome.get('success'):
            self.current_job_id = None
            return base_acceptance_outcome 

        can_handle_bool, reason_str = self.can_handle_task(task_type, details)
        if not can_handle_bool:
            self.log_warning(f"Cannot handle task '{task_type}' (Job: {self.current_job_id}). Reason: {reason_str}")
            overall_response_time_ms = (time.time() - request_start_time) * 1000
            measured_qos = {'task_success_binary': 0, 'response_time_ms': overall_response_time_ms, 'expected_load_for_task': load_requested}
            if from_device: self.update_trust_from_qoe(from_device, task_type, measured_qos, interaction_role="performer_rejected_task")
            self.current_job_id = None
            return {'success': False, 'reason': f'unsupported_task_type_by_composite:_{reason_str}', 
                    'measured_qos_for_requestor': measured_qos, 'request_start_time': request_start_time }

        action_outcome_details: Dict[str, Any] = {'success': False, 'reason': 'no_action_performed_by_composite_default'}
        final_success_of_composite_task = False
        reason_for_composite_outcome = "composite_coordination_failed"
        composite_coordination_load_cost = max(1, int(self.announced_qos.get('coordination_overhead_ms', 20) / 5)) 
        
        if not self.consume_load(composite_coordination_load_cost):
            self.log_warning(f"Composite {self.nameShort()} FAILED to consume its own coordination load {composite_coordination_load_cost} for task '{task_type}' (Job: {self.current_job_id}).")
            self.current_job_id = None
            return {'success': False, 'reason': 'composite_self_overload_for_coordination_effort',
                    'measured_qos_for_requestor': {'task_success_binary': 0, 'response_time_ms': (time.time() - request_start_time) * 1000, 'load_consumed': 0, 'expected_load_for_task': load_requested}, 
                    'request_start_time': request_start_time}

        if task_type == "PERIODIC_HEALTH_CHECK":
            action_outcome_details = {'success': True, 'value': 'OK_COMPOSITE_HEALTHY', 'load_consumed': composite_coordination_load_cost, 'processing_time_ms': (time.time() - request_start_time) * 1000}
            final_success_of_composite_task = True
            reason_for_composite_outcome = "health_check_composite_ok"
        
        elif task_type == "COORDINATE_TASKS":
            sub_tasks_sequence = details.get("sub_tasks_sequence", []) 
            all_sub_tasks_successful_overall = True
            aggregated_sub_task_results_for_job = []
            
            if not self.workers:
                action_outcome_details = {'success': False, 'reason': 'no_workers_available_for_coordination'}
                all_sub_tasks_successful_overall = False
                reason_for_composite_outcome = "no_workers_to_coordinate"
            else:
                for sub_task_idx, sub_task_info in enumerate(sub_tasks_sequence):
                    sub_task_type = sub_task_info.get("type")
                    sub_task_capability = sub_task_info.get("capability", sub_task_type) 
                    sub_task_details_from_job = sub_task_info.get("details", {})
                    
                    merged_sub_task_details_for_worker = {
                        **details, 
                        **sub_task_details_from_job, 
                        "sub_task_id": f"{self.current_job_id}_sub_{sub_task_idx}"
                    }
                    
                    sub_task_props_local = JOB_PROPERTIES.get(sub_task_type, {})
                    default_load_range = sub_task_props_local.get("work_units_base", (5,10))
                    load_for_this_sub_task = sub_task_info.get("work_units_required", random.randint(*default_load_range) if sub_task_props_local else 10) 
                    
                    delegation_outcome = self._delegate_to_worker(
                        sub_task_type, 
                        merged_sub_task_details_for_worker, 
                        sub_task_capability, 
                        request_start_time,
                        attempt_number=1, 
                        tried_workers_ids=[] 
                    )
                    
                    aggregated_sub_task_results_for_job.append(delegation_outcome)

                    if not delegation_outcome.get("success"):
                        all_sub_tasks_successful_overall = False
                        self.log_warning(f"Sub-task '{sub_task_type}' for COORDINATE_TASKS (Job: {self.current_job_id}) FAILED. Halting coordination for this job.")
                        reason_for_composite_outcome = f"sub_task_{sub_task_type}_failed_on_worker_{delegation_outcome.get('delegated_to_worker_name','Unknown')}"
                        break 
                
                if all_sub_tasks_successful_overall:
                    reason_for_composite_outcome = 'all_sub_tasks_coordinated_successfully'
                
                action_outcome_details = { 
                    'success': all_sub_tasks_successful_overall,
                    'reason': reason_for_composite_outcome,
                    'sub_task_outcomes': aggregated_sub_task_results_for_job, 
                    'load_consumed': composite_coordination_load_cost, 
                    'processing_time_ms': (time.time() - request_start_time) * 1000 
                }
                final_success_of_composite_task = all_sub_tasks_successful_overall

        overall_response_time_ms = (time.time() - request_start_time) * 1000
        
        delegated_load_consumed = 0
        if "delegated_to" in reason_for_composite_outcome and action_outcome_details.get('success'):
            worker_measured_qos = action_outcome_details.get('measured_qos_for_requestor', {})
            delegated_load_consumed = worker_measured_qos.get('load_consumed', 0)
        elif action_outcome_details.get('success') and task_type == "PERIODIC_HEALTH_CHECK": 
            delegated_load_consumed = 0 
        elif not final_success_of_composite_task and "delegated_to" in reason_for_composite_outcome:
             worker_measured_qos = action_outcome_details.get('measured_qos_for_requestor', {})
             delegated_load_consumed = worker_measured_qos.get('load_consumed', 0) 

        total_load_consumed_for_task_by_composite_system = composite_coordination_load_cost + delegated_load_consumed

        measured_qos_for_trust_and_requestor = {
            'task_success_binary': 1 if final_success_of_composite_task else 0,
            'response_time_ms': overall_response_time_ms,
            'load_consumed': total_load_consumed_for_task_by_composite_system, 
            'expected_load_for_task': load_requested, 
            'coordination_overhead_ms_measured': action_outcome_details.get('coordination_overhead_ms', self.announced_qos.get('coordination_overhead_ms',30) if final_success_of_composite_task else overall_response_time_ms),
            'delegate_success_rate_measured': 1.0 if final_success_of_composite_task and "delegated_to" in reason_for_composite_outcome else 0.0,
            'sub_task_outcomes_summary': action_outcome_details.get('sub_task_outcomes', [])
        }
        
        if final_success_of_composite_task and "delegated_to" in reason_for_composite_outcome:
            worker_qos = action_outcome_details.get('measured_qos_for_requestor', {})
            if 'processing_time_ms' in worker_qos: 
                 measured_qos_for_trust_and_requestor['worker_processing_time_ms'] = worker_qos.get('processing_time_ms')

        if from_device: 
            self.update_trust_from_qoe(from_device, task_type, measured_qos_for_trust_and_requestor, interaction_role="performer")

        if final_success_of_composite_task:
            if not details.get("delegator_device_id"): 
                self.receive_income(details.get('iot_app_reward', self.base_coordination_reward), f"Coordinated Task '{task_type}' (Job: {self.current_job_id})")
            self.log_info(f"Composite {self.nameShort()} SUCCEEDED managing '{task_type}' (Job: {self.current_job_id}). Reason: {reason_for_composite_outcome}")
        else:
            self.log_warning(f"Composite {self.nameShort()} FAILED to manage '{task_type}' (Job: {self.current_job_id}). Reason: {reason_for_composite_outcome}")
            if self.framework_variant in ["social_basic", "full_siot"] and not details.get('is_backup_attempt'): 
                active_backups = [rel['device'] for rel in self.relationships.get('back_me', []) if rel.get('status')=='active']
                if active_backups:
                    backup_composite_candidate = self.select_worker_for_task(active_backups, f"backup_for_composite_task_{task_type}")
                    if backup_composite_candidate and backup_composite_candidate != from_device and backup_composite_candidate != self:
                        self.log_info(f"Attempting backup for composite task '{task_type}' (Job: {self.current_job_id}) with {backup_composite_candidate.nameShort()}")
                        backup_details = details.copy(); backup_details['is_backup_attempt'] = True
                        backup_details['original_backup_initiator'] = self.device_id 
                        
                        backup_outcome = backup_composite_candidate.handle_request(self, task_type, load_requested, backup_details)
                        
                        if self.framework_variant == "full_siot" and backup_outcome.get('measured_qos_for_requestor'):
                            self.update_trust_from_qoe(backup_composite_candidate, task_type, backup_outcome['measured_qos_for_requestor'], "requester_of_backup")
                        
                        if backup_outcome.get('success'):
                            self.log_info(f"Backup by {backup_composite_candidate.nameShort()} for composite task '{task_type}' (Job: {self.current_job_id}) SUCCEEDED.")
                            if self.sim_metrics_ref and 'back_me_invocations_successful' in self.sim_metrics_ref:
                                self.sim_metrics_ref['back_me_invocations_successful'] +=1
                            
                            final_backup_qos = {
                                **backup_outcome.get('measured_qos_for_requestor', {}), 
                                'task_success_binary': 1,
                                'response_time_ms': (time.time() - request_start_time) * 1000, 
                                'load_consumed': backup_outcome.get('measured_qos_for_requestor',{}).get('load_consumed',0) + composite_coordination_load_cost, 
                                'expected_load_for_task': load_requested
                            }
                            self.current_job_id = None
                            return {**backup_outcome, 
                                    'backed_up_by': backup_composite_candidate.device_id,
                                    'measured_qos_for_requestor': final_backup_qos, 
                                    'request_start_time': request_start_time
                                    }
                        else:
                            if self.sim_metrics_ref and 'back_me_invocations_failed' in self.sim_metrics_ref:
                                self.sim_metrics_ref['back_me_invocations_failed'] +=1
                            self.log_warning(f"Backup by {backup_composite_candidate.nameShort()} for composite task '{task_type}' (Job: {self.current_job_id}) FAILED.")
            
        self.current_job_id = None
        return {'success': final_success_of_composite_task, 
                'reason': reason_for_composite_outcome, 
                'value': action_outcome_details.get('value', action_outcome_details.get('sub_task_outcomes')), 
                'measured_qos_for_requestor': measured_qos_for_trust_and_requestor, 
                'request_start_time': request_start_time}

