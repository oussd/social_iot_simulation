import random
import time
import logging
from enum import Enum
from typing import List, Dict, Any, Optional

class QoELevel(Enum):
    BAD = 0
    FAIR = 1
    GOOD = 2

class Device:
    def __init__(self, device_id: str, name: str, max_load: int = 100,
                 framework_variant: str = "full_siot",
                 capabilities: Optional[List[str]] = None,
                 logger_instance=None,
                 current_minute_provider=None,
                 behavior_profile: str = "normal",
                 fault_probability: float = 0.0,
                 unresponsive_probability: float = 0.0,
                 unresponsive_duration_range: tuple = (3, 10),
                 deception_factor: float = 1.0
                 ):

        self.device_id = device_id
        self.name = name
        self.framework_variant = framework_variant
        self.capabilities = capabilities if capabilities is not None else []
        self.max_load = max_load
        self.current_load = 0
        self.trust_score = 75.0 if framework_variant == "full_siot" else None
        
        self.relationships: Dict[str, List[Dict[str, Any]]] = {
            'work_with_me': [], 'work_for_me': [], 'controller_for': [],
            'back_me': [], 'avoid_me': []
        }
        self.policy = {
            'max_tasks_per_controller': 10,
            'max_load_per_controller': 50,
            'task_timeout': 300,
            'min_trust_for_critical_delegation': 60,
            'max_failed_interactions_before_avoid': 3,
            'negotiation_reject_if_own_load_above_percent': 0.75,
        }
        
        self.behavior_profile = behavior_profile
        self.fault_probability = fault_probability
        self.unresponsive_probability = unresponsive_probability
        self.unresponsive_duration_range = unresponsive_duration_range
        self.is_unresponsive_until: int = 0
        self.deception_factor = deception_factor if self.behavior_profile == 'deceptive' else 1.0
        
        if self.behavior_profile == 'selfish':
            self.policy['selfish_rejection_probability'] = 0.3
            self.policy['selfish_low_backup_priority_factor'] = 0.2

        self.task_log: List[str] = []
        self.misuse_incidents_flagged = 0
        self.blame_count = 0
        
        self.balance = 1000.0
        self.min_acceptable_income_threshold = 50.0
        self.current_period_income = 0.0
        self.total_income_earned = 0.0
        self.total_expenses_paid = 0.0
        self.total_penalties_applied_to_others = 0.0
        self.total_penalties_received = 0.0
        self.task_failure_penalty_value = 15.0
        self.policy_violation_penalty_value = 25.0
        
        base_response_time = float(random.uniform(30, 70))
        base_success_rate = random.uniform(0.90, 0.99)

        if self.behavior_profile == 'deceptive':
            self.announced_qos = {
                'response_time_ms': base_response_time * (self.deception_factor * 0.8),
                'task_success_rate': min(0.999, base_success_rate / (self.deception_factor * 0.9) if self.deception_factor > 0 else 0.999),
                'load_efficiency': random.uniform(0.8, 1.0),
            }
        else:
            self.announced_qos = {
                'response_time_ms': base_response_time,
                'task_success_rate': base_success_rate,
                'load_efficiency': random.uniform(0.9, 1.1),
            }

        self.expected_partner_qos = {
            'response_time_ms': float(random.uniform(40, 80)),
            'task_success_rate': random.uniform(0.85, 0.95),
        }
        self.qoe_thresholds = {
            'response_time_ms': {'sigma': 25.0, 'delta': 15.0},
            'task_success_rate': {'sigma': 0.15, 'delta': 0.10},
            'load_efficiency': {'sigma': 0.25, 'delta': 0.15},
            'negotiation_success_binary': {'sigma': 0.1, 'delta': 0.05},
            'policy_adherence_binary': {'sigma': 0.1, 'delta': 0.05},
            'availability_binary': {'sigma': 0.1, 'delta': 0.05}
        }
        self.interaction_history: List[Dict[str, Any]] = []
        self.max_interaction_history_len = 20
        self.trust_adjustment_factor = 5.0

        if logger_instance:
            self.logger = logger_instance
        else:
            class PrintLogger: # Basic fallback
                def log_info(self, tag, msg, context_override=None): print(f"INFO [{context_override or tag}] {msg}")
                def log_warning(self, tag, msg, context_override=None): print(f"WARN [{context_override or tag}] {msg}")
                def log_error(self, tag, msg, context_override=None): print(f"ERROR [{context_override or tag}] {msg}")
                def log_event(self, tag, msg, level='info', context_override=None):
                    print(f"[{level.upper()}] [{context_override or tag}] {msg}")
            self.logger = PrintLogger()

        self.current_job_id: Optional[str] = None
        self.current_minute_provider = current_minute_provider
        self.sim_metrics_ref: Optional[Dict[str, Any]] = None

    def get_current_minute(self) -> int:
        return self.current_minute_provider() if self.current_minute_provider else int(time.time() // 60)

    # --- New Logging Wrapper Methods ---
    def log_info(self, message: str, context_tag: Optional[str] = None, context_override: Optional[str] = None):
        """Logs an informational message via the main logger."""
        tag = context_tag if context_tag is not None else self.nameShort()
        self.logger.log_info(tag, message, context_override=context_override)

    def log_warning(self, message: str, context_tag: Optional[str] = None, context_override: Optional[str] = None):
        """Logs a warning message via the main logger."""
        tag = context_tag if context_tag is not None else self.nameShort()
        self.logger.log_warning(tag, message, context_override=context_override)

    def log_error(self, message: str, context_tag: Optional[str] = None, context_override: Optional[str] = None):
        """Logs an error message via the main logger."""
        tag = context_tag if context_tag is not None else self.nameShort()
        self.logger.log_error(tag, message, context_override=context_override)

    def log_debug(self, message: str, context_tag: Optional[str] = None, context_override: Optional[str] = None):
        """Logs a debug message via the main logger's log_event."""
        tag = context_tag if context_tag is not None else self.nameShort()
        # SimulationLogger uses log_event for debug level
        self.logger.log_event(tag, message, level='debug', context_override=context_override)
    
    # The old Device.log_event can be removed or kept for internal Device use if preferred,
    # but subclasses should now use log_info, log_warning, etc.
    # For clarity, let's remove the old one if it's not used internally by other base Device methods.
    # (Upon review, no other base Device methods were using self.log_event directly)

    def nameShort(self) -> str:
        class_name = self.__class__.__name__.replace("Device","D").replace("Sensor","Sens").replace("Actuator","Act").replace("Communicating","Comm").replace("Composite","Comp")
        parts = self.device_id.split('_')
        id_part = self.device_id
        for part in reversed(parts):
            if any(char.isdigit() for char in part): id_part = part; break
            elif len(parts) > 1 : id_part = parts[-1]
            else: id_part = self.device_id
        id_part = id_part.replace('bldg','b').replace('lab','l').replace('zc','z').replace('dev','d').replace('cplx','cx').replace('cplx2','c2')
        id_part = id_part.replace('sensor','s').replace('actuator','a').replace('comm','c').replace('composite','co')
        return f"{class_name}({id_part})"

    def receive_income(self, amount: float, source_description: str = ""):
        self.balance += amount; self.total_income_earned += amount; self.current_period_income += amount
        self.log_debug(f"Received income: {amount:.2f} from {source_description}. New balance: {self.balance:.2f}")

    def pay_expense(self, amount: float, recipient_device: Optional['Device'], description: str = "") -> bool:
        if self.balance >= amount:
            self.balance -= amount; self.total_expenses_paid += amount
            if recipient_device: recipient_device.receive_income(amount, f"payment from {self.nameShort()} for {description}")
            self.log_debug(f"Paid expense: {amount:.2f} to {recipient_device.nameShort() if recipient_device else description}. New balance: {self.balance:.2f}")
            return True
        else:
            self.log_warning(f"Failed to pay expense: {amount:.2f} (insufficient balance: {self.balance:.2f})")
            if self.framework_variant == "full_siot" and recipient_device:
                 self.update_trust_from_qoe(recipient_device, "payment_obligation",
                                            {'task_success_binary': 0, 'response_time_ms': 1000}, 
                                            interaction_role="performer_of_payment")
            return False

    def apply_penalty_to_device(self, target_device: 'Device', penalty_amount: float, reason: str = ""):
        self.log_info(f"Applying penalty: {penalty_amount:.2f} to {target_device.nameShort()} for {reason}.")
        target_device.receive_penalty(penalty_amount, self.nameShort(), reason)
        self.total_penalties_applied_to_others += penalty_amount

    def receive_penalty(self, penalty_amount: float, penalized_by: str = "System", reason: str = ""):
        self.balance -= penalty_amount; self.total_penalties_received += penalty_amount
        self.log_warning(f"Received penalty: {penalty_amount:.2f} from {penalized_by} for {reason}. New balance: {self.balance:.2f}")
        if self.framework_variant == "full_siot":
            direct_trust_hit = -10.0 
            self.trust_score = max(0.0, min(100.0, self.trust_score + direct_trust_hit))
            self.log_info(f"Direct trust hit from penalty: {direct_trust_hit:.1f}. New trust: {self.trust_score:.1f}")

    def check_min_income_satisfied(self):
        satisfied = self.current_period_income >= self.min_acceptable_income_threshold
        if not satisfied and self.framework_variant == "full_siot":
            self.log_warning(f"Min income ({self.min_acceptable_income_threshold:.2f}) not met for period (earned: {self.current_period_income:.2f}). Trust may be affected.")
        self.current_period_income = 0
        return satisfied

    def add_relationship(self, relation_type: str, device: 'Device', constraints: Optional[Dict] = None):
        if self.framework_variant == "baseline": return
        if relation_type not in self.relationships: self.relationships[relation_type] = []
        if not any(r['device'] == device for r in self.relationships[relation_type]):
            self.relationships[relation_type].append({
                'device': device, 'constraints': constraints or {},
                'start_time': time.time(), 'status': 'active',
                'interaction_count': 0, 'successful_interactions': 0, 'failed_interactions': 0,
                'consecutive_failures': 0
            })
            self.log_debug(f"Added '{relation_type}' relationship with {device.nameShort()}")

    def avoid(self, device: 'Device'):
        if self.framework_variant == "baseline": return
        if 'avoid_me' not in self.relationships: self.relationships['avoid_me'] = []
        if not any(r['device'] == device for r in self.relationships['avoid_me']):
            self.relationships['avoid_me'].append({'device': device, 'status': 'active', 'start_time': time.time()})
            self.log_info(f"Now AVOIDING device {device.nameShort()}")

    def get_relationship_with(self, partner_device: 'Device', relation_type: Optional[str] = None) -> Optional[Dict]:
        if not partner_device or self.framework_variant == "baseline": return None
        for rel_key_iter, rel_list in self.relationships.items():
            if relation_type and rel_key_iter != relation_type: continue
            for rel_entry in rel_list:
                if rel_entry.get('device') == partner_device:
                    return rel_entry
        return None

    def negotiate_load(self, requested_load: int, from_device: Optional['Device'] = None, task_details: Optional[Dict]=None) -> bool:
        if self.current_load + requested_load > self.max_load:
            return False

        if self.framework_variant == "full_siot" and from_device:
            requester_trust_proxy = getattr(from_device, 'trust_score', 50)
            if requested_load > self.max_load * 0.5 and requester_trust_proxy < self.policy.get('min_trust_for_critical_delegation', 60):
                self.log_debug(f"NEGOTIATION REJECT: Task load {requested_load} too high from partner {from_device.nameShort()} with perceived trust {requester_trust_proxy:.1f}.")
                if self.sim_metrics_ref: self.sim_metrics_ref['failed_negotiations'] = self.sim_metrics_ref.get('failed_negotiations',0) + 1
                return False
            if (self.current_load / self.max_load if self.max_load > 0 else 1.0) > self.policy.get('negotiation_reject_if_own_load_above_percent', 0.75):
                self.log_debug(f"NEGOTIATION REJECT: Own load too high ({self.current_load/self.max_load if self.max_load > 0 else 1.0:.2%}) for task from {from_device.nameShort()}.")
                if self.sim_metrics_ref: self.sim_metrics_ref['failed_negotiations'] = self.sim_metrics_ref.get('failed_negotiations',0) + 1
                return False
            required_capability = (task_details or {}).get('required_capability')
            if required_capability and required_capability not in self.capabilities:
                self.log_debug(f"NEGOTIATION REJECT: Lacking capability '{required_capability}' for task from {from_device.nameShort()}.")
                if self.sim_metrics_ref: self.sim_metrics_ref['failed_negotiations'] = self.sim_metrics_ref.get('failed_negotiations',0) + 1
                return False
            self.log_debug(f"NEGOTIATION ACCEPT: Task from {from_device.nameShort()} accepted under full_siot policies.")
            if self.sim_metrics_ref: self.sim_metrics_ref['successful_negotiations'] = self.sim_metrics_ref.get('successful_negotiations',0) + 1
            return True
        return True

    def consume_load(self, load_amount: int) -> bool:
        if self.current_load + load_amount <= self.max_load:
            self.current_load += load_amount
            return True
        return False

    def reduce_load(self, amount: Optional[int] = None):
        if self.current_load == 0: return
        if amount is None:
            amount = random.randint(max(1,int(self.current_load*0.1)), max(2,int(self.current_load*0.3)))
        self.current_load = max(0, self.current_load - amount)

    def check_policy(self, relation_type_context: str, task_type: str, from_device_partner: Optional['Device'], details: Optional[Dict]=None) -> bool:
        if self.framework_variant == "baseline": return True 
        if not from_device_partner: return True 
        rel_entry = self.get_relationship_with(from_device_partner, relation_type_context)
        if rel_entry:
            constraints = rel_entry.get('constraints', {})
            if task_type in constraints.get('forbidden_tasks', []):
                self.log_warning(f"POLICY VIOLATION with {from_device_partner.nameShort()}: Task '{task_type}' forbidden by relationship constraints.")
                self.blame_count +=1 
                self.receive_penalty(self.policy_violation_penalty_value, "Policy Self-Violation", f"Forbidden Task '{task_type}' with {from_device_partner.nameShort()}")
                return False 
        return True 

    def add_controller(self, controller_device: 'Device', constraints: Optional[Dict] = None) -> bool:
        if self.framework_variant == "baseline":
            self.log_debug(f"Baseline mode: Cannot add {controller_device.nameShort()} as controller for {self.nameShort()}.")
            return False
        if 'work_for_me' not in self.relationships: self.relationships['work_for_me'] = []
        if any(r['device'] == controller_device for r in self.relationships['work_for_me']):
            self.log_debug(f"{controller_device.nameShort()} is already a controller for {self.nameShort()}.")
            return False 
        self.relationships['work_for_me'].append({
            'device': controller_device, 'constraints': constraints or {}, 'start_time': time.time(),
            'status': 'active', 'task_count_from_controller': 0, 'total_load_from_controller': 0, 
            'consecutive_task_failures_for_controller': 0}) 
        self.log_info(f"Added {controller_device.nameShort()} as my controller (I work for them).")
        return True

    def remove_controller(self, controller_device: 'Device'):
        if self.framework_variant == "baseline": return
        if 'work_for_me' in self.relationships:
            initial_len = len(self.relationships['work_for_me'])
            self.relationships['work_for_me'] = [
                r for r in self.relationships['work_for_me'] if r.get('device') != controller_device
            ]
            if len(self.relationships['work_for_me']) < initial_len:
                self.log_info(f"Removed {controller_device.nameShort()} as my controller.")
            else:
                self.log_debug(f"{controller_device.nameShort()} was not found as my controller.")

    def is_authorized_controller(self, device: Optional['Device']) -> bool:
        if self.framework_variant == "baseline" or not device: return False
        return any(r.get('device') == device and r.get('status') == 'active'
                   for r in self.relationships.get('work_for_me', []))

    def check_controller_limits(self, controller_device: 'Device', load_of_this_task: int) -> bool:
        if self.framework_variant == "baseline": return True
        rel_entry = self.get_relationship_with(controller_device, 'work_for_me')
        if not rel_entry:
            self.log_warning(f"No 'work_for_me' relationship found with supposed controller {controller_device.nameShort()}")
            return False
        rel_constraints = rel_entry.get('constraints',{})
        max_tasks = rel_constraints.get('max_tasks_from_controller', self.policy['max_tasks_per_controller'])
        max_load_total = rel_constraints.get('max_load_from_controller', self.policy['max_load_per_controller'])
        current_task_count = rel_entry.get('task_count_from_controller',0)
        current_total_load = rel_entry.get('total_load_from_controller',0)

        if current_task_count >= max_tasks:
            self.log_warning(f"Controller {controller_device.nameShort()} exceeded max tasks policy ({current_task_count}/{max_tasks}). Request rejected.")
            return False
        if current_total_load + load_of_this_task > max_load_total:
            self.log_warning(f"Controller {controller_device.nameShort()} would exceed max load policy with this task ({current_total_load + load_of_this_task}/{max_load_total}). Request rejected.")
            return False
        return True

    def update_controller_metrics(self, controller_device: 'Device', load_of_this_task: int, task_succeeded: bool):
        if self.framework_variant == "baseline": return
        rel_entry = self.get_relationship_with(controller_device, 'work_for_me')
        if rel_entry:
            rel_entry['task_count_from_controller'] = rel_entry.get('task_count_from_controller', 0) + 1
            rel_entry['total_load_from_controller'] = rel_entry.get('total_load_from_controller', 0) + load_of_this_task
            if not task_succeeded:
                rel_entry['consecutive_task_failures_for_controller'] = rel_entry.get('consecutive_task_failures_for_controller',0) + 1
            else:
                rel_entry['consecutive_task_failures_for_controller'] = 0

    def add_worker(self, worker_device: 'Device', constraints: Optional[Dict] = None) -> bool:
        if self.framework_variant == "baseline":
            self.log_debug(f"Baseline mode: {self.nameShort()} cannot add {worker_device.nameShort()} as worker.")
            return False
        if any(r.get('device') == worker_device for r in self.relationships.get('controller_for', [])):
            self.log_debug(f"{worker_device.nameShort()} is already a worker for {self.nameShort()}.")
            return True
        self.add_relationship('controller_for', worker_device, constraints)
        self.log_info(f"Added {worker_device.nameShort()} as a worker under {self.nameShort()}.")
        if hasattr(worker_device, 'add_controller'):
            worker_device.add_controller(self, constraints)
        else:
            self.log_warning(f"Worker {worker_device.nameShort()} does not have add_controller method.")
        return True

    def remove_worker(self, worker_device: 'Device'):
        if self.framework_variant == "baseline":
            self.log_debug(f"Baseline mode: {self.nameShort()} cannot remove {worker_device.nameShort()} as worker.")
            return
        initial_len = len(self.relationships.get('controller_for', []))
        self.relationships['controller_for'] = [
            r for r in self.relationships.get('controller_for', []) if r.get('device') != worker_device
        ]
        if len(self.relationships.get('controller_for', [])) < initial_len:
            self.log_info(f"Removed {worker_device.nameShort()} as a worker from {self.nameShort()}.")
            if hasattr(worker_device, 'remove_controller'):
                worker_device.remove_controller(self)
            else:
                self.log_warning(f"Worker {worker_device.nameShort()} does not have remove_controller method.")
        else:
            self.log_debug(f"{worker_device.nameShort()} was not found as a worker for {self.nameShort()}.")

    def _calculate_qoe_level_for_param(self, qos_param_name: str, announced_val: Optional[float], measured_val: Optional[float]) -> QoELevel:
        if announced_val is None or measured_val is None: return QoELevel.FAIR
        if qos_param_name not in self.qoe_thresholds:
            self.log_debug(f"Warning: QoE thresholds undefined for '{qos_param_name}'. Assuming FAIR.")
            return QoELevel.FAIR
        sigma = self.qoe_thresholds[qos_param_name]['sigma']
        delta = self.qoe_thresholds[qos_param_name]['delta']
        diff = abs(announced_val - measured_val)
        if diff < (sigma - delta): return QoELevel.GOOD
        elif diff < (sigma + delta): return QoELevel.FAIR
        else: return QoELevel.BAD

    def update_trust_from_qoe(self, partner_device: Optional['Device'], task_type: str,
                              measured_qos_params: Dict[str, Any], interaction_role: str):
        if self.framework_variant != "full_siot": return
        qoe_values_for_agg: List[int] = []
        log_qoe_details: List[str] = []
        announced_qos_set = {}
        if interaction_role == "performer": announced_qos_set = self.announced_qos
        elif interaction_role == "requester": announced_qos_set = self.expected_partner_qos
        elif interaction_role == "performer_of_payment": announced_qos_set = {'task_success_rate': 1.0}
        elif interaction_role == "requester_of_good_policy": announced_qos_set = {'policy_adherence_binary': 1.0}
        else: announced_qos_set = self.announced_qos

        if 'task_success_binary' in measured_qos_params:
            announced_val = announced_qos_set.get('task_success_rate', 1.0)
            qoe = self._calculate_qoe_level_for_param('task_success_rate', announced_val, measured_qos_params['task_success_binary'])
            qoe_values_for_agg.append(qoe.value)
            log_qoe_details.append(f"SR:{qoe.name[0]}(E:{announced_val*100:.0f}A:{measured_qos_params['task_success_binary']*100:.0f})")
        if 'response_time_ms' in measured_qos_params:
            announced_val = announced_qos_set.get('response_time_ms')
            if announced_val is not None:
                qoe = self._calculate_qoe_level_for_param('response_time_ms', announced_val, measured_qos_params['response_time_ms'])
                qoe_values_for_agg.append(qoe.value)
                log_qoe_details.append(f"RT:{qoe.name[0]}(E:{announced_val:.0f}A:{measured_qos_params['response_time_ms']:.0f})")
        if interaction_role == "performer" and 'load_consumed' in measured_qos_params and 'expected_load_for_task' in measured_qos_params:
            announced_val = announced_qos_set.get('load_efficiency', 1.0)
            expected_load = measured_qos_params.get('expected_load_for_task', 1.0)
            actual_load = measured_qos_params['load_consumed']
            measured_eff = actual_load / expected_load if expected_load > 0 else 1.0
            qoe = self._calculate_qoe_level_for_param('load_efficiency', announced_val, measured_eff)
            qoe_values_for_agg.append(qoe.value)
            log_qoe_details.append(f"LE:{qoe.name[0]}(E:{announced_val:.1f}A:{measured_eff:.1f})")
        if 'policy_adherence_binary' in measured_qos_params:
            announced_val = announced_qos_set.get('policy_adherence_binary', 1.0)
            qoe = self._calculate_qoe_level_for_param('policy_adherence_binary', announced_val, measured_qos_params['policy_adherence_binary'])
            qoe_values_for_agg.append(qoe.value)
            log_qoe_details.append(f"PA:{qoe.name[0]}")
        if 'negotiation_success_binary' in measured_qos_params:
            announced_val = announced_qos_set.get('negotiation_success_binary', 1.0)
            qoe = self._calculate_qoe_level_for_param('negotiation_success_binary', announced_val, measured_qos_params['negotiation_success_binary'])
            qoe_values_for_agg.append(qoe.value)
            log_qoe_details.append(f"Neg:{qoe.name[0]}")
        if 'availability_binary' in measured_qos_params:
            announced_val = 1.0
            qoe = self._calculate_qoe_level_for_param('availability_binary', announced_val, measured_qos_params['availability_binary'])
            qoe_values_for_agg.append(qoe.value)
            log_qoe_details.append(f"Avail:{qoe.name[0]}")

        if not qoe_values_for_agg: return
        avg_qoe_numeric = sum(qoe_values_for_agg) / len(qoe_values_for_agg)
        delta_trust = (avg_qoe_numeric - QoELevel.FAIR.value) * self.trust_adjustment_factor
        delta_trust_multiplier = 1.0
        if partner_device:
            rel_to_update_type = None
            if interaction_role == "performer":
                if self.is_authorized_controller(partner_device): rel_to_update_type = 'work_for_me'
                else: rel_to_update_type = 'work_with_me'
            elif interaction_role == "requester":
                if any(r.get('device') == partner_device for r in self.relationships.get('controller_for',[])):
                     rel_to_update_type = 'controller_for'
                else: rel_to_update_type = 'work_with_me'
            rel_entry = self.get_relationship_with(partner_device, rel_to_update_type) if rel_to_update_type else self.get_relationship_with(partner_device)
            if rel_entry:
                rel_entry['interaction_count'] = rel_entry.get('interaction_count',0) + 1
                if avg_qoe_numeric >= QoELevel.FAIR.value :
                    rel_entry['successful_interactions'] = rel_entry.get('successful_interactions',0) + 1
                    rel_entry['consecutive_failures'] = 0
                else:
                    rel_entry['failed_interactions'] = rel_entry.get('failed_interactions',0) + 1
                    rel_entry['consecutive_failures'] = rel_entry.get('consecutive_failures',0) + 1
                if rel_entry['consecutive_failures'] >= self.policy.get('max_failed_interactions_before_avoid',3):
                    self.log_warning(f"MISUSE ALERT: Partner {partner_device.nameShort()} has {rel_entry['consecutive_failures']} consecutive failures. Harsher trust penalty. Consider avoiding.")
                    delta_trust_multiplier = 2.0
                    self.misuse_incidents_flagged += 1
                    if self.sim_metrics_ref and 'misuse_incidents_detected' in self.sim_metrics_ref:
                        self.sim_metrics_ref['misuse_incidents_detected'] += 1
        if delta_trust < 0: delta_trust *= delta_trust_multiplier
        self.trust_score = max(0.0, min(100.0, self.trust_score + delta_trust))
        partner_name_log = partner_device.nameShort() if partner_device else "Self/System"
        self.log_debug(f"QoE ({interaction_role} for '{task_type}' with {partner_name_log}): "
                       f"{', '.join(log_qoe_details) if log_qoe_details else 'NoQoSDetails'}. AvgQoE:{avg_qoe_numeric:.2f}. dT:{delta_trust:.1f}. "
                       f"New Trust for {self.nameShort()}:{self.trust_score:.1f}")
        interaction_record = {
            'partner_id': partner_device.device_id if partner_device else None,
            'partner_name': partner_name_log, 
            'task_type': task_type, 'role': interaction_role, 'measured_qos': measured_qos_params,
            'avg_qoe_calculated_value': avg_qoe_numeric,
            'delta_trust_calculated': delta_trust,
            'timestamp': self.get_current_minute() }
        self.interaction_history.append(interaction_record)
        if len(self.interaction_history) > self.max_interaction_history_len: self.interaction_history.pop(0)

    def handle_request(self, from_device: Optional['Device'], task_type: str,
                       load_requested: int = 10, details: Optional[Dict] = None) -> Dict[str, Any]:
        details = details if details is not None else {}
        request_start_time = time.time()
        measured_qos_for_requestor = {'task_success_binary': 0, 'response_time_ms': 0.0, 'expected_load_for_task': load_requested}

        current_sim_minute = self.get_current_minute()
        if self.is_unresponsive_until > current_sim_minute:
            self.log_info(f"Device is unresponsive until minute {self.is_unresponsive_until}. Rejecting request.")
            measured_qos_for_requestor['response_time_ms'] = (time.time() - request_start_time) * 1000
            measured_qos_for_requestor['availability_binary'] = 0
            if self.sim_metrics_ref: self.sim_metrics_ref['unresponsive_device_rejections'] = self.sim_metrics_ref.get('unresponsive_device_rejections',0) + 1
            return {'success': False, 'reason': 'device_unresponsive', 'measured_qos_for_requestor': measured_qos_for_requestor, 'request_start_time': request_start_time}

        if random.random() < self.unresponsive_probability:
            duration = random.randint(*self.unresponsive_duration_range)
            self.is_unresponsive_until = current_sim_minute + duration
            self.log_info(f"Becoming unresponsive for {duration} minutes (until minute {self.is_unresponsive_until}).")
            measured_qos_for_requestor['response_time_ms'] = (time.time() - request_start_time) * 1000
            measured_qos_for_requestor['availability_binary'] = 0
            if self.sim_metrics_ref: self.sim_metrics_ref['unresponsive_device_rejections'] = self.sim_metrics_ref.get('unresponsive_device_rejections',0) + 1
            return {'success': False, 'reason': 'device_became_unresponsive', 'measured_qos_for_requestor': measured_qos_for_requestor, 'request_start_time': request_start_time}

        if self.behavior_profile == 'selfish' and random.random() < self.policy.get('selfish_rejection_probability', 0.0):
            self.log_info(f"Selfishly rejecting request for '{task_type}' from {from_device.nameShort() if from_device else 'N/A'}.")
            measured_qos_for_requestor['response_time_ms'] = (time.time() - request_start_time) * 1000
            measured_qos_for_requestor['negotiation_success_binary'] = 0 
            if self.sim_metrics_ref: 
                self.sim_metrics_ref['failed_negotiations'] = self.sim_metrics_ref.get('failed_negotiations',0) + 1
                self.sim_metrics_ref['selfish_rejections'] = self.sim_metrics_ref.get('selfish_rejections',0) + 1
            return {'success': False, 'reason': 'selfishly_rejected_request', 'measured_qos_for_requestor': measured_qos_for_requestor, 'request_start_time': request_start_time}
        
        if self.framework_variant != "baseline" and from_device and \
           any(r.get('device') == from_device for r in self.relationships.get('avoid_me', [])):
            self.log_info(f"Rejected (AVOIDED) request for '{task_type}' from {from_device.nameShort()}")
            measured_qos_for_requestor['response_time_ms'] = (time.time() - request_start_time) * 1000
            return {'success': False, 'reason': 'avoided_device', 'measured_qos_for_requestor': measured_qos_for_requestor, 'request_start_time': request_start_time}

        if self.framework_variant != "baseline" and from_device and self.is_authorized_controller(from_device):
            if not self.check_controller_limits(from_device, load_requested):
                measured_qos_for_requestor['response_time_ms'] = (time.time() - request_start_time) * 1000
                measured_qos_for_requestor['policy_adherence_binary'] = 0
                self.update_trust_from_qoe(from_device, "controller_limit_check_by_worker",
                                           {'task_success_binary': 0, 'policy_adherence_binary': 0},
                                           interaction_role="requester_of_good_policy")
                return {'success': False, 'reason': 'controller_limits_exceeded', 'measured_qos_for_requestor': measured_qos_for_requestor, 'request_start_time': request_start_time}
        
        if self.framework_variant != "baseline" and from_device:
            relation_type_context = 'work_for_me' if self.is_authorized_controller(from_device) else 'work_with_me'
            if not self.check_policy(relation_type_context, task_type, from_device, details):
                measured_qos_for_requestor['response_time_ms'] = (time.time() - request_start_time) * 1000
                measured_qos_for_requestor['policy_adherence_binary'] = 0
                self.update_trust_from_qoe(from_device, task_type,
                                           {'task_success_binary': 0, 'policy_adherence_binary':0},
                                           interaction_role="performer")
                return {'success': False, 'reason': 'policy_violation_by_self_to_partner', 'measured_qos_for_requestor': measured_qos_for_requestor, 'request_start_time': request_start_time}

        can_take_task = self.negotiate_load(load_requested, from_device, details)
        negotiation_qos_param = {}
        if self.framework_variant == "full_siot" and from_device :
            negotiation_qos_param = {'negotiation_success_binary': 1 if can_take_task else 0}

        if not can_take_task:
            reason = 'negotiation_failed' if self.framework_variant == "full_siot" and from_device else 'overload'
            self.log_info(f"Rejected ({reason.upper()}) for '{task_type}' from {from_device.nameShort() if from_device else 'N/A'}")
            measured_qos_for_requestor['response_time_ms'] = (time.time() - request_start_time) * 1000
            measured_qos_for_requestor.update(negotiation_qos_param)
            self.update_trust_from_qoe(from_device, task_type,
                                       {**measured_qos_for_requestor, 'task_success_binary': 0, 'availability_binary': 0},
                                       interaction_role="performer")
            return {'success': False, 'reason': reason, 'measured_qos_for_requestor': measured_qos_for_requestor, 'request_start_time': request_start_time}

        self.log_debug(f"Provisionally accepted task '{task_type}' from {from_device.nameShort() if from_device else 'N/A'} (load_req: {load_requested})")
        
        return {'success': True, 'reason': 'accepted_by_base_checks',
                'request_start_time': request_start_time,
                'negotiation_qos': negotiation_qos_param}

    def report_status(self):
        trust_str = f"Trust:{self.trust_score:.1f}" if self.framework_variant == "full_siot" else "Trust:N/A"
        load_str = f"Load:{self.current_load}/{self.max_load}"
        bal_str = f"Bal:{self.balance:.0f}"
        profile_str = f"Profile:{self.behavior_profile}" if self.behavior_profile != "normal" else ""
        unresp_str = f"UnrespUntil:{self.is_unresponsive_until}" if self.is_unresponsive_until > self.get_current_minute() else ""
        rels_summary = []
        if self.framework_variant != "baseline":
            for k,v_list in self.relationships.items():
                if v_list:
                    active_count = sum(1 for r_entry in v_list if r_entry.get('status') == 'active')
                    if active_count > 0:
                        key_short = k.split('_')[0][:2] if '_' in k else k[:2]
                        if k == "controller_for": key_short = "cf"
                        elif k == "work_for_me": key_short = "wf"
                        rels_summary.append(f"{key_short}:{active_count}")
        rel_str = f"Rel:[{','.join(rels_summary)}]" if rels_summary else ""
        status_parts = [part for part in [trust_str, bal_str, load_str, profile_str, unresp_str, rel_str] if part]
        self.log_info(f"STATUS: {' '.join(status_parts)}", context_tag=self.nameShort())

    def select_worker_for_task(self, worker_list: List['Device'], task_description: str) -> Optional['Device']:
        if not worker_list: return None
        if self.framework_variant == "baseline":
            return random.choice(worker_list)
        else:
            available_workers = [
                w for w in worker_list
                if w.current_load < w.max_load * 0.85 and
                not any(r.get('device') == w for r in self.relationships.get('avoid_me',[])) and
                w.is_unresponsive_until <= self.get_current_minute()
            ]
            if not available_workers:
                self.log_debug(f"No available (non-overloaded/non-avoided/responsive) workers for task '{task_description}' among {len(worker_list)} candidates.")
                return None
            if self.framework_variant == "full_siot":
                sorted_workers = sorted(available_workers, key=lambda w: (getattr(w, 'trust_score', 0), -w.current_load), reverse=True)
            else:
                sorted_workers = sorted(available_workers, key=lambda w: -w.current_load, reverse=True)
            selected_worker = sorted_workers[0]
            if self.framework_variant == "full_siot" and selected_worker.trust_score is not None:
                trust_str = f"{selected_worker.trust_score:.1f}"
            else:
                trust_str = "N/A"
            self.log_debug(f"Selected worker {selected_worker.nameShort()} (Trust: {trust_str}, Load: {selected_worker.current_load}) for '{task_description}'.")
            return selected_worker
