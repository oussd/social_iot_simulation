# src/devices/device.py

import random
import time
from typing import List, Dict, Any, Optional, Callable, TYPE_CHECKING
from enum import Enum

if TYPE_CHECKING:
    from ..utils.logger import SimulationLogger # Forward declaration for type hinting

# --- QoE Level Enum & Policy Definitions (can be expanded) ---
class QoELevel(Enum):
    EXCELLENT = (0.9, 1.0)
    GOOD = (0.7, 0.89)
    FAIR = (0.5, 0.69)
    POOR = (0.3, 0.49)
    UNACCEPTABLE = (0.0, 0.29)

DEFAULT_POLICY_STORE = {
    "default_task_policy": {
        "id": "default_task_policy",
        "rules": {
            "max_response_time_ms": 500, # ms
            "min_success_rate": 0.90, # binary tasks
            "min_data_accuracy": 0.85, # for sensing tasks
            "max_load_contribution_percent": 0.75 # Max load device will take for one task relative to its max_load
        }
    },
    "hvac_backup_policy_v1": {
        "id": "hvac_backup_policy_v1",
        "description": "Policy for HVAC devices backing each other up.",
        "rules": {
            "max_backup_response_time_ms": 1000,
            "backup_priority_threshold": 0.6 # Min trust to be considered for backup
        }
    },
    "server_collaboration_policy_v1": {
        "id": "server_collaboration_policy_v1",
        "description": "Policy for ZoneServers collaborating on tasks.",
        "rules": {
            "max_delegated_task_time_ms": 2000,
            "min_trust_for_delegation": 0.5
        }
    }
    # Add more predefined policies here
}


class Device:
    def __init__(self, device_id: str, name: str, max_load: int = 100,
                 framework_variant: str = "full_siot",
                 capabilities: Optional[List[str]] = None,
                 logger_instance: Optional['SimulationLogger'] = None,
                 current_minute_provider: Optional[Callable[[], int]] = None,
                 behavior_profile: str = "normal", # normal, selfish, faulty, deceptive, policy_violator
                 fault_probability: float = 0.01, # Base probability of a fault per action
                 deception_factor: float = 1.0 # Multiplier for QoS deception (e.g., >1 looks better than it is)
                 ):
        self.device_id = device_id
        self.name = name
        self.nameShort = lambda: f"{self.__class__.__name__[0]}D({self.name.split('_')[-1] if '_' in self.name else self.name})" # Short name for logging
        
        self.max_load = max_load
        self.current_load = 0
        self.framework_variant = framework_variant
        self.capabilities = capabilities if capabilities is not None else ["basic_operation"]
        self.status = "active"  # active, inactive, faulty
        self.current_job_id: Optional[str] = None


        self.logger = logger_instance
        self.current_minute_provider = current_minute_provider

        self.behavior_profile = behavior_profile
        self.fault_probability = fault_probability if behavior_profile != 'faulty' else 0.25 # Higher for faulty
        self.deception_factor = deception_factor if behavior_profile == 'deceptive' else 1.0
        if self.behavior_profile == 'deceptive' and self.deception_factor == 1.0:
            self.deception_factor = random.uniform(1.5, 2.5) # Default deception if not specified

        # Social aspects
        self.trust_scores: Dict[str, float] = {}  # device_id -> trust_score (0.0 to 1.0)
        self.relationships: Dict[str, List[Dict[str, Any]]] = {
            "work-with-me": [], 
            "work-for-me": [],  
            "controller_for": [],
            "back-me": [],      
            "avoid-me": []      
        }
        self.policy: Dict[str, Any] = DEFAULT_POLICY_STORE.get("default_task_policy", {}) 
        
        # Financials / Rewards
        self.balance = 100.0 
        self.base_task_reward = 5.0 
        self.task_failure_penalty_value = 2.0
        self.total_income_earned = 0.0
        self.total_penalties_received = 0.0
        self.total_expenses_paid = 0.0

        # QoS / QoE
        self.announced_qos: Dict[str, Any] = {'response_time_ms': random.uniform(10,100), 'task_success_rate': random.uniform(0.9,0.99), 'load_efficiency': 1.0}
        self.qoe_thresholds: Dict[str, Dict[str, float]] = {
            'response_time_ms': {'sigma': 50.0, 'delta': 20.0}, 
            'task_success_rate': {'sigma': 0.1, 'delta': 0.05},  
            'load_efficiency': {'sigma': 0.2, 'delta': 0.1}     
        }
        self.sim_metrics_ref: Optional[Dict[str, Any]] = None 

        if self.behavior_profile == 'deceptive':
            self.announced_qos['response_time_ms'] = max(5, self.announced_qos['response_time_ms'] / self.deception_factor)
            self.announced_qos['task_success_rate'] = min(0.999, self.announced_qos['task_success_rate'] * self.deception_factor)
        elif self.behavior_profile == 'faulty':
            self.announced_qos['task_success_rate'] *= 0.8 


    def log_debug(self, message: str, context_override: Optional[str] = None):
        if self.logger: self.logger.log_debug(context_override or self.nameShort(), message)
    def log_info(self, message: str, context_override: Optional[str] = None):
        if self.logger: self.logger.log_info(context_override or self.nameShort(), message)
    def log_warning(self, message: str, context_override: Optional[str] = None):
        if self.logger: self.logger.log_warning(context_override or self.nameShort(), message)
    def log_error(self, message: str, context_override: Optional[str] = None):
        if self.logger: self.logger.log_error(context_override or self.nameShort(), message)
    def log_event(self, tag: str, message: str, level: str = "info", context_override: Optional[str] = None):
        if self.logger: self.logger.log_event(tag, message, level, context_override or self.nameShort())

    def get_current_minute(self) -> int:
        return self.current_minute_provider() if self.current_minute_provider else 0

    def consume_load(self, load_amount: int) -> bool:
        if self.current_load + load_amount <= self.max_load:
            self.current_load += load_amount
            return True
        self.log_warning(f"Cannot consume load {load_amount}. Overload: {self.current_load}/{self.max_load}")
        return False

    def reduce_load(self, amount_to_reduce: Optional[int] = None):
        if amount_to_reduce is None:
            amount_to_reduce = max(1, int(self.current_load * 0.1)) 
        
        self.current_load = max(0, self.current_load - amount_to_reduce)

    def add_relationship(self, other_device: 'Device', relationship_type: str,
                         initial_trust: float = 0.5, status: str = 'active',
                         policy: Optional[Any] = None): # 'policy' is the expected keyword
        if relationship_type not in self.relationships:
            self.relationships[relationship_type] = []
        
        for rel in self.relationships[relationship_type]:
            if rel['device'].device_id == other_device.device_id:
                return

        new_relationship_entry = {
            'device': other_device,
            'type': relationship_type, 
            'trust_score': initial_trust,
            'interactions': 0,
            'successful_interactions': 0,
            'failed_interactions': 0,
            'status': status, 
            'history': [], 
            'policy': policy # Store the policy (which might be a string ID or a dict)
        }
        self.relationships[relationship_type].append(new_relationship_entry)
        self.log_info(f"Established relationship: {self.nameShort()} --{relationship_type}--> {other_device.nameShort()} (Policy: {str(policy)[:30] if policy else 'None'})")


    def update_trust_from_qoe(self, target_device: Optional['Device'], task_type: str, 
                              measured_qos: Dict[str, Any], interaction_role: str):
        if not target_device or self.framework_variant == "baseline":
            return

        current_trust = self.trust_scores.get(target_device.device_id, 0.5) 
        task_successful = measured_qos.get('task_success_binary', 0) == 1
        alpha = self.policy.get('trust_learning_rate', 0.1)

        if task_successful:
            current_trust += alpha * (1.0 - current_trust) 
        else:
            current_trust -= alpha * current_trust         
        
        self.trust_scores[target_device.device_id] = max(0.0, min(1.0, current_trust))
        
        for rel_list in self.relationships.values():
            for rel in rel_list:
                if rel['device'].device_id == target_device.device_id:
                    rel['trust_score'] = self.trust_scores[target_device.device_id]
                    rel['interactions'] = rel.get('interactions', 0) + 1
                    if task_successful:
                        rel['successful_interactions'] = rel.get('successful_interactions', 0) + 1
                    else:
                        rel['failed_interactions'] = rel.get('failed_interactions', 0) + 1
                    rel.get('history', []).append({
                        'minute': self.get_current_minute(),
                        'task_type': task_type,
                        'qos_observed': measured_qos,
                        'role': interaction_role,
                        'new_trust': rel['trust_score']
                    })
                    if len(rel.get('history',[])) > 20: rel['history'].pop(0) 
                    break 
        
        self.log_debug(f"Updated trust for {target_device.nameShort()} to {self.trust_scores[target_device.device_id]:.2f} after task '{task_type}' (Success: {task_successful})")

    def negotiate_load(self, from_device: Optional['Device'], task_type: str, load_requested: int, details: Dict) -> bool:
        if self.status != "active":
            self.log_warning(f"Cannot accept task '{task_type}', device status is '{self.status}'.")
            if self.sim_metrics_ref: self.sim_metrics_ref['unresponsive_device_rejections'] = self.sim_metrics_ref.get('unresponsive_device_rejections',0) + 1
            return False

        max_acceptable_load_for_task = self.max_load * self.policy.get('task_acceptance_max_load_threshold', 0.95)

        if self.current_load + load_requested > self.max_load:
            self.log_warning(f"Rejected task '{task_type}' from {from_device.nameShort() if from_device else 'N/A'} due to OVERLOAD. Requested: {load_requested}, Current: {self.current_load}, Max: {self.max_load}")
            if self.sim_metrics_ref: self.sim_metrics_ref['unresponsive_device_rejections'] = self.sim_metrics_ref.get('unresponsive_device_rejections',0) + 1
            return False
        
        if load_requested > max_acceptable_load_for_task :
            self.log_warning(f"Rejected task '{task_type}' from {from_device.nameShort() if from_device else 'N/A'} as requested load {load_requested} exceeds task threshold {max_acceptable_load_for_task}.")
            return False

        if self.behavior_profile == 'selfish' and self.framework_variant != "baseline":
            task_reward = details.get('iot_app_reward', self.base_task_reward) 
            selfish_threshold = self.policy.get('selfish_rejection_threshold', 0.3) 
            if (task_reward / load_requested if load_requested > 0 else task_reward) < (self.base_task_reward / 10 * selfish_threshold) : 
                 if random.random() < self.policy.get('selfish_rejection_probability', 0.5):
                    self.log_info(f"Selfish device {self.nameShort()} REJECTING task '{task_type}' (low reward/load ratio).")
                    if self.sim_metrics_ref: self.sim_metrics_ref['selfish_rejections'] = self.sim_metrics_ref.get('selfish_rejections',0) + 1
                    return False
        
        return True 

    def handle_request(self, from_device: Optional['Device'], task_type: str,
                       load_requested: int = 10, details: Optional[Dict] = None) -> Dict[str, Any]:
        request_start_time = time.time()
        details = details if details is not None else {}
        
        self.log_debug(f"Received task '{task_type}' from {from_device.nameShort() if from_device else 'environment/self'} with load {load_requested}. Current load: {self.current_load}")

        if not self.negotiate_load(from_device, task_type, load_requested, details):
            overall_response_time_ms = (time.time() - request_start_time) * 1000
            measured_qos = {'task_success_binary': 0, 'response_time_ms': overall_response_time_ms, 'expected_load_for_task': load_requested}
            return {'success': False, 'reason': 'rejected_by_load_negotiation', 
                    'measured_qos_for_requestor': measured_qos, 'request_start_time': request_start_time}
        
        action_result: Dict[str, Any] = {}
        if task_type == "PERIODIC_HEALTH_CHECK" or task_type == "basic_operation":
            load_cost = max(1, int(load_requested * 0.5)) 
            if self.consume_load(load_cost):
                time.sleep(0.001) 
                action_result = {'success': True, 'value': 'OK', 'load_consumed': load_cost, 'processing_time_ms': (time.time() - request_start_time)*1000}
                self.log_debug(f"Performed generic task '{task_type}'.")
            else:
                action_result = {'success': False, 'reason': 'overload_at_action', 'load_consumed': 0}
        else:
            self.log_warning(f"Rejected: Base device {self.nameShort()} cannot directly handle specialized task type '{task_type}'. Subclass should implement.")
            action_result = {'success': False, 'reason': 'unsupported_task_type_by_base_device'}

        overall_response_time_ms = (time.time() - request_start_time) * 1000
        measured_qos_for_trust_and_requestor = {
            'task_success_binary': 1 if action_result.get('success') else 0,
            'response_time_ms': overall_response_time_ms,
            'load_consumed': action_result.get('load_consumed', 0),
            'expected_load_for_task': load_requested,
            'processing_time_ms': action_result.get('processing_time_ms', overall_response_time_ms),
        }
        if 'data_accuracy_measured' in action_result: measured_qos_for_trust_and_requestor['data_accuracy_measured'] = action_result['data_accuracy_measured']
        if 'state_changed_correctly_binary' in action_result: measured_qos_for_trust_and_requestor['state_changed_correctly_binary'] = action_result['state_changed_correctly_binary']
        if 'message_delivered_binary' in action_result: measured_qos_for_trust_and_requestor['message_delivered_binary'] = action_result['message_delivered_binary']

        self.update_trust_from_qoe(from_device, task_type, measured_qos_for_trust_and_requestor, interaction_role="performer")
        
        if action_result.get('success'):
            self.receive_income(details.get('iot_app_reward', self.base_task_reward), f"{task_type} completion")
            return {'success': True, 'reason': f'{task_type}_successful_base', 'value': action_result.get('value'),
                    'measured_qos_for_requestor': measured_qos_for_trust_and_requestor, 'request_start_time': request_start_time}
        else:
            return {'success': False, 'reason': action_result.get('reason', 'base_device_task_failed'),
                    'measured_qos_for_requestor': measured_qos_for_trust_and_requestor, 'request_start_time': request_start_time}

    def receive_income(self, amount: float, reason: str):
        self.balance += amount
        self.total_income_earned += amount
        self.log_debug(f"Received income: {amount:.2f} for {reason}. New balance: {self.balance:.2f}")

    def pay_expense(self, amount: float, recipient: Optional['Device'], reason: str):
        if self.balance >= amount:
            self.balance -= amount
            self.total_expenses_paid += amount
            if recipient: recipient.receive_income(amount, f"Payment from {self.nameShort()} for {reason}")
            self.log_debug(f"Paid expense: {amount:.2f} to {recipient.nameShort() if recipient else 'N/A'} for {reason}. New balance: {self.balance:.2f}")
            return True
        else:
            self.log_warning(f"Insufficient funds to pay expense: {amount:.2f} for {reason}. Balance: {self.balance:.2f}")
            return False

    def apply_penalty_to_device(self, target_device: 'Device', penalty_amount: float, reason: str):
        if hasattr(target_device, 'receive_penalty'):
            target_device.receive_penalty(penalty_amount, reason, self)
            self.log_info(f"Applied penalty of {penalty_amount:.2f} to {target_device.nameShort()} for: {reason}")

    def receive_penalty(self, amount: float, reason: str, from_device: Optional['Device']):
        self.balance -= amount
        self.total_penalties_received += amount
        self.log_warning(f"Received penalty: {amount:.2f} from {from_device.nameShort() if from_device else 'System'} for {reason}. New balance: {self.balance:.2f}")
        if from_device and self.framework_variant == "full_siot":
            current_trust = self.trust_scores.get(from_device.device_id, 0.5)
            updated_trust = max(0, current_trust - (amount / self.base_task_reward) * 0.5 ) 
            self.trust_scores[from_device.device_id] = updated_trust
            self.log_info(f"Trust towards {from_device.nameShort()} reduced to {updated_trust:.2f} due to penalty.")

    def report_status(self):
        self.log_info(f"Status - Load: {self.current_load}/{self.max_load}, Balance: {self.balance:.2f}, Trust Scores: {self.trust_scores}")


# import random
# import time
# import logging
# from enum import Enum
# from typing import List, Dict, Any, Optional

# class QoELevel(Enum):
#     BAD = 0
#     FAIR = 1
#     GOOD = 2

# class Device:
#     def __init__(self, device_id: str, name: str, max_load: int = 100,
#                  framework_variant: str = "full_siot",
#                  capabilities: Optional[List[str]] = None,
#                  logger_instance=None,
#                  current_minute_provider=None,
#                  behavior_profile: str = "normal",
#                  fault_probability: float = 0.0,
#                  unresponsive_probability: float = 0.0,
#                  unresponsive_duration_range: tuple = (3, 10),
#                  deception_factor: float = 1.0
#                  ):

#         self.device_id = device_id
#         self.name = name
#         self.framework_variant = framework_variant
#         self.capabilities = capabilities if capabilities is not None else []
#         self.max_load = max_load
#         self.current_load = 0
#         self.trust_score = 75.0 if framework_variant == "full_siot" else None
        
#         self.relationships: Dict[str, List[Dict[str, Any]]] = {
#             'work_with_me': [], 'work_for_me': [], 'controller_for': [],
#             'back_me': [], 'avoid_me': []
#         }
#         self.policy = {
#             'max_tasks_per_controller': 10,
#             'max_load_per_controller': 50,
#             'task_timeout': 300,
#             'min_trust_for_critical_delegation': 60,
#             'max_failed_interactions_before_avoid': 3,
#             'negotiation_reject_if_own_load_above_percent': 0.75,
#         }
        
#         self.behavior_profile = behavior_profile
#         self.fault_probability = fault_probability
#         self.unresponsive_probability = unresponsive_probability
#         self.unresponsive_duration_range = unresponsive_duration_range
#         self.is_unresponsive_until: int = 0
#         self.deception_factor = deception_factor if self.behavior_profile == 'deceptive' else 1.0
        
#         if self.behavior_profile == 'selfish':
#             self.policy['selfish_rejection_probability'] = 0.3
#             self.policy['selfish_low_backup_priority_factor'] = 0.2

#         self.task_log: List[str] = []
#         self.misuse_incidents_flagged = 0
#         self.blame_count = 0
        
#         self.balance = 1000.0
#         self.min_acceptable_income_threshold = 50.0
#         self.current_period_income = 0.0
#         self.total_income_earned = 0.0
#         self.total_expenses_paid = 0.0
#         self.total_penalties_applied_to_others = 0.0
#         self.total_penalties_received = 0.0
#         self.task_failure_penalty_value = 15.0
#         self.policy_violation_penalty_value = 25.0
        
#         base_response_time = float(random.uniform(30, 70))
#         base_success_rate = random.uniform(0.90, 0.99)

#         if self.behavior_profile == 'deceptive':
#             self.announced_qos = {
#                 'response_time_ms': base_response_time * (self.deception_factor * 0.8),
#                 'task_success_rate': min(0.999, base_success_rate / (self.deception_factor * 0.9) if self.deception_factor > 0 else 0.999),
#                 'load_efficiency': random.uniform(0.8, 1.0),
#             }
#         else:
#             self.announced_qos = {
#                 'response_time_ms': base_response_time,
#                 'task_success_rate': base_success_rate,
#                 'load_efficiency': random.uniform(0.9, 1.1),
#             }

#         self.expected_partner_qos = {
#             'response_time_ms': float(random.uniform(40, 80)),
#             'task_success_rate': random.uniform(0.85, 0.95),
#         }
#         self.qoe_thresholds = {
#             'response_time_ms': {'sigma': 25.0, 'delta': 15.0},
#             'task_success_rate': {'sigma': 0.15, 'delta': 0.10},
#             'load_efficiency': {'sigma': 0.25, 'delta': 0.15},
#             'negotiation_success_binary': {'sigma': 0.1, 'delta': 0.05},
#             'policy_adherence_binary': {'sigma': 0.1, 'delta': 0.05},
#             'availability_binary': {'sigma': 0.1, 'delta': 0.05}
#         }
#         self.interaction_history: List[Dict[str, Any]] = []
#         self.max_interaction_history_len = 20
#         self.trust_adjustment_factor = 5.0

#         if logger_instance:
#             self.logger = logger_instance
#         else:
#             class PrintLogger: # Basic fallback
#                 def log_info(self, tag, msg, context_override=None): print(f"INFO [{context_override or tag}] {msg}")
#                 def log_warning(self, tag, msg, context_override=None): print(f"WARN [{context_override or tag}] {msg}")
#                 def log_error(self, tag, msg, context_override=None): print(f"ERROR [{context_override or tag}] {msg}")
#                 def log_event(self, tag, msg, level='info', context_override=None):
#                     print(f"[{level.upper()}] [{context_override or tag}] {msg}")
#             self.logger = PrintLogger()

#         self.current_job_id: Optional[str] = None
#         self.current_minute_provider = current_minute_provider
#         self.sim_metrics_ref: Optional[Dict[str, Any]] = None

#     def get_current_minute(self) -> int:
#         return self.current_minute_provider() if self.current_minute_provider else int(time.time() // 60)

#     # --- New Logging Wrapper Methods ---
#     def log_info(self, message: str, context_tag: Optional[str] = None, context_override: Optional[str] = None):
#         """Logs an informational message via the main logger."""
#         tag = context_tag if context_tag is not None else self.nameShort()
#         self.logger.log_info(tag, message, context_override=context_override)

#     def log_warning(self, message: str, context_tag: Optional[str] = None, context_override: Optional[str] = None):
#         """Logs a warning message via the main logger."""
#         tag = context_tag if context_tag is not None else self.nameShort()
#         self.logger.log_warning(tag, message, context_override=context_override)

#     def log_error(self, message: str, context_tag: Optional[str] = None, context_override: Optional[str] = None):
#         """Logs an error message via the main logger."""
#         tag = context_tag if context_tag is not None else self.nameShort()
#         self.logger.log_error(tag, message, context_override=context_override)

#     def log_debug(self, message: str, context_tag: Optional[str] = None, context_override: Optional[str] = None):
#         """Logs a debug message via the main logger's log_event."""
#         tag = context_tag if context_tag is not None else self.nameShort()
#         # SimulationLogger uses log_event for debug level
#         self.logger.log_event(tag, message, level='debug', context_override=context_override)
    
#     # The old Device.log_event can be removed or kept for internal Device use if preferred,
#     # but subclasses should now use log_info, log_warning, etc.
#     # For clarity, let's remove the old one if it's not used internally by other base Device methods.
#     # (Upon review, no other base Device methods were using self.log_event directly)

#     def nameShort(self) -> str:
#         class_name = self.__class__.__name__.replace("Device","D").replace("Sensor","Sens").replace("Actuator","Act").replace("Communicating","Comm").replace("Composite","Comp")
#         parts = self.device_id.split('_')
#         id_part = self.device_id
#         for part in reversed(parts):
#             if any(char.isdigit() for char in part): id_part = part; break
#             elif len(parts) > 1 : id_part = parts[-1]
#             else: id_part = self.device_id
#         id_part = id_part.replace('bldg','b').replace('lab','l').replace('zc','z').replace('dev','d').replace('cplx','cx').replace('cplx2','c2')
#         id_part = id_part.replace('sensor','s').replace('actuator','a').replace('comm','c').replace('composite','co')
#         return f"{class_name}({id_part})"

#     def receive_income(self, amount: float, source_description: str = ""):
#         self.balance += amount; self.total_income_earned += amount; self.current_period_income += amount
#         self.log_debug(f"Received income: {amount:.2f} from {source_description}. New balance: {self.balance:.2f}")

#     def pay_expense(self, amount: float, recipient_device: Optional['Device'], description: str = "") -> bool:
#         if self.balance >= amount:
#             self.balance -= amount; self.total_expenses_paid += amount
#             if recipient_device: recipient_device.receive_income(amount, f"payment from {self.nameShort()} for {description}")
#             self.log_debug(f"Paid expense: {amount:.2f} to {recipient_device.nameShort() if recipient_device else description}. New balance: {self.balance:.2f}")
#             return True
#         else:
#             self.log_warning(f"Failed to pay expense: {amount:.2f} (insufficient balance: {self.balance:.2f})")
#             if self.framework_variant == "full_siot" and recipient_device:
#                  self.update_trust_from_qoe(recipient_device, "payment_obligation",
#                                             {'task_success_binary': 0, 'response_time_ms': 1000}, 
#                                             interaction_role="performer_of_payment")
#             return False

#     def apply_penalty_to_device(self, target_device: 'Device', penalty_amount: float, reason: str = ""):
#         self.log_info(f"Applying penalty: {penalty_amount:.2f} to {target_device.nameShort()} for {reason}.")
#         target_device.receive_penalty(penalty_amount, self.nameShort(), reason)
#         self.total_penalties_applied_to_others += penalty_amount

#     def receive_penalty(self, penalty_amount: float, penalized_by: str = "System", reason: str = ""):
#         self.balance -= penalty_amount; self.total_penalties_received += penalty_amount
#         self.log_warning(f"Received penalty: {penalty_amount:.2f} from {penalized_by} for {reason}. New balance: {self.balance:.2f}")
#         if self.framework_variant == "full_siot":
#             direct_trust_hit = -10.0 
#             self.trust_score = max(0.0, min(100.0, self.trust_score + direct_trust_hit))
#             self.log_info(f"Direct trust hit from penalty: {direct_trust_hit:.1f}. New trust: {self.trust_score:.1f}")

#     def check_min_income_satisfied(self):
#         satisfied = self.current_period_income >= self.min_acceptable_income_threshold
#         if not satisfied and self.framework_variant == "full_siot":
#             self.log_warning(f"Min income ({self.min_acceptable_income_threshold:.2f}) not met for period (earned: {self.current_period_income:.2f}). Trust may be affected.")
#         self.current_period_income = 0
#         return satisfied

#     def add_relationship(self, relation_type: str, device: 'Device', constraints: Optional[Dict] = None):
#         if self.framework_variant == "baseline": return
#         if relation_type not in self.relationships: self.relationships[relation_type] = []
#         if not any(r['device'] == device for r in self.relationships[relation_type]):
#             self.relationships[relation_type].append({
#                 'device': device, 'constraints': constraints or {},
#                 'start_time': time.time(), 'status': 'active',
#                 'interaction_count': 0, 'successful_interactions': 0, 'failed_interactions': 0,
#                 'consecutive_failures': 0
#             })
#             self.log_debug(f"Added '{relation_type}' relationship with {device.nameShort()}")

#     def avoid(self, device: 'Device'):
#         if self.framework_variant == "baseline": return
#         if 'avoid_me' not in self.relationships: self.relationships['avoid_me'] = []
#         if not any(r['device'] == device for r in self.relationships['avoid_me']):
#             self.relationships['avoid_me'].append({'device': device, 'status': 'active', 'start_time': time.time()})
#             self.log_info(f"Now AVOIDING device {device.nameShort()}")

#     def get_relationship_with(self, partner_device: 'Device', relation_type: Optional[str] = None) -> Optional[Dict]:
#         if not partner_device or self.framework_variant == "baseline": return None
#         for rel_key_iter, rel_list in self.relationships.items():
#             if relation_type and rel_key_iter != relation_type: continue
#             for rel_entry in rel_list:
#                 if rel_entry.get('device') == partner_device:
#                     return rel_entry
#         return None

#     def negotiate_load(self, requested_load: int, from_device: Optional['Device'] = None, task_details: Optional[Dict]=None) -> bool:
#         if self.current_load + requested_load > self.max_load:
#             return False

#         if self.framework_variant == "full_siot" and from_device:
#             requester_trust_proxy = getattr(from_device, 'trust_score', 50)
#             if requested_load > self.max_load * 0.5 and requester_trust_proxy < self.policy.get('min_trust_for_critical_delegation', 60):
#                 self.log_debug(f"NEGOTIATION REJECT: Task load {requested_load} too high from partner {from_device.nameShort()} with perceived trust {requester_trust_proxy:.1f}.")
#                 if self.sim_metrics_ref: self.sim_metrics_ref['failed_negotiations'] = self.sim_metrics_ref.get('failed_negotiations',0) + 1
#                 return False
#             if (self.current_load / self.max_load if self.max_load > 0 else 1.0) > self.policy.get('negotiation_reject_if_own_load_above_percent', 0.75):
#                 self.log_debug(f"NEGOTIATION REJECT: Own load too high ({self.current_load/self.max_load if self.max_load > 0 else 1.0:.2%}) for task from {from_device.nameShort()}.")
#                 if self.sim_metrics_ref: self.sim_metrics_ref['failed_negotiations'] = self.sim_metrics_ref.get('failed_negotiations',0) + 1
#                 return False
#             required_capability = (task_details or {}).get('required_capability')
#             if required_capability and required_capability not in self.capabilities:
#                 self.log_debug(f"NEGOTIATION REJECT: Lacking capability '{required_capability}' for task from {from_device.nameShort()}.")
#                 if self.sim_metrics_ref: self.sim_metrics_ref['failed_negotiations'] = self.sim_metrics_ref.get('failed_negotiations',0) + 1
#                 return False
#             self.log_debug(f"NEGOTIATION ACCEPT: Task from {from_device.nameShort()} accepted under full_siot policies.")
#             if self.sim_metrics_ref: self.sim_metrics_ref['successful_negotiations'] = self.sim_metrics_ref.get('successful_negotiations',0) + 1
#             return True
#         return True

#     def consume_load(self, load_amount: int) -> bool:
#         if self.current_load + load_amount <= self.max_load:
#             self.current_load += load_amount
#             return True
#         return False

#     def reduce_load(self, amount: Optional[int] = None):
#         if self.current_load == 0: return
#         if amount is None:
#             amount = random.randint(max(1,int(self.current_load*0.1)), max(2,int(self.current_load*0.3)))
#         self.current_load = max(0, self.current_load - amount)

#     def check_policy(self, relation_type_context: str, task_type: str, from_device_partner: Optional['Device'], details: Optional[Dict]=None) -> bool:
#         if self.framework_variant == "baseline": return True 
#         if not from_device_partner: return True 
#         rel_entry = self.get_relationship_with(from_device_partner, relation_type_context)
#         if rel_entry:
#             constraints = rel_entry.get('constraints', {})
#             if task_type in constraints.get('forbidden_tasks', []):
#                 self.log_warning(f"POLICY VIOLATION with {from_device_partner.nameShort()}: Task '{task_type}' forbidden by relationship constraints.")
#                 self.blame_count +=1 
#                 self.receive_penalty(self.policy_violation_penalty_value, "Policy Self-Violation", f"Forbidden Task '{task_type}' with {from_device_partner.nameShort()}")
#                 return False 
#         return True 

#     def add_controller(self, controller_device: 'Device', constraints: Optional[Dict] = None) -> bool:
#         if self.framework_variant == "baseline":
#             self.log_debug(f"Baseline mode: Cannot add {controller_device.nameShort()} as controller for {self.nameShort()}.")
#             return False
#         if 'work_for_me' not in self.relationships: self.relationships['work_for_me'] = []
#         if any(r['device'] == controller_device for r in self.relationships['work_for_me']):
#             self.log_debug(f"{controller_device.nameShort()} is already a controller for {self.nameShort()}.")
#             return False 
#         self.relationships['work_for_me'].append({
#             'device': controller_device, 'constraints': constraints or {}, 'start_time': time.time(),
#             'status': 'active', 'task_count_from_controller': 0, 'total_load_from_controller': 0, 
#             'consecutive_task_failures_for_controller': 0}) 
#         self.log_info(f"Added {controller_device.nameShort()} as my controller (I work for them).")
#         return True

#     def remove_controller(self, controller_device: 'Device'):
#         if self.framework_variant == "baseline": return
#         if 'work_for_me' in self.relationships:
#             initial_len = len(self.relationships['work_for_me'])
#             self.relationships['work_for_me'] = [
#                 r for r in self.relationships['work_for_me'] if r.get('device') != controller_device
#             ]
#             if len(self.relationships['work_for_me']) < initial_len:
#                 self.log_info(f"Removed {controller_device.nameShort()} as my controller.")
#             else:
#                 self.log_debug(f"{controller_device.nameShort()} was not found as my controller.")

#     def is_authorized_controller(self, device: Optional['Device']) -> bool:
#         if self.framework_variant == "baseline" or not device: return False
#         return any(r.get('device') == device and r.get('status') == 'active'
#                    for r in self.relationships.get('work_for_me', []))

#     def check_controller_limits(self, controller_device: 'Device', load_of_this_task: int) -> bool:
#         if self.framework_variant == "baseline": return True
#         rel_entry = self.get_relationship_with(controller_device, 'work_for_me')
#         if not rel_entry:
#             self.log_warning(f"No 'work_for_me' relationship found with supposed controller {controller_device.nameShort()}")
#             return False
#         rel_constraints = rel_entry.get('constraints',{})
#         max_tasks = rel_constraints.get('max_tasks_from_controller', self.policy['max_tasks_per_controller'])
#         max_load_total = rel_constraints.get('max_load_from_controller', self.policy['max_load_per_controller'])
#         current_task_count = rel_entry.get('task_count_from_controller',0)
#         current_total_load = rel_entry.get('total_load_from_controller',0)

#         if current_task_count >= max_tasks:
#             self.log_warning(f"Controller {controller_device.nameShort()} exceeded max tasks policy ({current_task_count}/{max_tasks}). Request rejected.")
#             return False
#         if current_total_load + load_of_this_task > max_load_total:
#             self.log_warning(f"Controller {controller_device.nameShort()} would exceed max load policy with this task ({current_total_load + load_of_this_task}/{max_load_total}). Request rejected.")
#             return False
#         return True

#     def update_controller_metrics(self, controller_device: 'Device', load_of_this_task: int, task_succeeded: bool):
#         if self.framework_variant == "baseline": return
#         rel_entry = self.get_relationship_with(controller_device, 'work_for_me')
#         if rel_entry:
#             rel_entry['task_count_from_controller'] = rel_entry.get('task_count_from_controller', 0) + 1
#             rel_entry['total_load_from_controller'] = rel_entry.get('total_load_from_controller', 0) + load_of_this_task
#             if not task_succeeded:
#                 rel_entry['consecutive_task_failures_for_controller'] = rel_entry.get('consecutive_task_failures_for_controller',0) + 1
#             else:
#                 rel_entry['consecutive_task_failures_for_controller'] = 0

#     def add_worker(self, worker_device: 'Device', constraints: Optional[Dict] = None) -> bool:
#         if self.framework_variant == "baseline":
#             self.log_debug(f"Baseline mode: {self.nameShort()} cannot add {worker_device.nameShort()} as worker.")
#             return False
#         if any(r.get('device') == worker_device for r in self.relationships.get('controller_for', [])):
#             self.log_debug(f"{worker_device.nameShort()} is already a worker for {self.nameShort()}.")
#             return True
#         self.add_relationship('controller_for', worker_device, constraints)
#         self.log_info(f"Added {worker_device.nameShort()} as a worker under {self.nameShort()}.")
#         if hasattr(worker_device, 'add_controller'):
#             worker_device.add_controller(self, constraints)
#         else:
#             self.log_warning(f"Worker {worker_device.nameShort()} does not have add_controller method.")
#         return True

#     def remove_worker(self, worker_device: 'Device'):
#         if self.framework_variant == "baseline":
#             self.log_debug(f"Baseline mode: {self.nameShort()} cannot remove {worker_device.nameShort()} as worker.")
#             return
#         initial_len = len(self.relationships.get('controller_for', []))
#         self.relationships['controller_for'] = [
#             r for r in self.relationships.get('controller_for', []) if r.get('device') != worker_device
#         ]
#         if len(self.relationships.get('controller_for', [])) < initial_len:
#             self.log_info(f"Removed {worker_device.nameShort()} as a worker from {self.nameShort()}.")
#             if hasattr(worker_device, 'remove_controller'):
#                 worker_device.remove_controller(self)
#             else:
#                 self.log_warning(f"Worker {worker_device.nameShort()} does not have remove_controller method.")
#         else:
#             self.log_debug(f"{worker_device.nameShort()} was not found as a worker for {self.nameShort()}.")

#     def _calculate_qoe_level_for_param(self, qos_param_name: str, announced_val: Optional[float], measured_val: Optional[float]) -> QoELevel:
#         if announced_val is None or measured_val is None: return QoELevel.FAIR
#         if qos_param_name not in self.qoe_thresholds:
#             self.log_debug(f"Warning: QoE thresholds undefined for '{qos_param_name}'. Assuming FAIR.")
#             return QoELevel.FAIR
#         sigma = self.qoe_thresholds[qos_param_name]['sigma']
#         delta = self.qoe_thresholds[qos_param_name]['delta']
#         diff = abs(announced_val - measured_val)
#         if diff < (sigma - delta): return QoELevel.GOOD
#         elif diff < (sigma + delta): return QoELevel.FAIR
#         else: return QoELevel.BAD

#     def update_trust_from_qoe(self, partner_device: Optional['Device'], task_type: str,
#                               measured_qos_params: Dict[str, Any], interaction_role: str):
#         if self.framework_variant != "full_siot": return
#         qoe_values_for_agg: List[int] = []
#         log_qoe_details: List[str] = []
#         announced_qos_set = {}
#         if interaction_role == "performer": announced_qos_set = self.announced_qos
#         elif interaction_role == "requester": announced_qos_set = self.expected_partner_qos
#         elif interaction_role == "performer_of_payment": announced_qos_set = {'task_success_rate': 1.0}
#         elif interaction_role == "requester_of_good_policy": announced_qos_set = {'policy_adherence_binary': 1.0}
#         else: announced_qos_set = self.announced_qos

#         if 'task_success_binary' in measured_qos_params:
#             announced_val = announced_qos_set.get('task_success_rate', 1.0)
#             qoe = self._calculate_qoe_level_for_param('task_success_rate', announced_val, measured_qos_params['task_success_binary'])
#             qoe_values_for_agg.append(qoe.value)
#             log_qoe_details.append(f"SR:{qoe.name[0]}(E:{announced_val*100:.0f}A:{measured_qos_params['task_success_binary']*100:.0f})")
#         if 'response_time_ms' in measured_qos_params:
#             announced_val = announced_qos_set.get('response_time_ms')
#             if announced_val is not None:
#                 qoe = self._calculate_qoe_level_for_param('response_time_ms', announced_val, measured_qos_params['response_time_ms'])
#                 qoe_values_for_agg.append(qoe.value)
#                 log_qoe_details.append(f"RT:{qoe.name[0]}(E:{announced_val:.0f}A:{measured_qos_params['response_time_ms']:.0f})")
#         if interaction_role == "performer" and 'load_consumed' in measured_qos_params and 'expected_load_for_task' in measured_qos_params:
#             announced_val = announced_qos_set.get('load_efficiency', 1.0)
#             expected_load = measured_qos_params.get('expected_load_for_task', 1.0)
#             actual_load = measured_qos_params['load_consumed']
#             measured_eff = actual_load / expected_load if expected_load > 0 else 1.0
#             qoe = self._calculate_qoe_level_for_param('load_efficiency', announced_val, measured_eff)
#             qoe_values_for_agg.append(qoe.value)
#             log_qoe_details.append(f"LE:{qoe.name[0]}(E:{announced_val:.1f}A:{measured_eff:.1f})")
#         if 'policy_adherence_binary' in measured_qos_params:
#             announced_val = announced_qos_set.get('policy_adherence_binary', 1.0)
#             qoe = self._calculate_qoe_level_for_param('policy_adherence_binary', announced_val, measured_qos_params['policy_adherence_binary'])
#             qoe_values_for_agg.append(qoe.value)
#             log_qoe_details.append(f"PA:{qoe.name[0]}")
#         if 'negotiation_success_binary' in measured_qos_params:
#             announced_val = announced_qos_set.get('negotiation_success_binary', 1.0)
#             qoe = self._calculate_qoe_level_for_param('negotiation_success_binary', announced_val, measured_qos_params['negotiation_success_binary'])
#             qoe_values_for_agg.append(qoe.value)
#             log_qoe_details.append(f"Neg:{qoe.name[0]}")
#         if 'availability_binary' in measured_qos_params:
#             announced_val = 1.0
#             qoe = self._calculate_qoe_level_for_param('availability_binary', announced_val, measured_qos_params['availability_binary'])
#             qoe_values_for_agg.append(qoe.value)
#             log_qoe_details.append(f"Avail:{qoe.name[0]}")

#         if not qoe_values_for_agg: return
#         avg_qoe_numeric = sum(qoe_values_for_agg) / len(qoe_values_for_agg)
#         delta_trust = (avg_qoe_numeric - QoELevel.FAIR.value) * self.trust_adjustment_factor
#         delta_trust_multiplier = 1.0
#         if partner_device:
#             rel_to_update_type = None
#             if interaction_role == "performer":
#                 if self.is_authorized_controller(partner_device): rel_to_update_type = 'work_for_me'
#                 else: rel_to_update_type = 'work_with_me'
#             elif interaction_role == "requester":
#                 if any(r.get('device') == partner_device for r in self.relationships.get('controller_for',[])):
#                      rel_to_update_type = 'controller_for'
#                 else: rel_to_update_type = 'work_with_me'
#             rel_entry = self.get_relationship_with(partner_device, rel_to_update_type) if rel_to_update_type else self.get_relationship_with(partner_device)
#             if rel_entry:
#                 rel_entry['interaction_count'] = rel_entry.get('interaction_count',0) + 1
#                 if avg_qoe_numeric >= QoELevel.FAIR.value :
#                     rel_entry['successful_interactions'] = rel_entry.get('successful_interactions',0) + 1
#                     rel_entry['consecutive_failures'] = 0
#                 else:
#                     rel_entry['failed_interactions'] = rel_entry.get('failed_interactions',0) + 1
#                     rel_entry['consecutive_failures'] = rel_entry.get('consecutive_failures',0) + 1
#                 if rel_entry['consecutive_failures'] >= self.policy.get('max_failed_interactions_before_avoid',3):
#                     self.log_warning(f"MISUSE ALERT: Partner {partner_device.nameShort()} has {rel_entry['consecutive_failures']} consecutive failures. Harsher trust penalty. Consider avoiding.")
#                     delta_trust_multiplier = 2.0
#                     self.misuse_incidents_flagged += 1
#                     if self.sim_metrics_ref and 'misuse_incidents_detected' in self.sim_metrics_ref:
#                         self.sim_metrics_ref['misuse_incidents_detected'] += 1
#         if delta_trust < 0: delta_trust *= delta_trust_multiplier
#         self.trust_score = max(0.0, min(100.0, self.trust_score + delta_trust))
#         partner_name_log = partner_device.nameShort() if partner_device else "Self/System"
#         self.log_debug(f"QoE ({interaction_role} for '{task_type}' with {partner_name_log}): "
#                        f"{', '.join(log_qoe_details) if log_qoe_details else 'NoQoSDetails'}. AvgQoE:{avg_qoe_numeric:.2f}. dT:{delta_trust:.1f}. "
#                        f"New Trust for {self.nameShort()}:{self.trust_score:.1f}")
#         interaction_record = {
#             'partner_id': partner_device.device_id if partner_device else None,
#             'partner_name': partner_name_log, 
#             'task_type': task_type, 'role': interaction_role, 'measured_qos': measured_qos_params,
#             'avg_qoe_calculated_value': avg_qoe_numeric,
#             'delta_trust_calculated': delta_trust,
#             'timestamp': self.get_current_minute() }
#         self.interaction_history.append(interaction_record)
#         if len(self.interaction_history) > self.max_interaction_history_len: self.interaction_history.pop(0)

#     def handle_request(self, from_device: Optional['Device'], task_type: str,
#                        load_requested: int = 10, details: Optional[Dict] = None) -> Dict[str, Any]:
#         details = details if details is not None else {}
#         request_start_time = time.time()
#         measured_qos_for_requestor = {'task_success_binary': 0, 'response_time_ms': 0.0, 'expected_load_for_task': load_requested}

#         current_sim_minute = self.get_current_minute()
#         if self.is_unresponsive_until > current_sim_minute:
#             self.log_info(f"Device is unresponsive until minute {self.is_unresponsive_until}. Rejecting request.")
#             measured_qos_for_requestor['response_time_ms'] = (time.time() - request_start_time) * 1000
#             measured_qos_for_requestor['availability_binary'] = 0
#             if self.sim_metrics_ref: self.sim_metrics_ref['unresponsive_device_rejections'] = self.sim_metrics_ref.get('unresponsive_device_rejections',0) + 1
#             return {'success': False, 'reason': 'device_unresponsive', 'measured_qos_for_requestor': measured_qos_for_requestor, 'request_start_time': request_start_time}

#         if random.random() < self.unresponsive_probability:
#             duration = random.randint(*self.unresponsive_duration_range)
#             self.is_unresponsive_until = current_sim_minute + duration
#             self.log_info(f"Becoming unresponsive for {duration} minutes (until minute {self.is_unresponsive_until}).")
#             measured_qos_for_requestor['response_time_ms'] = (time.time() - request_start_time) * 1000
#             measured_qos_for_requestor['availability_binary'] = 0
#             if self.sim_metrics_ref: self.sim_metrics_ref['unresponsive_device_rejections'] = self.sim_metrics_ref.get('unresponsive_device_rejections',0) + 1
#             return {'success': False, 'reason': 'device_became_unresponsive', 'measured_qos_for_requestor': measured_qos_for_requestor, 'request_start_time': request_start_time}

#         if self.behavior_profile == 'selfish' and random.random() < self.policy.get('selfish_rejection_probability', 0.0):
#             self.log_info(f"Selfishly rejecting request for '{task_type}' from {from_device.nameShort() if from_device else 'N/A'}.")
#             measured_qos_for_requestor['response_time_ms'] = (time.time() - request_start_time) * 1000
#             measured_qos_for_requestor['negotiation_success_binary'] = 0 
#             if self.sim_metrics_ref: 
#                 self.sim_metrics_ref['failed_negotiations'] = self.sim_metrics_ref.get('failed_negotiations',0) + 1
#                 self.sim_metrics_ref['selfish_rejections'] = self.sim_metrics_ref.get('selfish_rejections',0) + 1
#             return {'success': False, 'reason': 'selfishly_rejected_request', 'measured_qos_for_requestor': measured_qos_for_requestor, 'request_start_time': request_start_time}
        
#         if self.framework_variant != "baseline" and from_device and \
#            any(r.get('device') == from_device for r in self.relationships.get('avoid_me', [])):
#             self.log_info(f"Rejected (AVOIDED) request for '{task_type}' from {from_device.nameShort()}")
#             measured_qos_for_requestor['response_time_ms'] = (time.time() - request_start_time) * 1000
#             return {'success': False, 'reason': 'avoided_device', 'measured_qos_for_requestor': measured_qos_for_requestor, 'request_start_time': request_start_time}

#         if self.framework_variant != "baseline" and from_device and self.is_authorized_controller(from_device):
#             if not self.check_controller_limits(from_device, load_requested):
#                 measured_qos_for_requestor['response_time_ms'] = (time.time() - request_start_time) * 1000
#                 measured_qos_for_requestor['policy_adherence_binary'] = 0
#                 self.update_trust_from_qoe(from_device, "controller_limit_check_by_worker",
#                                            {'task_success_binary': 0, 'policy_adherence_binary': 0},
#                                            interaction_role="requester_of_good_policy")
#                 return {'success': False, 'reason': 'controller_limits_exceeded', 'measured_qos_for_requestor': measured_qos_for_requestor, 'request_start_time': request_start_time}
        
#         if self.framework_variant != "baseline" and from_device:
#             relation_type_context = 'work_for_me' if self.is_authorized_controller(from_device) else 'work_with_me'
#             if not self.check_policy(relation_type_context, task_type, from_device, details):
#                 measured_qos_for_requestor['response_time_ms'] = (time.time() - request_start_time) * 1000
#                 measured_qos_for_requestor['policy_adherence_binary'] = 0
#                 self.update_trust_from_qoe(from_device, task_type,
#                                            {'task_success_binary': 0, 'policy_adherence_binary':0},
#                                            interaction_role="performer")
#                 return {'success': False, 'reason': 'policy_violation_by_self_to_partner', 'measured_qos_for_requestor': measured_qos_for_requestor, 'request_start_time': request_start_time}

#         can_take_task = self.negotiate_load(load_requested, from_device, details)
#         negotiation_qos_param = {}
#         if self.framework_variant == "full_siot" and from_device :
#             negotiation_qos_param = {'negotiation_success_binary': 1 if can_take_task else 0}

#         if not can_take_task:
#             reason = 'negotiation_failed' if self.framework_variant == "full_siot" and from_device else 'overload'
#             self.log_info(f"Rejected ({reason.upper()}) for '{task_type}' from {from_device.nameShort() if from_device else 'N/A'}")
#             measured_qos_for_requestor['response_time_ms'] = (time.time() - request_start_time) * 1000
#             measured_qos_for_requestor.update(negotiation_qos_param)
#             self.update_trust_from_qoe(from_device, task_type,
#                                        {**measured_qos_for_requestor, 'task_success_binary': 0, 'availability_binary': 0},
#                                        interaction_role="performer")
#             return {'success': False, 'reason': reason, 'measured_qos_for_requestor': measured_qos_for_requestor, 'request_start_time': request_start_time}

#         self.log_debug(f"Provisionally accepted task '{task_type}' from {from_device.nameShort() if from_device else 'N/A'} (load_req: {load_requested})")
        
#         return {'success': True, 'reason': 'accepted_by_base_checks',
#                 'request_start_time': request_start_time,
#                 'negotiation_qos': negotiation_qos_param}

#     def report_status(self):
#         trust_str = f"Trust:{self.trust_score:.1f}" if self.framework_variant == "full_siot" else "Trust:N/A"
#         load_str = f"Load:{self.current_load}/{self.max_load}"
#         bal_str = f"Bal:{self.balance:.0f}"
#         profile_str = f"Profile:{self.behavior_profile}" if self.behavior_profile != "normal" else ""
#         unresp_str = f"UnrespUntil:{self.is_unresponsive_until}" if self.is_unresponsive_until > self.get_current_minute() else ""
#         rels_summary = []
#         if self.framework_variant != "baseline":
#             for k,v_list in self.relationships.items():
#                 if v_list:
#                     active_count = sum(1 for r_entry in v_list if r_entry.get('status') == 'active')
#                     if active_count > 0:
#                         key_short = k.split('_')[0][:2] if '_' in k else k[:2]
#                         if k == "controller_for": key_short = "cf"
#                         elif k == "work_for_me": key_short = "wf"
#                         rels_summary.append(f"{key_short}:{active_count}")
#         rel_str = f"Rel:[{','.join(rels_summary)}]" if rels_summary else ""
#         status_parts = [part for part in [trust_str, bal_str, load_str, profile_str, unresp_str, rel_str] if part]
#         self.log_info(f"STATUS: {' '.join(status_parts)}", context_tag=self.nameShort())

#     def select_worker_for_task(self, worker_list: List['Device'], task_description: str) -> Optional['Device']:
#         if not worker_list: return None
#         if self.framework_variant == "baseline":
#             return random.choice(worker_list)
#         else:
#             available_workers = [
#                 w for w in worker_list
#                 if w.current_load < w.max_load * 0.85 and
#                 not any(r.get('device') == w for r in self.relationships.get('avoid_me',[])) and
#                 w.is_unresponsive_until <= self.get_current_minute()
#             ]
#             if not available_workers:
#                 self.log_debug(f"No available (non-overloaded/non-avoided/responsive) workers for task '{task_description}' among {len(worker_list)} candidates.")
#                 return None
#             if self.framework_variant == "full_siot":
#                 sorted_workers = sorted(available_workers, key=lambda w: (getattr(w, 'trust_score', 0), -w.current_load), reverse=True)
#             else:
#                 sorted_workers = sorted(available_workers, key=lambda w: -w.current_load, reverse=True)
#             selected_worker = sorted_workers[0]
#             if self.framework_variant == "full_siot" and selected_worker.trust_score is not None:
#                 trust_str = f"{selected_worker.trust_score:.1f}"
#             else:
#                 trust_str = "N/A"
#             self.log_debug(f"Selected worker {selected_worker.nameShort()} (Trust: {trust_str}, Load: {selected_worker.current_load}) for '{task_description}'.")
#             return selected_worker

#     def _generate_temperature_reading(self, zone_id: str, timestamp: int) -> float:
#         """Generate a realistic temperature reading based on time and conditions."""
#         zone = next(z for z in self.zones if z.zone_id == zone_id)
#         base_temp = zone.base_temperature

#         # Peak at noon, lowest at midnight
#         hour = (timestamp // 60) % 24
#         time_variation = self.environmental_config.temperature_variation_per_hour * (hour - 12) / 12

#         # Add random variation
#         random_variation = random.uniform(-0.5, 0.5)

#         # Check for window open events affecting temperature
#         window_effect = 0
#         for event in self.generated_events:
#             if (event["type"] == "window_opened" and 
#                 event["zone_id"] == zone_id and 
#                 timestamp - event["timestamp"] < event["duration_minutes"]):
#                 window_effect = self.environmental_config.window_effect_on_temperature
#                 break

#         return base_temp + time_variation + random_variation + window_effect
