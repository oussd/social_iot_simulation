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
        # Lambda for a shorter name, useful in logs. Extracts the last part of the name if underscore-separated.
        self.nameShort = lambda: f"{self.__class__.__name__[0]}D({self.name.split('_')[-1] if '_' in self.name else self.name})" 
        
        self.max_load = max_load
        self.current_load = 0
        self.framework_variant = framework_variant # Influences behavior (baseline, social_basic, full_siot)
        self.capabilities = capabilities if capabilities is not None else ["basic_operation"]
        self.status = "active"  # Possible statuses: active, inactive, faulty
        self.current_job_id: Optional[str] = None # ID of the job currently being processed


        self.logger = logger_instance # Instance of SimulationLogger for logging events
        self.current_minute_provider = current_minute_provider # Callable to get current simulation time

        # Behavioral profile attributes
        self.behavior_profile = behavior_profile
        self.fault_probability = fault_probability if behavior_profile != 'faulty' else 0.25 # Higher fault prob for 'faulty' profile
        self.deception_factor = deception_factor if behavior_profile == 'deceptive' else 1.0
        if self.behavior_profile == 'deceptive' and self.deception_factor == 1.0:
            self.deception_factor = random.uniform(1.5, 2.5) # Default deception if not specified for deceptive profile

        # Social aspects: trust scores and relationships with other devices
        self.trust_scores: Dict[str, float] = {}  # device_id -> trust_score (0.0 to 1.0)
        self.relationships: Dict[str, List[Dict[str, Any]]] = {
            "work-with-me": [], 
            "work-for-me": [],  
            "controller_for": [], # Devices this device controls (it works for them)
            "back-me": [],      
            "avoid-me": []      
        }
        self.policy: Dict[str, Any] = DEFAULT_POLICY_STORE.get("default_task_policy", {}) # Current operational policy
        
        # Financials / Rewards system
        self.balance = 100.0 # Starting balance
        self.base_task_reward = 5.0 # Default reward for a generic task
        self.task_failure_penalty_value = 2.0 # Penalty for failing a task
        self.total_income_earned = 0.0
        self.total_penalties_received = 0.0
        self.total_expenses_paid = 0.0

        # QoS / QoE parameters
        # Announced QoS: what the device claims its performance is
        self.announced_qos: Dict[str, Any] = {'response_time_ms': random.uniform(10,100), 'task_success_rate': random.uniform(0.9,0.99), 'load_efficiency': 1.0}
        # QoE thresholds: used to evaluate observed performance against announced QoS
        self.qoe_thresholds: Dict[str, Dict[str, float]] = {
            'response_time_ms': {'sigma': 50.0, 'delta': 20.0}, 
            'task_success_rate': {'sigma': 0.1, 'delta': 0.05},  
            'load_efficiency': {'sigma': 0.2, 'delta': 0.1}     
        }
        self.sim_metrics_ref: Optional[Dict[str, Any]] = None # Reference to global simulation metrics for updates

        # Adjust announced QoS based on behavior profile
        if self.behavior_profile == 'deceptive':
            self.announced_qos['response_time_ms'] = max(5, self.announced_qos['response_time_ms'] / self.deception_factor)
            self.announced_qos['task_success_rate'] = min(0.999, self.announced_qos['task_success_rate'] * self.deception_factor)
        elif self.behavior_profile == 'faulty':
            self.announced_qos['task_success_rate'] *= 0.8 # Faulty devices have lower actual success rate


    # --- Logging Helper Methods ---
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
        """Returns the current simulation minute."""
        return self.current_minute_provider() if self.current_minute_provider else 0

    # --- Load Management ---
    def consume_load(self, load_amount: int) -> bool:
        """Attempts to consume a given amount of load. Returns True if successful."""
        if self.current_load + load_amount <= self.max_load:
            self.current_load += load_amount
            return True
        self.log_warning(f"Cannot consume load {load_amount}. Overload: {self.current_load}/{self.max_load}")
        return False

    def reduce_load(self, amount_to_reduce: Optional[int] = None):
        """Reduces the current load, typically simulating passive load recovery."""
        if amount_to_reduce is None:
            # Default reduction: 10% of current load, at least 1 unit.
            amount_to_reduce = max(1, int(self.current_load * 0.1)) 
        
        self.current_load = max(0, self.current_load - amount_to_reduce)

    # --- Relationship and Trust Management ---
    def add_relationship(self, other_device: 'Device', relationship_type: str,
                         initial_trust: float = 0.5, status: str = 'active',
                         policy: Optional[Any] = None): # 'policy' can be a string ID or a dict
        """Adds a social relationship with another device."""
        if relationship_type not in self.relationships:
            self.relationships[relationship_type] = []
        
        # Avoid duplicate relationships of the same type with the same device
        for rel in self.relationships[relationship_type]:
            if rel['device'].device_id == other_device.device_id:
                return # Relationship already exists

        new_relationship_entry = {
            'device': other_device,
            'type': relationship_type, 
            'trust_score': initial_trust, # Initial trust in the partner for this relationship
            'interactions': 0, # Total interactions within this relationship
            'successful_interactions': 0,
            'failed_interactions': 0,
            'status': status, # e.g., 'active', 'suspended'
            'history': [], # Log of interactions within this relationship
            'policy': policy # Specific policy governing this relationship instance
        }
        self.relationships[relationship_type].append(new_relationship_entry)
        self.log_info(f"Established relationship: {self.nameShort()} --{relationship_type}--> {other_device.nameShort()} (Policy: {str(policy)[:30] if policy else 'None'})")


    def update_trust_from_qoe(self, target_device: Optional['Device'], task_type: str, 
                              measured_qos: Dict[str, Any], interaction_role: str):
        """Updates trust score towards a target device based on Quality of Experience (QoE) of an interaction."""
        if not target_device or self.framework_variant == "baseline":
            # No trust updates in baseline mode or if no target device
            return

        current_trust = self.trust_scores.get(target_device.device_id, 0.5) # Default to neutral trust
        task_successful = measured_qos.get('task_success_binary', 0) == 1
        alpha = self.policy.get('trust_learning_rate', 0.1) # Learning rate for trust updates

        # Simple trust update: increase for success, decrease for failure
        if task_successful:
            current_trust += alpha * (1.0 - current_trust) 
        else:
            current_trust -= alpha * current_trust         
        
        self.trust_scores[target_device.device_id] = max(0.0, min(1.0, current_trust)) # Clamp trust between 0 and 1
        
        # Update relationship-specific trust and interaction history
        for rel_list in self.relationships.values():
            for rel in rel_list:
                if rel['device'].device_id == target_device.device_id:
                    rel['trust_score'] = self.trust_scores[target_device.device_id]
                    rel['interactions'] = rel.get('interactions', 0) + 1
                    if task_successful:
                        rel['successful_interactions'] = rel.get('successful_interactions', 0) + 1
                    else:
                        rel['failed_interactions'] = rel.get('failed_interactions', 0) + 1
                    # Add interaction details to history (capped at 20 entries)
                    rel.get('history', []).append({
                        'minute': self.get_current_minute(),
                        'task_type': task_type,
                        'qos_observed': measured_qos,
                        'role': interaction_role, # e.g., 'performer', 'requester'
                        'new_trust': rel['trust_score']
                    })
                    if len(rel.get('history',[])) > 20: rel['history'].pop(0) 
                    break # Found and updated the specific relationship
        
        self.log_debug(f"Updated trust for {target_device.nameShort()} to {self.trust_scores[target_device.device_id]:.2f} after task '{task_type}' (Success: {task_successful})")

    # --- Task Handling and Negotiation ---
    def negotiate_load(self, from_device: Optional['Device'], task_type: str, load_requested: int, details: Dict) -> bool:
        """Negotiates whether to accept a task based on load and device status/profile."""
        if self.status != "active":
            self.log_warning(f"Cannot accept task '{task_type}', device status is '{self.status}'.")
            if self.sim_metrics_ref: self.sim_metrics_ref['unresponsive_device_rejections'] = self.sim_metrics_ref.get('unresponsive_device_rejections',0) + 1
            return False

        # Check if requested load exceeds device's overall capacity
        if self.current_load + load_requested > self.max_load:
            self.log_warning(f"Rejected task '{task_type}' from {from_device.nameShort() if from_device else 'N/A'} due to OVERLOAD. Requested: {load_requested}, Current: {self.current_load}, Max: {self.max_load}")
            if self.sim_metrics_ref: self.sim_metrics_ref['unresponsive_device_rejections'] = self.sim_metrics_ref.get('unresponsive_device_rejections',0) + 1 # Using this for general rejections for now
            return False
        
        # Check against policy: max load device will take for a single task relative to its max capacity
        max_acceptable_load_for_task = self.max_load * self.policy.get('rules',{}).get('max_load_contribution_percent', 0.75)
        if load_requested > max_acceptable_load_for_task :
            self.log_warning(f"Rejected task '{task_type}' from {from_device.nameShort() if from_device else 'N/A'} as requested load {load_requested} exceeds task threshold {max_acceptable_load_for_task} ({self.policy.get('rules',{}).get('max_load_contribution_percent', 0.75)*100}% of max).")
            return False

        # Selfish behavior: reject if reward/load ratio is too low
        if self.behavior_profile == 'selfish' and self.framework_variant != "baseline":
            task_reward = details.get('iot_app_reward', self.base_task_reward) 
            selfish_threshold = self.policy.get('selfish_rejection_threshold', 0.3) # Example policy value
            # Reject if reward per unit of load is below a threshold (e.g., 30% of base reward per 10 units of load)
            if (task_reward / load_requested if load_requested > 0 else task_reward) < (self.base_task_reward / 10 * selfish_threshold) : 
                 if random.random() < self.policy.get('selfish_rejection_probability', 0.5): # Another policy value
                    self.log_info(f"Selfish device {self.nameShort()} REJECTING task '{task_type}' (low reward/load ratio).")
                    if self.sim_metrics_ref: self.sim_metrics_ref['selfish_rejections'] = self.sim_metrics_ref.get('selfish_rejections',0) + 1
                    return False
        
        # If all checks pass
        return True 

    def handle_request(self, from_device: Optional['Device'], task_type: str,
                       load_requested: int = 10, details: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Handles an incoming task request.
        This base method performs common checks. Subclasses override this to add specific task logic.
        """
        request_start_time = time.time()
        details = details if details is not None else {}
        
        self.log_debug(f"Received task '{task_type}' from {from_device.nameShort() if from_device else 'environment/self'} with load {load_requested}. Current load: {self.current_load}")

        # Perform negotiation and common pre-checks (e.g., device status, load)
        negotiation_passed = self.negotiate_load(from_device, task_type, load_requested, details)
        if not negotiation_passed:
            overall_response_time_ms = (time.time() - request_start_time) * 1000
            measured_qos = {'task_success_binary': 0, 'response_time_ms': overall_response_time_ms, 'expected_load_for_task': load_requested}
            # 'success': False here means the initial request handling (negotiation/pre-checks) failed.
            return {'success': False, 'reason': 'rejected_by_load_negotiation_or_pre_checks', 
                    'measured_qos_for_requestor': measured_qos, 'request_start_time': request_start_time}

        # --- MODIFIED LOGIC ---
        action_result: Dict[str, Any] = {}
        
        # Check if this instance is a direct instance of Device class (i.e., not a subclass instance).
        # If so, it should only handle its own defined generic tasks.
        if type(self) == Device:
            if task_type == "PERIODIC_HEALTH_CHECK" or task_type == "basic_operation":
                load_cost = max(1, int(load_requested * 0.5)) # Example load cost for generic task
                if self.consume_load(load_cost):
                    # Simulate minimal work for a base device health check or basic operation
                    time.sleep(0.001) 
                    action_result = {'success': True, 'value': 'OK_BASE_DEVICE', 'load_consumed': load_cost, 'processing_time_ms': (time.time() - request_start_time) * 1000}
                    self.log_debug(f"Base Device instance {self.nameShort()} performed generic task '{task_type}'.")
                else:
                    action_result = {'success': False, 'reason': 'overload_at_action_base_device_instance', 'load_consumed': 0}
            else:
                # If it's a base Device instance and task is not generic, then it's genuinely an unsupported task for this specific object.
                self.log_warning(f"Rejected: Base Device INSTANCE {self.nameShort()} cannot directly handle specialized task type '{task_type}'.")
                action_result = {'success': False, 'reason': 'unsupported_task_type_for_direct_base_device_instance'}
        
            # Finalize and return if the base Device instance itself handled (or attempted to handle) the task
            overall_response_time_ms = (time.time() - request_start_time) * 1000
            measured_qos_for_trust_and_requestor = {
                'task_success_binary': 1 if action_result.get('success') else 0,
                'response_time_ms': overall_response_time_ms,
                'load_consumed': action_result.get('load_consumed', 0),
                'expected_load_for_task': load_requested,
                'processing_time_ms': action_result.get('processing_time_ms', overall_response_time_ms if action_result.get('success') else 0),
            }
            # Trust update for interaction handled by base device instance
            if from_device: # Only update trust if the request came from another device
                 self.update_trust_from_qoe(from_device, task_type, measured_qos_for_trust_and_requestor, interaction_role="performer")

            if action_result.get('success'):
                # Only pay reward if it's for an external requestor (or if self-initiated tasks also grant rewards)
                # For now, assuming only externally requested tasks (from_device is not None) might have rewards.
                if from_device: 
                    self.receive_income(details.get('iot_app_reward', self.base_task_reward), f"{task_type} completion by base device instance")
                return {'success': True, 'reason': action_result.get('reason', f'{task_type}_successful_base_device_instance'), 'value': action_result.get('value'),
                        'measured_qos_for_requestor': measured_qos_for_trust_and_requestor, 'request_start_time': request_start_time}
            else:
                return {'success': False, 'reason': action_result.get('reason', 'base_device_instance_task_failed'),
                        'measured_qos_for_requestor': measured_qos_for_trust_and_requestor, 'request_start_time': request_start_time}

        # If this point is reached, it means:
        # 1. Negotiation and pre-checks passed.
        # 2. This is NOT a direct instance of `Device`, so it's a subclass calling `super().handle_request()`.
        #    The base class should not perform the action or reject it based on task_type; 
        #    it should let the subclass's `handle_request` method continue to handle it.
        #    The 'success': True here indicates that common pre-checks were okay.
        return {'success': True, 
                'reason': 'negotiation_ok_pending_subclass_handling', 
                'request_start_time': request_start_time
               }
    # --- End of MODIFIED LOGIC ---

    # --- Financial and Status Methods ---
    def receive_income(self, amount: float, reason: str):
        """Increases device balance due to earned income."""
        self.balance += amount
        self.total_income_earned += amount
        self.log_debug(f"Received income: {amount:.2f} for {reason}. New balance: {self.balance:.2f}")

    def pay_expense(self, amount: float, recipient: Optional['Device'], reason: str):
        """Decreases device balance due to an expense. Returns True if payment successful."""
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
        """Applies a penalty to another device."""
        if hasattr(target_device, 'receive_penalty'):
            target_device.receive_penalty(penalty_amount, reason, self) # Pass self as the penalizing device
            self.log_info(f"Applied penalty of {penalty_amount:.2f} to {target_device.nameShort()} for: {reason}")

    def receive_penalty(self, amount: float, reason: str, from_device: Optional['Device']):
        """Decreases device balance due to a received penalty and adjusts trust towards penalizer."""
        self.balance -= amount
        self.total_penalties_received += amount
        self.log_warning(f"Received penalty: {amount:.2f} from {from_device.nameShort() if from_device else 'System'} for {reason}. New balance: {self.balance:.2f}")
        
        # If penalized by another device, reduce trust towards that device
        if from_device and self.framework_variant == "full_siot":
            current_trust = self.trust_scores.get(from_device.device_id, 0.5)
            # Penalty impact on trust could be proportional to penalty amount relative to a base reward
            trust_reduction_factor = (amount / self.base_task_reward) * 0.5 # Example: penalty equivalent to half a task reward reduces trust significantly
            updated_trust = max(0, current_trust - trust_reduction_factor ) 
            self.trust_scores[from_device.device_id] = updated_trust
            self.log_info(f"Trust towards {from_device.nameShort()} reduced to {updated_trust:.2f} due to penalty received.")

    def report_status(self):
        """Logs the current status of the device."""
        self.log_info(f"Status - Load: {self.current_load}/{self.max_load}, Balance: {self.balance:.2f}, Trust Scores: {self.trust_scores}")

    def select_worker_for_task(self, worker_list: List['Device'], task_description: str) -> Optional['Device']:
        """
        Selects a suitable worker from a list for a given task.
        In baseline, picks randomly. In social modes, considers trust and load.
        """
        if not worker_list:
            self.log_debug(f"No workers provided for task '{task_description}'.")
            return None

        if self.framework_variant == "baseline":
            return random.choice(worker_list) # Simplest selection for baseline
        else: # For "social_basic" and "full_siot"
            available_workers = [
                w for w in worker_list
                if w.current_load < w.max_load * 0.90 and # Consider workers not already overloaded
                not any(r.get('device') == w for r in self.relationships.get('avoid-me',[])) # Avoid if in avoid-me list
                # Could add check for w.status == "active" if devices can go inactive
            ]
            if not available_workers:
                self.log_debug(f"No available (non-overloaded/non-avoided) workers for task '{task_description}' among {len(worker_list)} candidates.")
                return None
            
            if self.framework_variant == "full_siot":
                # Sort by trust score (descending), then by current load (ascending)
                # Get trust score from the relationship entry if available, else from device's general trust_scores
                def get_trust_for_sort(worker_device: Device) -> float:
                    rel = self.get_relationship_with(worker_device, "controller_for") # Assuming this composite controls the worker
                    if rel and 'trust_score' in rel:
                        return rel['trust_score']
                    return self.trust_scores.get(worker_device.device_id, 0.5) # Fallback to general trust

                sorted_workers = sorted(available_workers, key=lambda w: (get_trust_for_sort(w), -w.current_load), reverse=True)
            else: # "social_basic" - might only consider load or basic availability
                sorted_workers = sorted(available_workers, key=lambda w: -w.current_load, reverse=True) # Prioritize less loaded

            selected_worker = sorted_workers[0]
            
            trust_str = "N/A"
            if self.framework_variant == "full_siot":
                trust_val = self.trust_scores.get(selected_worker.device_id, None)
                if trust_val is not None: trust_str = f"{trust_val:.2f}"
            
            self.log_debug(f"Selected worker {selected_worker.nameShort()} (Trust: {trust_str}, Load: {selected_worker.current_load}/{selected_worker.max_load}) for '{task_description}'.")
            return selected_worker

    def get_relationship_with(self, partner_device: 'Device', relation_type: Optional[str] = None) -> Optional[Dict]:
        """Retrieves a specific relationship entry with a partner device."""
        if not partner_device: return None
        
        if relation_type:
            if relation_type in self.relationships:
                for rel_entry in self.relationships[relation_type]:
                    if rel_entry.get('device') == partner_device:
                        return rel_entry
        else: # Search all relationship types if not specified
            for rel_list in self.relationships.values():
                for rel_entry in rel_list:
                    if rel_entry.get('device') == partner_device:
                        return rel_entry
        return None
